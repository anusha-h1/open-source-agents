"""Public deployment access-password checks."""

import base64

from backend.app import main as api


def _header(value: bytes) -> str:
    return "Basic " + base64.b64encode(value).decode("ascii")


def test_access_password_rejects_missing_malformed_and_wrong_headers():
    expected = "a-long-private-test-password"
    assert not api.has_valid_access_password("", expected)
    assert not api.has_valid_access_password("Basic not-base64", expected)
    assert not api.has_valid_access_password(_header(b"other:" + expected.encode()), expected)
    assert not api.has_valid_access_password(_header(b"sqlbuddy:wrong"), expected)


def test_access_password_accepts_the_configured_utf8_password():
    password = "secure-test-password-123"
    assert api.has_valid_access_password(_header(f"sqlbuddy:{password}".encode()), password)


def test_public_mode_fails_startup_when_password_is_missing_or_too_short():
    for password in ("", "short"):
        try:
            api.validate_access_password_config(True, password)
        except RuntimeError as error:
            assert "at least 16 characters" in str(error)
        else:
            raise AssertionError("Public mode must reject a missing or short password.")

    api.validate_access_password_config(True, "a-long-private-test-password")
    api.validate_access_password_config(False, "")
