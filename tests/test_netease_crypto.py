import json
from platforms.netease.crypto import weapi_encrypt, eapi_encrypt


def test_weapi_encrypt_returns_params_and_enc_sec_key():
    result = weapi_encrypt({"s": "hello", "type": 1, "limit": 5})
    assert "params" in result
    assert "encSecKey" in result
    assert isinstance(result["params"], str)
    assert isinstance(result["encSecKey"], str)


def test_weapi_encrypt_params_is_base64():
    import base64
    result = weapi_encrypt({"s": "hello"})
    base64.b64decode(result["params"])


def test_weapi_encrypt_different_calls_produce_different_params():
    r1 = weapi_encrypt({"s": "hello"})
    r2 = weapi_encrypt({"s": "hello"})
    assert r1["params"] != r2["params"]


def test_eapi_encrypt_returns_params():
    result = eapi_encrypt("/api/cloudsearch/pc", {"s": "test", "type": 1})
    assert "params" in result
    assert isinstance(result["params"], str)


def test_eapi_encrypt_is_hex():
    result = eapi_encrypt("/api/song/lyric", {"id": 123})
    bytes.fromhex(result["params"])
