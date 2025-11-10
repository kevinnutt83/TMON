"""Minimal ChaCha20 stream cipher (insecure nonce reuse caution) for MicroPython.
Usage:
    keystream = chacha20(key32, nonce12, counter)
    ciphertext = xor_bytes(plaintext, keystream[:len(plaintext)])
Pure-Python; optimized for small payloads (<256 bytes).
Not constant time; DO NOT use for high-security contexts without review.
"""
def _rotl32(v, n):
    return ((v << n) & 0xffffffff) | (v >> (32 - n))

def _quarter(a, b, c, d, st):
    st[a] = (st[a] + st[b]) & 0xffffffff; st[d] ^= st[a]; st[d] = _rotl32(st[d], 16)
    st[c] = (st[c] + st[d]) & 0xffffffff; st[b] ^= st[c]; st[b] = _rotl32(st[b], 12)
    st[a] = (st[a] + st[b]) & 0xffffffff; st[d] ^= st[a]; st[d] = _rotl32(st[d], 8)
    st[c] = (st[c] + st[d]) & 0xffffffff; st[b] ^= st[c]; st[b] = _rotl32(st[b], 7)

def chacha20_block(key, counter, nonce):
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError('Bad key/nonce length')
    const = b'expand 32-byte k'
    def load4(b, i):
        return b[i] | (b[i+1]<<8) | (b[i+2]<<16) | (b[i+3]<<24)
    st = [0]*16
    st[0]=load4(const,0); st[1]=load4(const,4); st[2]=load4(const,8); st[3]=load4(const,12)
    for i in range(8): st[4+i]=load4(key, i*4)
    st[12]=counter & 0xffffffff
    st[13]=load4(nonce,0); st[14]=load4(nonce,4); st[15]=load4(nonce,8)
    working=st[:]    
    for _ in range(10):
        _quarter(0,4,8,12,working); _quarter(1,5,9,13,working); _quarter(2,6,10,14,working); _quarter(3,7,11,15,working)
        _quarter(0,5,10,15,working); _quarter(1,6,11,12,working); _quarter(2,7,8,13,working); _quarter(3,4,9,14,working)
    for i in range(16): working[i] = (working[i] + st[i]) & 0xffffffff
    out = bytearray(64)
    for i,w in enumerate(working):
        out[i*4]   = w & 0xff
        out[i*4+1] = (w>>8) & 0xff
        out[i*4+2] = (w>>16) & 0xff
        out[i*4+3] = (w>>24) & 0xff
    return bytes(out)

def chacha20_encrypt(key, nonce, counter, data):
    out = bytearray(len(data))
    off=0; blk_counter=counter
    while off < len(data):
        ks = chacha20_block(key, blk_counter, nonce)
        blk_counter = (blk_counter + 1) & 0xffffffff
        chunk = data[off:off+64]
        for i,b in enumerate(chunk):
            out[off+i] = b ^ ks[i]
        off += len(chunk)
    return bytes(out)

def derive_nonce(ts, ctr):
    # 12-byte nonce from timestamp (4 bytes) + counter (4 bytes) + mixed XOR chunk (4 bytes)
    return ((ts & 0xffffffff).to_bytes(4,'little') + (ctr & 0xffffffff).to_bytes(4,'little') + ((ts ^ ctr) & 0xffffffff).to_bytes(4,'little'))
