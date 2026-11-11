import time
from pathlib import Path

from fastapi_cloud_cli.utils.auth import AuthConfig, Identity, write_auth_config

from .utils import USER_TOKEN, create_jwt_token


def test_is_logged_in_with_no_token(temp_auth_config: Path) -> None:
    assert not temp_auth_config.exists()
    assert not Identity().is_logged_in()


def test_is_logged_in_with_token(temp_auth_config: Path) -> None:
    write_auth_config(AuthConfig(access_token=USER_TOKEN))

    assert Identity().is_logged_in()


def test_is_logged_in_before_token_expires(temp_auth_config: Path) -> None:
    write_auth_config(
        AuthConfig(access_token=USER_TOKEN, expires_at=int(time.time()) + 3600)
    )

    identity = Identity()

    assert identity.is_logged_in()
    assert not identity.is_user_token_expired()


def test_is_logged_in_with_expired_token(temp_auth_config: Path) -> None:
    write_auth_config(
        AuthConfig(access_token=USER_TOKEN, expires_at=int(time.time()) - 3600)
    )

    identity = Identity()

    assert not identity.is_logged_in()
    assert identity.is_user_token_expired()


def test_token_without_saved_expiry_is_left_to_the_server(
    temp_auth_config: Path,
) -> None:
    past_exp = int(time.time()) - 3600
    token = create_jwt_token({"exp": past_exp, "sub": "test_user"})

    write_auth_config(AuthConfig(access_token=token))

    identity = Identity()

    assert identity.is_logged_in()
    assert not identity.is_user_token_expired()


def test_is_logged_in_with_empty_token(temp_auth_config: Path) -> None:
    write_auth_config(AuthConfig(access_token=""))

    assert not Identity().is_logged_in()
