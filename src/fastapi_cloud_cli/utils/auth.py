from typing import Optional

from pydantic import BaseModel

from .config import get_auth_path


class AuthConfig(BaseModel):
    access_token: str


def write_auth_config(auth_data: AuthConfig) -> None:
    auth_path = get_auth_path()

    auth_path.write_text(auth_data.model_dump_json(), encoding="utf-8")


def read_auth_config() -> Optional[AuthConfig]:
    auth_path = get_auth_path()

    if not auth_path.exists():
        return None

    return AuthConfig.model_validate_json(auth_path.read_text(encoding="utf-8"))


def get_auth_token() -> Optional[str]:
    auth_data = read_auth_config()

    if auth_data is None:
        return None

    return auth_data.access_token


def is_logged_in() -> bool:
    return get_auth_token() is not None
