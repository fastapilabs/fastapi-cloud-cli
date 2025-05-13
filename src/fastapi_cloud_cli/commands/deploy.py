import json
import logging
import tarfile
import tempfile
import time
import uuid
from enum import Enum
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union

import rignore
import typer
from httpx import Client
from pydantic import BaseModel
from rich.text import Text
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option
from typing_extensions import Annotated

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config, write_app_config
from fastapi_cloud_cli.utils.auth import is_logged_in
from fastapi_cloud_cli.utils.cli import get_rich_toolkit, handle_http_errors
from fastapi_cloud_cli.utils.env import validate_environment_variable_name

logger = logging.getLogger(__name__)


def _get_app_name(path: Path) -> str:
    # TODO: use pyproject.toml to get the app name
    return path.name


def _should_exclude_entry(path: Path) -> bool:
    if ".venv" in path.parts:
        return True

    if "__pycache__" in path.parts:
        return True

    if path.suffix == ".pyc":
        return True

    return False


def archive(path: Path) -> Path:
    files = rignore.walk(path, should_exclude_entry=_should_exclude_entry)

    temp_dir = tempfile.mkdtemp()

    name = f"fastapi-cloud-deploy-{uuid.uuid4()}"
    tar_path = Path(temp_dir) / f"{name}.tar"

    with tarfile.open(tar_path, "w") as tar:
        for filename in files:
            if filename.is_dir():
                continue

            tar.add(filename, arcname=filename.relative_to(path))

    return tar_path


class Team(BaseModel):
    id: str
    slug: str
    name: str


def _get_teams() -> List[Team]:
    with APIClient() as client:
        response = client.get("/teams/")
        response.raise_for_status()

        data = response.json()["data"]

    return [Team.model_validate(team) for team in data]


class AppResponse(BaseModel):
    id: str
    slug: str


def _create_app(team_id: str, app_name: str) -> AppResponse:
    with APIClient() as client:
        response = client.post(
            "/apps/",
            json={"name": app_name, "team_id": team_id},
        )

        response.raise_for_status()

        return AppResponse.model_validate(response.json())


class DeploymentStatus(str, Enum):
    waiting_upload = "waiting_upload"
    ready_for_build = "ready_for_build"
    building = "building"
    extracting = "extracting"
    building_image = "building_image"
    deploying = "deploying"
    success = "success"
    failed = "failed"

    @classmethod
    def to_human_readable(cls, status: "DeploymentStatus") -> str:
        return {
            cls.waiting_upload: "Waiting for upload",
            cls.ready_for_build: "Ready for build",
            cls.building: "Building",
            cls.extracting: "Extracting",
            cls.building_image: "Building image",
            cls.deploying: "Deploying",
            cls.success: "Success",
            cls.failed: "Failed",
        }[status]


class CreateDeploymentResponse(BaseModel):
    id: str
    app_id: str
    slug: str
    status: DeploymentStatus
    dashboard_url: str
    url: str


def _create_deployment(app_id: str) -> CreateDeploymentResponse:
    with APIClient() as client:
        response = client.post(f"/apps/{app_id}/deployments/")
        response.raise_for_status()

        return CreateDeploymentResponse.model_validate(response.json())


class RequestUploadResponse(BaseModel):
    url: str
    fields: Dict[str, str]


def _upload_deployment(deployment_id: str, archive_path: Path) -> None:
    with APIClient() as fastapi_client, Client() as client:
        # Get the upload URL
        response = fastapi_client.post(f"/deployments/{deployment_id}/upload")
        response.raise_for_status()

        upload_data = RequestUploadResponse.model_validate(response.json())

        # Upload the archive
        upload_response = client.post(
            upload_data.url,
            data=upload_data.fields,
            files={"file": archive_path.open("rb")},
        )

        upload_response.raise_for_status()

        # Notify the server that the upload is complete
        notify_response = fastapi_client.post(
            f"/deployments/{deployment_id}/upload-complete"
        )

        notify_response.raise_for_status()


