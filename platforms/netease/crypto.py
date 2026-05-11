from __future__ import annotations
import base64
import hashlib
import json
import os
import struct

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ── Constants ────────────────────────────────────────────────────────────────

_WEAPI_IV = b"0102030405060708"
_WEAPI_PRESET_KEY = b"0CoJUm6Qyw8W8jud"
_WEAPI_BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Netease RSA public key (known constant)
_RSA_MODULUS = int(
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
    "3c57fae0e1dd5fc56ea925cba6b5aef56b3fd2a0b92d77c81e7d0e1ce3e"
    "7cfe89d32f3d1c5c9527b2b70c4c3acb2c7b2e5a4ce51c10dd5d9ca70f3"
    "0aa1f55de33a51c8d7cebd43f69d1b3fa20a5060db91b10c74f82d4d76c"
    "df9cd3ef9e8a9c3b0843d4b2d4c1c7b5c4f7d43671ec6af2e76a83b47c5"
    "00ed2f2abc5b4bd05c6c5c44ffa8b41218e6e2f5ef3e5d52ee1c85e09ef"
    "6dac84e2bb20cac2ffe3bb8d62e47f487be3b80cbf258d51e6e75be51f3"
    "53c6ca4e893e0ad96a35",
    16,
)
_RSA_EXPONENT = 65537

_EAPI_KEY = b"e82ckenh8dichen8"


# ── weapi encryption ─────────────────────────────────────────────────────────

def _aes_cbc_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(data, AES.block_size))


def _rsa_encrypt(data: bytes) -> str:
    # Raw modpow: reverse the bytes, convert to int, modpow, hex-encode
    n = int.from_bytes(data[::-1], "big")
    result = pow(n, _RSA_EXPONENT, _RSA_MODULUS)
    return format(result, "0256x")


def weapi_encrypt(params: dict) -> dict:
    data = json.dumps(params).encode()

    # Random 16-char secret key from base62 alphabet
    secret_key = "".join(_WEAPI_BASE62[b % 62] for b in os.urandom(16)).encode()

    # First AES pass: encrypt data with preset key
    first_pass = _aes_cbc_encrypt(data, _WEAPI_PRESET_KEY, _WEAPI_IV)
    # Second AES pass: encrypt first_pass with the random secret key
    second_pass = _aes_cbc_encrypt(base64.b64encode(first_pass), secret_key, _WEAPI_IV)
    params_b64 = base64.b64encode(second_pass).decode()

    enc_sec_key = _rsa_encrypt(secret_key)

    return {"params": params_b64, "encSecKey": enc_sec_key}


# ── eapi encryption ──────────────────────────────────────────────────────────

def eapi_encrypt(url: str, params: dict) -> dict:
    params_json = json.dumps(params)
    message = f"nobody{url}use{params_json}md5forencrypt"
    md5_digest = hashlib.md5(message.encode()).hexdigest()
    data = f"{url}-36cd479b6b5-{params_json}-36cd479b6b5-{md5_digest}"

    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import pad as _pad
    cipher = _AES.new(_EAPI_KEY, _AES.MODE_ECB)
    encrypted = cipher.encrypt(_pad(data.encode(), _AES.block_size))
    return {"params": encrypted.hex().upper()}
