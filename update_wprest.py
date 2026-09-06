from pathlib import Path
import subprocess

path = Path('micropython/wprest.py')
lines = path.read_text().splitlines(keepends=True)

def has_line(text):
    return any(text in line for line in lines)

# 1-2: add module state after the requested anchor.
if not has_line('LAST_OTA_401_WARN_TS = 0'):
    for i, line in enumerate(lines):
        if line.strip() == 'LAST_REST_SUCCESS_TS = 0':
            lines[i + 1:i + 1] = ['LAST_OTA_401_WARN_TS = 0\n', 'LAST_DIAG_FAIL_TS = 0\n']
            break
    else:
        raise RuntimeError('LAST_REST_SUCCESS_TS = 0 not found')

# Locate function ranges by top-level async/def declarations.
def function_range(name):
    start = next((i for i, line in enumerate(lines)
                  if line.lstrip().startswith(('def ', 'async def ')) and
                  line.lstrip().split('(', 1)[0].split()[-1] == name), None)
    if start is None:
        raise RuntimeError(f'{name} not found')
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace() and lines[i].lstrip().startswith(('def ', 'async def ')):
            end = i
            break
    return start, end

# 3: add a rate-limited 401 response in poll_ota_jobs.
start, end = function_range('poll_ota_jobs')
if not any('OTA request unauthorized (401)' in line for line in lines[start:end]):
    inserted = False
    for i in range(start, end - 1):
        if lines[i].strip() == 'if code == 404:' and lines[i + 1].strip() == 'return []':
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            child = indent + '    '
            block = [
                f'{indent}if code == 401:\n',
                f'{child}now = _now_ts()\n',
                f'{child}if now - LAST_OTA_401_WARN_TS >= 300:\n',
                f'{child}    LAST_OTA_401_WARN_TS = now\n',
                f'{child}    await debug_print("wprest: OTA request unauthorized (401); backing off", "WARN")\n',
                f'{child}return []\n',
            ]
            lines[i + 2:i + 2] = block
            # Add global declaration immediately below the function signature.
            lines[start + 1:start + 1] = ['    global LAST_OTA_401_WARN_TS\n']
            inserted = True
            break
    if not inserted:
        raise RuntimeError('poll_ota_jobs 404 block not found')

# 4: gate diagnostics and suppress attempts during a failure backoff.
start, end = function_range('send_diagnostics_to_wp')
if not any('ENABLE_DIAGNOSTICS_UPLOAD' in line for line in lines[start:end]):
    for i in range(start, end):
        if lines[i].strip() == 'if not wp_url:':
            guard_indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            j = i + 1
            while j < end and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > len(guard_indent)):
                if lines[j].strip() == 'return':
                    j += 1
                    break
                j += 1
            checks = [
                f'{guard_indent}if not globals().get("ENABLE_DIAGNOSTICS_UPLOAD", True):\n',
                f'{guard_indent}    return\n',
                f'{guard_indent}if _now_ts() - LAST_DIAG_FAIL_TS < 300:\n',
                f'{guard_indent}    return\n',
            ]
            lines[j:j] = checks
            start, end = function_range('send_diagnostics_to_wp')
            lines[start + 1:start + 1] = ['    global LAST_DIAG_FAIL_TS\n']
            # Record a failed upload at the function's exception handler.
            for k in range(start, end):
                if lines[k].lstrip().startswith('except Exception'):
                    indent = lines[k][:len(lines[k]) - len(lines[k].lstrip())]
                    lines[k + 1:k + 1] = [f'{indent}    LAST_DIAG_FAIL_TS = _now_ts()\n']
                    break
            else:
                raise RuntimeError('diagnostics exception handler not found')
            break
    else:
        raise RuntimeError('diagnostics wp_url guard not found')

path.write_text(''.join(lines))
subprocess.run(['python', '-m', 'py_compile', str(path)], check=True)
print('SUCCESS: updated micropython/wprest.py and py_compile passed')
