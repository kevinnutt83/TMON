# Simple host-mode test for utils log trimming
import tempfile, os, time
from utils import _check_and_trim_log
import settings

if not getattr(settings, 'DEBUG_TESTS', False) and not getattr(settings, 'LORA_SIMULATE', False):
    print('Skipping test_log_trim (disabled in production)')
    raise SystemExit(0)

def test_trim_behavior():
    tmp = tempfile.gettempdir()
    test_file = os.path.join(tmp, 'test_log_trim.log')
    # write 200KB
    data = b'A' * (200 * 1024)
    with open(test_file, 'wb') as f:
        f.write(data)
    window = 64 * 1024
    ok = _check_and_trim_log(test_file, window)
    assert ok
    st = os.stat(test_file)
    sz = st.st_size
    assert sz <= window + 16  # small margin
    os.remove(test_file)
    print('test_trim_behavior: PASS')

if __name__ == '__main__':
    test_trim_behavior()
