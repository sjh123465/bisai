"""认证与权限单元测试"""
import time
import pytest
from app.core.security import (
    hash_password, verify_password, create_token, decode_token,
)


class TestPassword:
    def test_roundtrip(self):
        stored = hash_password("s3cret!")
        assert verify_password("s3cret!", stored)

    def test_wrong_password(self):
        stored = hash_password("right")
        assert not verify_password("wrong", stored)

    def test_unique_salt(self):
        a, b = hash_password("same"), hash_password("same")
        assert a["salt"] != b["salt"]


class TestToken:
    def test_roundtrip(self):
        tok = create_token("alice", "student")
        payload = decode_token(tok)
        assert payload["u"] == "alice"
        assert payload["r"] == "student"

    def test_tampered(self):
        tok = create_token("alice", "student")
        assert decode_token(tok + "x") is None

    def test_expired(self):
        import base64, hmac, hashlib, json
        from app.core.security import _secret
        raw = base64.urlsafe_b64encode(
            json.dumps({"u": "bob", "r": "teacher", "exp": int(time.time()) - 10}).encode()
        ).decode()
        sig = hmac.new(_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
        assert decode_token(f"{raw}.{sig}") is None