def _get_app(app_slug: str) -> Optional[AppResponse]:
    with APIClient() as client:
        response = client.get(f"/apps/{app_slug}")

        if response.status_code == 404:
            return None

        response.raise_for_status()

        data = response.json()

    return AppResponse.model_validate(data)


def _get_apps(team_id: str) -> List[AppResponse]:
    with APIClient() as client:
        response = client.get("/apps/", params={"team_id": team_id})
        response.raise_for_status()

        data = response.json()["data"]

    return [AppResponse.model_validate(app) for app in data]


def _create_environment_variables(app_id: str, env_vars: Dict[str, str]) -> None:
    with APIClient() as client:
        response = client.patch(f"/apps/{app_id}/environment-variables/", json=env_vars)
        response.raise_for_status()


def _stream_build_logs(deployment_id: str) -> Generator[str, None, None]:
    with APIClient() as client:
        with client.stream(
            "GET", f"/deployments/{deployment_id}/build-logs", timeout=60
        ) as response:
            response.raise_for_status()

            yield from response.iter_lines()


WAITING_MESSAGES = [
    "🚀 Preparing for liftoff! Almost there...",
    "👹 Sneaking past the dependency gremlins... Don't wake them up!",
    "🤏 Squishing code into a tiny digital sandwich. Nom nom nom.",
    "📉 Server space running low. Time to delete those cat videos?",
    "🐢 Uploading at blazing speeds of 1 byte per hour. Patience, young padawan.",
    "🔌 Connecting to server... Please stand by while we argue with the firewall.",
    "💥 Oops! We've angered the Python God. Sacrificing a rubber duck to appease it.",
    "🧙 Sprinkling magic deployment dust. Abracadabra!",
    "👀 Hoping that @tiangolo doesn't find out about this deployment.",
    "🍪 Cookie monster detected on server. Deploying anti-cookie shields.",
]

LONG_WAIT_MESSAGES = [
    "😅 Well, that's embarrassing. We're still waiting for the deployment to finish...",
    "🤔 Maybe we should have brought snacks for this wait...",
    "🥱 Yawn... Still waiting...",
    "🤯 Time is relative... Especially when you're waiting for a deployment...",
]


def _configure_app(toolkit: RichToolkit, path_to_deploy: Path) -> AppConfig:
    if not toolkit.confirm(f"Setup and deploy [blue]{path_to_deploy}[/]?", tag="dir"):
        raise typer.Exit(0)

    toolkit.print_line()

    with toolkit.progress("Fetching teams...") as progress:
        with handle_http_errors(
            progress, message="Error fetching teams. Please try again later."
        ):
            teams = _get_teams()

    toolkit.print_line()

    team = toolkit.ask(
        "Select the team you want to deploy to:",
        tag="team",
        options=[Option({"name": team.name, "value": team}) for team in teams],
    )

    toolkit.print_line()

    create_new_app = toolkit.confirm(
        "Do you want to create a new app?", tag="app", default=True
    )

    toolkit.print_line()

    if not create_new_app:
        with toolkit.progress("Fetching apps...") as progress:
            with handle_http_errors(
                progress, message="Error fetching apps. Please try again later."
            ):
                apps = _get_apps(team.id)

        toolkit.print_line()

        if not apps:
            toolkit.print(
                "No apps found in this team. You can create a new app instead.",
            )

            raise typer.Exit(1)

        app = toolkit.ask(
            "Select the app you want to deploy to:",
            options=[Option({"name": app.slug, "value": app}) for app in apps],
        )
    else:
        app_name = toolkit.input(
            title="What's your app name?",
            default=_get_app_name(path_to_deploy),
        )

        toolkit.print_line()

        with toolkit.progress(title="Creating app...") as progress:
            with handle_http_errors(progress):
                app = _create_app(team.id, app_name)

            progress.log(f"App created successfully! App slug: {app.slug}")

    app_config = AppConfig(app_id=app.id, team_id=team.id)

    write_app_config(path_to_deploy, app_config)

    return app_config


