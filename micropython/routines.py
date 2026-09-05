import uasyncio as asyncio
import utime as time
import ujson
import settings
import sdata

from utils import debug_print, record_field_data

ROUTINES_FILE = settings.LOG_DIR.rstrip('/') + '/routines.json'
ALLOWED_FIELDS = {'cur_temp_f', 'cur_humid', 'sys_voltage', 'lora_SigStr', 'relay1_on', 'relay2_on'}
ALLOWED_OPS = {'<', '<=', '>', '>=', '==', '!=', 'between'}
ALLOWED_ACTIONS = {'relay', 'log', 'flag', 'record', 'sleep_skip'}
_routines = None
_last_run = {}

def _load():
    global _routines
    if _routines is not None:
        return _routines
    try:
        with open(ROUTINES_FILE, 'r') as handle:
            value = ujson.loads(handle.read())
        _routines = value if isinstance(value, list) else []
    except Exception:
        _routines = []
    return _routines

def _save():
    try:
        with open(ROUTINES_FILE, 'w') as handle:
            handle.write(ujson.dumps(_load()))
        return True
    except Exception:
        return False

def validate_routine(routine):
    if not isinstance(routine, dict) or not str(routine.get('id') or ''):
        return False
    if int(routine.get('period_s') or 30) < 10:
        return False
    conditions = (routine.get('when') or {}).get('all', [])
    for condition in conditions:
        if not isinstance(condition, dict) or condition.get('field') not in ALLOWED_FIELDS or condition.get('op') not in ALLOWED_OPS:
            return False
    for action in (routine.get('then') or []) + (routine.get('else') or []):
        if not isinstance(action, dict) or action.get('action') not in ALLOWED_ACTIONS:
            return False
    return True

def upsert_routine(routine):
    global _routines
    if not validate_routine(routine):
        return False
    routines = _load()
    routine_id = str(routine['id'])
    replaced = False
    for index, existing in enumerate(routines):
        if isinstance(existing, dict) and str(existing.get('id')) == routine_id:
            routines[index] = routine
            replaced = True
            break
    if not replaced:
        if len(routines) >= 16:
            return False
        routines.append(routine)
    _routines = routines
    return _save()

def delete_routine(routine_id):
    global _routines
    _routines = [item for item in _load() if not isinstance(item, dict) or str(item.get('id')) != str(routine_id)]
    return _save()

async def _run_actions(actions):
    for action in actions:
        kind = action.get('action')
        if kind == 'relay':
            from relay import toggle_relay
            await toggle_relay(str(action.get('relay', 1)), 'on' if action.get('state') else 'off', str(action.get('runtime', 0)))
        elif kind == 'log':
            await debug_print(str(action.get('message') or 'routine'), 'ROUTINES')
        elif kind == 'flag':
            setattr(settings, str(action.get('key') or ''), bool(action.get('value')))
        elif kind == 'record':
            record_field_data()
        elif kind == 'sleep_skip' and str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote':
            settings.REMOTE_SLEEP_SKIP_ONCE = True

def _matches(condition):
    value = getattr(sdata, condition['field'], getattr(settings, condition['field'], None))
    target = condition.get('value')
    op = condition['op']
    try:
        if op == 'between':
            return isinstance(target, (list, tuple)) and len(target) == 2 and float(target[0]) <= float(value) <= float(target[1])
        return {'<': float(value) < float(target), '<=': float(value) <= float(target), '>': float(value) > float(target), '>=': float(value) >= float(target), '==': value == target, '!=': value != target}[op]
    except Exception:
        return False

async def run_routines_once():
    now = time.time()
    for routine in _load():
        if not validate_routine(routine) or not routine.get('enabled', True):
            continue
        routine_id = str(routine['id'])
        if now - _last_run.get(routine_id, 0) < int(routine.get('period_s') or 30):
            continue
        _last_run[routine_id] = now
        matched = all(_matches(condition) for condition in (routine.get('when') or {}).get('all', []))
        await _run_actions(routine.get('then' if matched else 'else') or [])
        setattr(sdata, 'routines_state', {'last_id': routine_id, 'last_ts': now, 'matched': matched})
        await asyncio.sleep(0)