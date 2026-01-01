import tempfile, os, time
import lora
import settings

if not getattr(settings, 'DEBUG_TESTS', False) and not getattr(settings, 'LORA_SIMULATE', False):
    print('Skipping test_chunk_dump_rotation (disabled in production)')
    raise SystemExit(0)

def test_rotate_keep_n():
    td = tempfile.mkdtemp()
    base = 'lora_chunks.json'
    # create 10 timestamped files
    for i in range(10):
        fname = base.rstrip('.json') + f".20250101_00000{i}.json"
        with open(os.path.join(td, fname), 'w') as f:
            f.write('{}')
        time.sleep(0.01)
    # rotate keeping last 4
    lora.rotate_chunk_dumps(td, base, keep_n=4)
    files = sorted([f for f in os.listdir(td) if f.endswith('.json') and f.startswith(base.rstrip('.json') + '.')])
    assert len(files) <= 4
    print('test_rotate_keep_n: PASS')
    # cleanup
    for f in os.listdir(td):
        try: os.remove(os.path.join(td, f))
        except Exception: pass
    os.rmdir(td)

if __name__ == '__main__':
    test_rotate_keep_n()