def _wait_for_deployment(
    toolkit: RichToolkit, app_id: str, deployment: CreateDeploymentResponse
) -> None:
    messages = cycle(WAITING_MESSAGES)

    toolkit.print(
        "Checking the status of your deployment 👀",
        tag="cloud",
    )
    toolkit.print_line()

    toolkit.print(
        f"You can also check the status at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]",
    )
    toolkit.print_line()

    time_elapsed = 0.0

    started_at = time.monotonic()

    last_message_changed_at = time.monotonic()

    with toolkit.progress(
        next(messages), inline_logs=True, lines_to_show=20
    ) as progress:
        for line in _stream_build_logs(deployment.id):
            time_elapsed = time.monotonic() - started_at

            data = json.loads(line)

            if "message" in data:
                progress.log(Text.from_ansi(data["message"].rstrip()))

            if data.get("type") == "complete":
                progress.log("")
                progress.log(
                    f"🐔 Ready the chicken! Your app is ready at [link={deployment.url}]{deployment.url}[/link]"
                )
                break

            if time_elapsed > 30:
                messages = cycle(LONG_WAIT_MESSAGES)

            if (time.monotonic() - last_message_changed_at) > 2:
                progress.title = next(messages)

                last_message_changed_at = time.monotonic()


def _setup_environment_variables(toolkit: RichToolkit, app_id: str) -> None:
    if not toolkit.confirm("Do you want to setup environment variables?", tag="env"):
        return

    toolkit.print_line()

    env_vars = {}

    while True:
        key = toolkit.input(
            "Enter the environment variable name: [ENTER to skip]", required=False
        )

        if key.strip() == "":
            break

        if not validate_environment_variable_name(key):
            toolkit.print(
                "[error]Invalid environment variable name.",
            )

        else:
            value = toolkit.input(
                "Enter the environment variable value:", password=True
            )

            env_vars[key] = value

        toolkit.print_line()

    toolkit.print_line()

    with toolkit.progress("Setting up environment variables...") as progress:
        with handle_http_errors(progress):
            _create_environment_variables(app_id, env_vars)

        progress.log("Environment variables set up successfully!")


def deploy(
    path: Annotated[
        Union[Path, None],
        typer.Argument(
            help="A path to the folder containing the app you want to deploy"
        ),
    ] = None,
    skip_wait: Annotated[
        bool, typer.Option("--no-wait", help="Skip waiting for deployment status")
    ] = False,
) -> Any:
    """
    Deploy a [bold]FastAPI[/bold] app to FastAPI Cloud. 🚀
    """

    with get_rich_toolkit() as toolkit:
        toolkit.print_title("Starting deployment", tag="FastAPI")
        toolkit.print_line()

        if not is_logged_in():
            toolkit.print(
                "No credentials found. Use [blue]`fastapi login`[/] to login.",
                tag="auth",
            )

            raise typer.Exit(1)

        path_to_deploy = path or Path.cwd()

        app_config = get_app_config(path_to_deploy)

        if not app_config:
            app_config = _configure_app(toolkit, path_to_deploy=path_to_deploy)
            toolkit.print_line()

            _setup_environment_variables(toolkit, app_config.app_id)
            toolkit.print_line()
        else:
            toolkit.print("Deploying app...")
            toolkit.print_line()

        with toolkit.progress("Checking app...", transient=True) as progress:
            with handle_http_errors(progress):
                app = _get_app(app_config.app_id)

            if not app:
                progress.set_error(
                    "App not found. Make sure you're logged in the correct account."
                )

                raise typer.Exit(1)

        archive_path = archive(path or Path.cwd())  # noqa: F841

        with toolkit.progress(title="Creating deployment") as progress:
            with handle_http_errors(progress):
                deployment = _create_deployment(app.id)

                progress.log(
                    f"Deployment created successfully! Deployment slug: {deployment.slug}"
                )

                progress.log("Uploading deployment...")

                _upload_deployment(deployment.id, archive_path)

            progress.log("Deployment uploaded successfully!")

        toolkit.print_line()

        if not skip_wait:
            _wait_for_deployment(toolkit, app.id, deployment=deployment)
        else:
            toolkit.print(
                f"Check the status of your deployment at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
            )
