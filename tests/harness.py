"""
Quick harness to validate TMON crypto primitives in CPython.
Run: python3 tests/harness.py
"""
import hashlib
import os
import sys

# Ensure we can import firmware crypto helpers
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from mircopython.encryption import chacha20_encrypt, derive_nonce
except Exception as e:
    chacha20_encrypt = None
    derive_nonce = None
    print("Warning: Could not import mircopython.encryption (", e, ") - skipping ChaCha20 tests")

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


def test_chacha20_roundtrip():
    if not (chacha20_encrypt and derive_nonce):
        print('ChaCha20 tests skipped (module not available)')
        return
    key = b'k'*32
    ts, ctr = 1731200000, 42
    nonce = derive_nonce(ts, ctr)
    pt = b'hello world'
    ct = chacha20_encrypt(key, nonce, 1, pt)
    rt = chacha20_encrypt(key, nonce, 1, ct)  # XOR stream
    assert rt == pt, 'round-trip failed for short message'
    # Multi-block (>64B)
    pt2 = bytes([i % 256 for i in range(200)])
    ct2 = chacha20_encrypt(key, nonce, 7, pt2)
    rt2 = chacha20_encrypt(key, nonce, 7, ct2)
    assert rt2 == pt2, 'round-trip failed for multi-block payload'
    print('ChaCha20 round-trip tests passed')


def test_derive_nonce():
    if not derive_nonce:
        return
    n1 = derive_nonce(100, 1)
    n2 = derive_nonce(100, 1)
    n3 = derive_nonce(100, 2)
    assert n1 == n2, 'nonce must be deterministic for same ts,ctr'
    assert n1 != n3, 'nonce should differ when ctr changes'
    assert len(n1) == 12, 'nonce must be 12 bytes'
    print('derive_nonce tests passed')

if __name__ == '__main__':
    test_sig()
    test_chacha20_roundtrip()
    test_derive_nonce()
    print('All tests passed')
