# -*- coding: utf-8 -*-
"""NKDB 解密（复用 04_临时车间/脚本/国际服拆包/tmp_decrypt_lsc_all.py 的算法）"""
import struct, zlib, sys, os
from Crypto.Cipher import AES


def decrypt_nkdb(data):
    assert data[:4] == b'NKDB', data[:8]
    version = int.from_bytes(data[4:8], 'big')
    aes_key = data[8:24]
    segment_size = int.from_bytes(data[24:28], 'big')
    segment_count = int.from_bytes(data[28:32], 'big')
    length_byte_count = 5 if segment_size * segment_count > 0xFFFFFFFF else 4
    pos = 32

    def read_offset(pos):
        val = int.from_bytes(data[pos:pos + length_byte_count], 'big')
        return val, pos + length_byte_count

    current_offset, pos = read_offset(pos)
    segments = []
    for i in range(segment_count):
        next_offset, pos = read_offset(pos)
        segments.append((current_offset, next_offset - current_offset, i))
        current_offset = next_offset
    out = bytearray()
    for offset, length, index in segments:
        seg = data[offset:offset + length]
        iv = struct.pack('<ii', index, offset) + b'\x00' * 8
        cipher = AES.new(aes_key, AES.MODE_OFB, iv=iv)
        dec = cipher.decrypt(seg)
        try:
            dec = zlib.decompress(dec)
        except Exception:
            pass
        out += dec
    return bytes(out)


if __name__ == '__main__':
    src = sys.argv[1]
    dst = sys.argv[2]
    raw = decrypt_nkdb(open(src, 'rb').read())
    open(dst, 'wb').write(raw)
    print('decrypted', len(raw), raw[:64])
