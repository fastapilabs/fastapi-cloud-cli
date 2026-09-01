import json
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta

import httpx
import typer
from agent_detector import detect_agent
from pydantic import ValidationError
from rich_toolkit.progress import Progress

from fastapi_cloud_cli import __version__
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.auth import AuthMode, Identity
from fastapi_cloud_cli.utils.errors import ErrorToolkit

from ._errors import (
    StreamLogError,
    TooManyRetriesError,
    get_http_error_code,
    get_http_error_hint,
    handle_http_error,
)
from ._models import (
    TERMINAL_STATUSES,
    AppLogEntry,
    BuildLogAdapter,
    BuildLogLine,
    CustomDomain,
    CustomDomainsAPIResponse,
    DeploymentStatus,
)
from ._retry import (
    STREAM_LOGS_MAX_RETRIES,
    STREAM_LOGS_TIMEOUT,
    attempt,
    attempts,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
POLL_TIMEOUT = timedelta(seconds=120)
POLL_MAX_RETRIES = 5


def _get_user_agent() -> str:
    user_agent = f"fastapi-cloud-cli/{__version__}"

    if detection := detect_agent(minimum_confidence="high"):
        user_agent = f"{user_agent} AI-Agent/{detection.agent}"

    return user_agent


class APIClient(httpx.Client):
    auth_mode: AuthMode

    def __init__(self, use_deploy_token: bool = False) -> None:
        settings = Settings.get()
        identity = Identity()

        token: str | None
        if use_deploy_token and identity.deploy_token:
            token = identity.deploy_token
            self.auth_mode = "token"
        else:
            token = identity.user_token
            self.auth_mode = "user"

        headers = {"User-Agent": _get_user_agent()}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        super().__init__(
            base_url=settings.base_api_url,
            timeout=httpx.Timeout(20),
            headers=headers,
        )

    @contextmanager
    def handle_http_errors(
        self,
        progress: Progress,
        default_message: str | None = None,
        *,
        not_found_message: str | None = None,
        toolkit: ErrorToolkit | None = None,
    ) -> Generator[None, None, None]:
        # TODO: Once every command supports JSON output, require toolkit here
        # and let it be the single human/JSON error rendering boundary.

        mode = toolkit.mode if toolkit else "human"

        try:
            yield
        except httpx.ReadTimeout as e:
            logger.debug(e)

            message = (
                "The request to the FastAPI Cloud server timed out."
                " Please try again later."
            )

            if mode == "json" and toolkit:
                toolkit.fail(
                    "network_error",
                    message,
                    hint="Please try again later.",
                )

            progress.set_error(message)

            raise typer.Exit(1) from None  # pragma: no cover
        except httpx.HTTPError as e:
            logger.debug(e)

            message = handle_http_error(
                e,
                default_message,
                not_found_message=not_found_message,
                auth_mode=self.auth_mode,
            )
            code = get_http_error_code(e)

            if mode == "json" and toolkit:
                toolkit.fail(
                    code,
                    message,
                    hint=get_http_error_hint(code, auth_mode=self.auth_mode),
                )
            else:
                progress.set_error(message)

            raise typer.Exit(1) from None

    def get_custom_domains(self, *, app_id: str) -> CustomDomainsAPIResponse:
        response = self.get(f"/apps/{app_id}/custom-domains")
        response.raise_for_status()

        return CustomDomainsAPIResponse.model_validate(response.json())

    def create_custom_domain(
        self,
        *,
        app_id: str,
        name: str,
        is_using_pre_validation: bool,
    ) -> CustomDomain:
        response = self.post(
            f"/apps/{app_id}/custom-domains",
            json={
                "name": name,
                "is_using_pre_validation": is_using_pre_validation,
            },
        )
        response.raise_for_status()

        return CustomDomain.model_validate(response.json())

    def remove_custom_domain(self, *, app_id: str, domain_id: str) -> None:
        response = self.delete(f"/apps/{app_id}/custom-domains/{domain_id}")
        response.raise_for_status()

    def restart_custom_domain_setup(
        self,
        *,
        app_id: str,
        domain_id: str,
    ) -> CustomDomain:
        response = self.post(f"/apps/{app_id}/custom-domains/{domain_id}/restart-setup")
        response.raise_for_status()

        return CustomDomain.model_validate(response.json())

    @attempts(STREAM_LOGS_MAX_RETRIES, STREAM_LOGS_TIMEOUT)
    def stream_build_logs(
        self, deployment_id: str, *, follow: bool = True
    ) -> Generator[BuildLogLine, None, None]:
        last_id = None

        while True:
            params = {"last_id": last_id} if last_id else None

            with self.stream(
                "GET",
                f"/deployments/{deployment_id}/build-logs",
                timeout=60,
                params=params,
            ) as response:
                if response.is_error:
                    # Load the body while the stream is open so error handlers
                    # can surface the server's error detail.
                    response.read()
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line or not line.strip():
                        continue

                    if log_line := self._parse_log_line(line):
                        if log_line.id:
                            last_id = log_line.id

                        if log_line.type == "message":
                            yield log_line

                        if log_line.type in ("complete", "failed"):
                            yield log_line
                            return

                        if log_line.type == "timeout":
                            logger.debug("Received timeout; reconnecting")
                            if not follow:
                                return
                            break  # Breaks for loop to reconnect
                else:
                    if not follow:
                        return

                    logger.debug("Connection closed by server unexpectedly; will retry")

                    raise httpx.NetworkError("Connection closed without terminal state")

            time.sleep(0.5)

    def _parse_log_line(self, line: str) -> BuildLogLine | None:
        try:
            return BuildLogAdapter.validate_json(line)
        except (ValidationError, json.JSONDecodeError) as e:
            logger.debug("Skipping malformed log: %s (error: %s)", line[:100], e)
            return None

    @attempts(STREAM_LOGS_MAX_RETRIES, STREAM_LOGS_TIMEOUT)
    def stream_app_logs(
        self,
        app_id: str,
        tail: int,
        since: str,
        follow: bool,
    ) -> Generator[AppLogEntry, None, None]:
        timeout = 120 if follow else 30
        with self.stream(
            "GET",
            f"/apps/{app_id}/logs/stream",
            params={
                "tail": tail,
                "since": since,
                "follow": follow,
            },
            timeout=timeout,
        ) as response:
            if response.is_error:
                # Load the body while the stream is open so error handlers
                # can surface the server's error detail.
                response.read()
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.strip():  # pragma: no cover
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Failed to parse log line: %s", line)
                    continue

                if data.get("type") == "heartbeat":
                    continue

                if data.get("type") == "error":
                    raise StreamLogError(data.get("message", "Unknown error"))

                try:
                    yield AppLogEntry.model_validate(data)
                except ValidationError as e:  # pragma: no cover
                    logger.debug("Failed to parse log entry: %s - %s", data, e)
                    continue

    def poll_deployment_status(
        self,
        deployment_id: str,
    ) -> DeploymentStatus:
        start = time.monotonic()
        error_count = 0

        while True:
            if time.monotonic() - start > POLL_TIMEOUT.total_seconds():
                raise TimeoutError("Deployment verification timed out")

            with attempt(error_count):
                response = self.get(f"/deployments/{deployment_id}")
                response.raise_for_status()
                status = DeploymentStatus(response.json()["status"])
                error_count = 0

                if status in TERMINAL_STATUSES:
                    return status

                time.sleep(POLL_INTERVAL)
                continue

            error_count += 1
            if error_count >= POLL_MAX_RETRIES:
                raise TooManyRetriesError(
                    f"Failed after {POLL_MAX_RETRIES} attempts polling deployment status"
                )
