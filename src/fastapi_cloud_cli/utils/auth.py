import logging
import os
import time
from typing import Literal

from pydantic import BaseModel

from .config import get_auth_path

logger = logging.getLogger("fastapi_cli")

AuthMode = Literal["token", "user"]


class AuthConfig(BaseModel):
    access_token: str
    # Unix time when FastAPI Cloud expires the token. Older logins didn't save it.
    expires_at: int | None = None


def write_auth_config(auth_data: AuthConfig) -> None:
    auth_path = get_auth_path()
    logger.debug("Writing auth config to: %s", auth_path)

    auth_path.write_text(auth_data.model_dump_json(), encoding="utf-8")
    logger.debug("Auth config written successfully")


def delete_auth_config() -> None:
    auth_path = get_auth_path()
    logger.debug("Deleting auth config at: %s", auth_path)

    if auth_path.exists():
        auth_path.unlink()
        logger.debug("Auth config deleted successfully")
    else:
        logger.debug("Auth config file doesn't exist, nothing to delete")


def read_auth_config() -> AuthConfig | None:
    auth_path = get_auth_path()
    logger.debug("Reading auth config from: %s", auth_path)

    if not auth_path.exists():
        logger.debug("Auth config file doesn't exist")
        return None

    logger.debug("Auth config loaded successfully")
    return AuthConfig.model_validate_json(auth_path.read_text(encoding="utf-8"))


class Identity:
    def __init__(self) -> None:
        auth_config = read_auth_config()
        self._user_token = auth_config.access_token if auth_config else None
        self._user_token_expires_at = auth_config.expires_at if auth_config else None
        self._deploy_token: str | None = os.environ.get("FASTAPI_CLOUD_TOKEN")

    @property
    def user_token(self) -> str | None:
        return self._user_token

    @property
    def deploy_token(self) -> str | None:
        return self._deploy_token

    def is_user_token_expired(self) -> bool:
        # Without a saved expiry, only FastAPI Cloud can tell, with a 401.
        if self._user_token_expires_at is None:
            return False

        return time.time() >= self._user_token_expires_at

    def is_logged_in(self) -> bool:
        if not self._user_token:
            logger.debug("Login status: False (no token)")
            return False

        if self.is_user_token_expired():
            logger.debug("Login status: False (token expired)")
            return False

        # A revoked token still gets a 401, which deletes the stored token.
        logger.debug("Login status: True")
        return True

    def has_deploy_token(self) -> bool:
        if self._deploy_token is None:
            logger.debug("Deploy token is not provided")
            return False

        logger.debug("Deploy token found")
        return True
