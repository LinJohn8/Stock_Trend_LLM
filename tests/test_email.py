from __future__ import annotations

from utils.email_utils import validate_email


def test_validate_email() -> None:
    assert validate_email("a@example.com")
    assert not validate_email("bad-address")
