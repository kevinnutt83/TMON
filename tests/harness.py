"""
Quick harness to validate TMON crypto primitives in CPython.
Run: python3 tests/harness.py
"""
import hashlib

def firmware_field_data_sig(secret, unit_id, firmware_version, node_type, count, first_ts, last_ts, trunc=32):
    canon = f"{unit_id}|{firmware_version}|{node_type}|{count}|{first_ts}|{last_ts}"
    h = hashlib.sha256((secret + canon).encode()).hexdigest()
    return h[:trunc]

def test_sig():
    secret = 's3cr3t'
    sig = firmware_field_data_sig(secret, 'U123', 'v2.00j', 'base', 10, 111, 222, 32)
    assert len(sig) == 32
    assert sig == hashlib.sha256((secret + 'U123|v2.00j|base|10|111|222').encode()).hexdigest()[:32]
    print('HMAC signature test passed')

if __name__ == '__main__':
    test_sig()
    print('All tests passed')
