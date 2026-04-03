import logging
from typing import Literal

from fastapi_cloud_cli.utils.auth import Identity

logger = logging.getLogger(__name__)


class Context:
    def __init__(self) -> None:
        self._is_initialized = False

    def initialize(self, prefer_auth_mode: Literal["token", "user"] = "user") -> None:
        logger.debug("Initializing context with prefer_auth_mode: %s", prefer_auth_mode)
        self.prefer_auth_mode = prefer_auth_mode
        self._is_initialized = True

    def get_identity(self) -> Identity:
        if not self._is_initialized:  # pragma: no cover
            raise RuntimeError("Context must be initialized before use")
        return Identity(prefer_auth_mode=self.prefer_auth_mode)


ctx = Context()
