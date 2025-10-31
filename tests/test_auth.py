import base64
import time
from pathlib import Path

import pytest

from fastapi_cloud_cli.utils.auth import (
    AuthConfig,
    is_logged_in,
    is_token_expired,
    write_auth_config,
)

from .utils import create_jwt_token


def test_is_token_expired_with_valid_token() -> None:
    future_exp = int(time.time()) + 3600

    token = create_jwt_token({"exp": future_exp, "sub": "test_user"})

    assert not is_token_expired(token)


def test_is_token_expired_with_expired_token() -> None:
    past_exp = int(time.time()) - 3600
    token = create_jwt_token({"exp": past_exp, "sub": "test_user"})

    assert is_token_expired(token)


def test_is_token_expired_with_no_exp_claim() -> None:
    token = create_jwt_token({"sub": "test_user"})

    # Tokens without exp claim should be considered valid
    assert not is_token_expired(token)


@pytest.mark.parametrize(
    "token",
    [
        "not.a.valid.jwt.token",
        "only.two",
        "invalid",
        "",
        "...",
    ],
)
def test_is_token_expired_with_malformed_token(token: str) -> None:
    assert is_token_expired(token)


def test_is_token_expired_with_invalid_base64() -> None:
    token = "header.!!!invalid_signature!!!.signature"
    assert is_token_expired(token)


def test_is_token_expired_with_invalid_json() -> None:
    header_encoded = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload_encoded = base64.urlsafe_b64encode(b"{invalid json}").decode().rstrip("=")
    signature = base64.urlsafe_b64encode(b"signature").decode().rstrip("=")
    token = f"{header_encoded}.{payload_encoded}.{signature}"

    assert is_token_expired(token)


def test_is_logged_in_with_no_token(temp_auth_config: Path) -> None:
    assert not temp_auth_config.exists()
    assert not is_logged_in()


def test_is_logged_in_with_valid_token(temp_auth_config: Path) -> None:
    future_exp = int(time.time()) + 3600
    token = create_jwt_token({"exp": future_exp, "sub": "test_user"})

    write_auth_config(AuthConfig(access_token=token))

    assert is_logged_in()


def test_is_logged_in_with_expired_token(temp_auth_config: Path) -> None:
    past_exp = int(time.time()) - 3600
    token = create_jwt_token({"exp": past_exp, "sub": "test_user"})

    write_auth_config(AuthConfig(access_token=token))

    assert not is_logged_in()


def test_is_logged_in_with_malformed_token(temp_auth_config: Path) -> None:
    write_auth_config(AuthConfig(access_token="not.a.valid.token"))

    assert not is_logged_in()


def test_is_token_expired_edge_case_exact_expiration() -> None:
    current_time = int(time.time())
    token = create_jwt_token({"exp": current_time, "sub": "test_user"})

    assert is_token_expired(token)


def test_is_token_expired_edge_case_one_second_before() -> None:
    current_time = int(time.time())
    token = create_jwt_token({"exp": current_time + 1, "sub": "test_user"})

    assert not is_token_expired(token)
