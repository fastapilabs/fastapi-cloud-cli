import logging
import time

import httpx
from pydantic import BaseModel
from rich_toolkit import RichToolkit
from rich_toolkit.progress import Progress

from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import AuthConfig, AuthMode, write_auth_config
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit

logger = logging.getLogger(__name__)

DEFAULT_LOGIN_TIMEOUT_SECONDS = 300


class AuthorizationData(BaseModel):
    user_code: str
    device_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: int = 5


class TokenResponse(BaseModel):
    access_token: str


class LoginOutput(BaseModel):
    authenticated: bool
    auth_mode: AuthMode


class DeviceAuthorizationOutput(BaseModel):
    verification_uri: str
    verification_uri_complete: str
    user_code: str
    device_code: str
    interval: int


class LoginTimeoutError(Exception):
    pass


def render_login_output(data: LoginOutput, toolkit: RichToolkit) -> None:
    toolkit.print("Now you are logged in! 🚀")


def device_authorization_output(
    authorization_data: AuthorizationData,
) -> DeviceAuthorizationOutput:
    return DeviceAuthorizationOutput(
        verification_uri=authorization_data.verification_uri,
        verification_uri_complete=authorization_data.verification_uri_complete,
        user_code=authorization_data.user_code,
        device_code=authorization_data.device_code,
        interval=authorization_data.interval,
    )


def start_device_authorization(
    client: httpx.Client,
) -> AuthorizationData:
    settings = Settings.get()

    response = client.post(
        "/login/device/authorization", data={"client_id": settings.client_id}
    )
    logger.debug(f"Device authorization response status code: {response.status_code}")

    response.raise_for_status()

    return AuthorizationData.model_validate_json(response.text)


def fetch_access_token(
    client: httpx.Client,
    device_code: str,
    interval: int,
    timeout: int = DEFAULT_LOGIN_TIMEOUT_SECONDS,
) -> str:
    settings = Settings.get()
    start = time.monotonic()

    logger.debug("Starting to poll for access token")
    while True:
        response = client.post(
            "/login/device/token",
            data={
                "device_code": device_code,
                "client_id": settings.client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        logger.debug(f"Token response status code: {response.status_code}")

        if response.status_code not in (200, 400):
            response.raise_for_status()

        if response.status_code == 400:
            data = response.json()
            error = data.get("error")
            logger.debug(f"Token response error: {error}")

            if error != "authorization_pending":
                response.raise_for_status()

        if response.status_code == 200:
            break

        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            raise LoginTimeoutError

        sleep_for = min(interval, remaining)

        logger.debug(f"Sleeping for {sleep_for} seconds before retrying...")
        time.sleep(sleep_for)

    response_data = TokenResponse.model_validate_json(response.text)
    logger.debug("Access token received successfully.")

    return response_data.access_token


def complete_device_login(
    *,
    client: APIClient,
    progress: Progress,
    toolkit: FastAPIRichToolkit,
    device_code: str,
    interval: int,
    timeout: int,
    cancel_hint: str,
) -> LoginOutput:
    try:
        with client.handle_http_errors(progress, toolkit=toolkit):
            access_token = fetch_access_token(client, device_code, interval, timeout)
    except LoginTimeoutError:
        message = "Login timed out before authorization completed."
        toolkit.fail(
            "timeout",
            message,
            hint="Try again with a longer --timeout value.",
        )
    except KeyboardInterrupt:
        message = "Login cancelled before authorization completed."
        toolkit.fail(
            "cancelled",
            message,
            hint=cancel_hint,
        )

    write_auth_config(AuthConfig(access_token=access_token))

    return LoginOutput(authenticated=True, auth_mode="user")
