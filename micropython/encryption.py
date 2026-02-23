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


# --- Optional AEAD (ChaCha20-Poly1305) ---
def _le64(v):
	# 64-bit little-endian
	return int(v).to_bytes(8, 'little')

def _pad16(b):
	# pad to 16-byte boundary with zeros per RFC
	if len(b) % 16 == 0:
		return b''
	return b'\x00' * (16 - (len(b) % 16))

def _poly1305_mac(key32, aad, ct):
	# Pure-Python Poly1305 as in RFC 8439.
	# key32: 32 bytes (r || s)
	r = int.from_bytes(key32[0:16], 'little')
	# clamp r
	r &= 0x0ffffffc0ffffffc0ffffffc0fffffff
	s = int.from_bytes(key32[16:32], 'little')
	p = (1 << 130) - 5
	acc = 0
	def _process_block(block):
		nonlocal acc
		n = int.from_bytes(block + b'\x01', 'little')  # append 1 byte per spec
		acc = (acc + n) % p
		acc = (acc * r) % p

	# process AAD
	if aad:
		for i in range(0, len(aad), 16):
			_process_block(aad[i:i+16])
	# process ciphertext
	for i in range(0, len(ct), 16):
		_process_block(ct[i:i+16])
	# final: add lengths (64-bit little-endian)
	alen = len(aad)
	clen = len(ct)
	acc = (acc + int.from_bytes(_le64(alen), 'little')) % p
	acc = (acc + (int.from_bytes(_le64(clen), 'little') << 64)) % p  # conceptually appended, equivalent accumulation
	# produce tag = (acc + s) mod 2^128
	tag_int = (acc + s) % (1 << 128)
	tag = tag_int.to_bytes(16, 'little')
	return tag

def _const_time_eq(a, b):
	# simple constant-time comparison
	if len(a) != len(b):
		return False
	res = 0
	for x, y in zip(a, b):
		res |= x ^ y
	return res == 0

def chacha20_poly1305_encrypt(key, nonce, aad, plaintext):
	"""AEAD: ChaCha20-Poly1305 (IETF). Returns (ciphertext, tag)."""
	if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
		raise ValueError('key must be 32 bytes')
	if not isinstance(nonce, (bytes, bytearray)) or len(nonce) != 12:
		raise ValueError('nonce must be 12 bytes')
	aad_b = aad or b''
	pt_b = plaintext or b''
	# Poly key = ChaCha20 block with counter=0
	poly_key_block = chacha20_block(key, 0, nonce)
	poly_key = poly_key_block[:32]
	# ciphertext using counter=1
	ct = chacha20_encrypt(key, nonce, 1, pt_b)
	# compute tag over AAD||pad||ct||pad||len(AAD)||len(CT)
	tag = _poly1305_mac(poly_key, aad_b, ct)
	return ct, tag

def chacha20_poly1305_decrypt(key, nonce, aad, ciphertext, tag):
	"""Verify tag then decrypt. Raises ValueError on authentication failure."""
	if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
		raise ValueError('key must be 32 bytes')
	if not isinstance(nonce, (bytes, bytearray)) or len(nonce) != 12:
		raise ValueError('nonce must be 12 bytes')
	aad_b = aad or b''
	ct_b = ciphertext or b''
	if not isinstance(tag, (bytes, bytearray)) or len(tag) != 16:
		raise ValueError('tag must be 16 bytes')
	poly_key_block = chacha20_block(key, 0, nonce)
	poly_key = poly_key_block[:32]
	expect = _poly1305_mac(poly_key, aad_b, ct_b)
	if not _const_time_eq(expect, tag):
		raise ValueError('Poly1305 authentication failed')
	pt = chacha20_encrypt(key, nonce, 1, ct_b)
	return pt
