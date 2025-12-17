import base64
import binascii
import json
import logging
import time
from typing import Optional

from pydantic import BaseModel

from .config import get_auth_path

logger = logging.getLogger("fastapi_cli")


class AuthConfig(BaseModel):
    access_token: str


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


def read_auth_config() -> Optional[AuthConfig]:
    auth_path = get_auth_path()
    logger.debug("Reading auth config from: %s", auth_path)

    if not auth_path.exists():
        logger.debug("Auth config file doesn't exist")
        return None

    logger.debug("Auth config loaded successfully")
    return AuthConfig.model_validate_json(auth_path.read_text(encoding="utf-8"))


def get_auth_token() -> Optional[str]:
    logger.debug("Getting auth token")
    auth_data = read_auth_config()

    if auth_data is None:
        logger.debug("No auth data found")
        return None

    logger.debug("Auth token retrieved successfully")
    return auth_data.access_token


def is_token_expired(token: str) -> bool:
    try:
        parts = token.split(".")

        if len(parts) != 3:
            logger.debug("Invalid JWT format: expected 3 parts, got %d", len(parts))
            return True

        payload = parts[1]

        # Add padding if needed (JWT uses base64url encoding without padding)
        if padding := len(payload) % 4:
            payload += "=" * (4 - padding)

        payload = payload.replace("-", "+").replace("_", "/")
        decoded_bytes = base64.b64decode(payload)
        payload_data = json.loads(decoded_bytes)

        exp = payload_data.get("exp")

        if exp is None:
            logger.debug("No 'exp' claim found in token")

            return False

        if not isinstance(exp, int):  # pragma: no cover
            logger.debug("Invalid 'exp' claim: expected int, got %s", type(exp))

            return True

        current_time = time.time()

        is_expired = current_time >= exp

        logger.debug(
            "Token expiration check: current=%d, exp=%d, expired=%s",
            current_time,
            exp,
            is_expired,
        )

        return is_expired
    except (binascii.Error, json.JSONDecodeError) as e:
        logger.debug("Error parsing JWT token: %s", e)

        return True


def is_logged_in() -> bool:
    token = get_auth_token()

    if token is None:
        logger.debug("Login status: False (no token)")
        return False

    if is_token_expired(token):
        logger.debug("Login status: False (token expired)")
        return False

    logger.debug("Login status: True")
    return True
