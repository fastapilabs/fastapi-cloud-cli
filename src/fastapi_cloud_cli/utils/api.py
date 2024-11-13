import httpx

from fastapi_cloud_cli.config import settings

from .auth import get_auth_token


class APIClient(httpx.Client):
    def __init__(self) -> None:
        token = get_auth_token()

        super().__init__(
            base_url=settings.base_api_url, headers={"Authorization": f"Bearer {token}"}
        )
