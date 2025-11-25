import contextlib
import logging
import subprocess
import tempfile
import time
from enum import Enum
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import fastar
import rignore
import typer
from httpx import Client
from pydantic import BaseModel, EmailStr, ValidationError
from rich.text import Text
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option
from typing_extensions import Annotated

from fastapi_cloud_cli.commands.login import login
from fastapi_cloud_cli.utils.api import APIClient, BuildLogError, TooManyRetriesError
from fastapi_cloud_cli.utils.apps import AppConfig, get_app_config, write_app_config
from fastapi_cloud_cli.utils.auth import is_logged_in
from fastapi_cloud_cli.utils.cli import get_rich_toolkit, handle_http_errors
from fastapi_cloud_cli.utils.pydantic_compat import (
    TypeAdapter,
    model_dump,
    model_validate,
)

logger = logging.getLogger(__name__)


def _get_app_name(path: Path) -> str:
    # TODO: use pyproject.toml to get the app name
    return path.name


def _should_exclude_entry(path: Path) -> bool:
    parts_to_exclude = [
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".gitignore",
        ".fastapicloudignore",
    ]

    if any(part in path.parts for part in parts_to_exclude):
        return True

    if path.suffix == ".pyc":
        return True

    return False


def archive(path: Path, tar_path: Path) -> Path:
    logger.debug("Starting archive creation for path: %s", path)
    files = rignore.walk(
        path,
        should_exclude_entry=_should_exclude_entry,
        additional_ignore_paths=[".fastapicloudignore"],
        ignore_hidden=False,
    )

    logger.debug("Archive will be created at: %s", tar_path)

    file_count = 0
    with fastar.open(tar_path, "w") as tar:
        for filename in files:
            if filename.is_dir():
                continue

            arcname = filename.relative_to(path)
            logger.debug("Adding %s to archive", arcname)
            tar.append(filename, arcname=arcname)
            file_count += 1

    logger.debug("Archive created successfully with %s files", file_count)
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

    return [model_validate(Team, team) for team in data]


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

        return model_validate(AppResponse, response.json())


class DeploymentStatus(str, Enum):
    waiting_upload = "waiting_upload"
    ready_for_build = "ready_for_build"
    building = "building"
    extracting = "extracting"
    extracting_failed = "extracting_failed"
    building_image = "building_image"
    building_image_failed = "building_image_failed"
    deploying = "deploying"
    deploying_failed = "deploying_failed"
    verifying = "verifying"
    verifying_failed = "verifying_failed"
    verifying_skipped = "verifying_skipped"
    success = "success"
    failed = "failed"

    @classmethod
    def to_human_readable(cls, status: "DeploymentStatus") -> str:
        return {
            cls.waiting_upload: "Waiting for upload",
            cls.ready_for_build: "Ready for build",
            cls.building: "Building",
            cls.extracting: "Extracting",
            cls.extracting_failed: "Extracting failed",
            cls.building_image: "Building image",
            cls.building_image_failed: "Build failed",
            cls.deploying: "Deploying",
            cls.deploying_failed: "Deploying failed",
            cls.verifying: "Verifying",
            cls.verifying_failed: "Verifying failed",
            cls.verifying_skipped: "Verification skipped",
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

        return model_validate(CreateDeploymentResponse, response.json())


class RequestUploadResponse(BaseModel):
    url: str
    fields: Dict[str, str]


def _upload_deployment(deployment_id: str, archive_path: Path) -> None:
    logger.debug(
        "Starting deployment upload for deployment: %s",
        deployment_id,
    )
    logger.debug(
        "Archive path: %s, size: %s bytes",
        archive_path,
        archive_path.stat().st_size,
    )

    with APIClient() as fastapi_client, Client() as client:
        # Get the upload URL
        logger.debug("Requesting upload URL from API")
        response = fastapi_client.post(f"/deployments/{deployment_id}/upload")
        response.raise_for_status()

        upload_data = model_validate(RequestUploadResponse, response.json())
        logger.debug("Received upload URL: %s", upload_data.url)

        logger.debug("Starting file upload to S3")
        with open(archive_path, "rb") as archive_file:
            upload_response = client.post(
                upload_data.url,
                data=upload_data.fields,
                files={"file": archive_file},
            )

        upload_response.raise_for_status()
        logger.debug("File upload completed successfully")

        # Notify the server that the upload is complete
        logger.debug("Notifying API that upload is complete")
        notify_response = fastapi_client.post(
            f"/deployments/{deployment_id}/upload-complete"
        )

        notify_response.raise_for_status()
        logger.debug("Upload notification sent successfully")


def _get_app(app_slug: str) -> Optional[AppResponse]:
    with APIClient() as client:
        response = client.get(f"/apps/{app_slug}")

        if response.status_code == 404:
            return None

        response.raise_for_status()

        data = response.json()

    return model_validate(AppResponse, data)


def _get_apps(team_id: str) -> List[AppResponse]:
    with APIClient() as client:
        response = client.get("/apps/", params={"team_id": team_id})
        response.raise_for_status()

        data = response.json()["data"]

    return [model_validate(AppResponse, app) for app in data]


WAITING_MESSAGES = [
    "🚀 Preparing for liftoff! Almost there...",
    "👹 Sneaking past the dependency gremlins... Don't wake them up!",
    "🤏 Squishing code into a tiny digital sandwich. Nom nom nom.",
    "🐱 Removing cat videos from our servers to free up space.",
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
    ) as progress, APIClient() as client:
        try:
            for log in client.stream_build_logs(deployment.id):
                time_elapsed = time.monotonic() - started_at

                if log.type == "message":
                    progress.log(Text.from_ansi(log.message.rstrip()))

                if log.type == "complete":
                    progress.log("")
                    progress.log(
                        f"🐔 Ready the chicken! Your app is ready at [link={deployment.url}]{deployment.url}[/link]"
                    )

                    progress.log("")

                    progress.log(
                        f"You can also check the app logs at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
                    )

                    break

                if log.type == "failed":
                    progress.log("")
                    progress.log(
                        f"😔 Oh no! Something went wrong. Check out the logs at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
                    )
                    raise typer.Exit(1)

                if time_elapsed > 30:
                    messages = cycle(LONG_WAIT_MESSAGES)

                if (time.monotonic() - last_message_changed_at) > 2:
                    progress.title = next(messages)

                    last_message_changed_at = time.monotonic()

        except (BuildLogError, TooManyRetriesError) as e:
            logger.error("Build log streaming failed: %s", e)
            toolkit.print_line()
            toolkit.print(
                f"⚠️  Unable to stream build logs. Check the dashboard for status: [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
            )
            raise typer.Exit(1) from e


class SignupToWaitingList(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    organization: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[str] = None
    location: Optional[str] = None
    use_case: Optional[str] = None
    secret_code: Optional[str] = None


def _send_waitlist_form(
    result: SignupToWaitingList,
    toolkit: RichToolkit,
) -> None:
    with toolkit.progress("Sending your request...") as progress:
        with APIClient() as client:
            with handle_http_errors(progress):
                response = client.post("/users/waiting-list", json=model_dump(result))

                response.raise_for_status()

        progress.log("Let's go! Thanks for your interest in FastAPI Cloud! 🚀")


def _waitlist_form(toolkit: RichToolkit) -> None:
    from rich_toolkit.form import Form

    toolkit.print(
        "We're currently in private beta. If you want to be notified when we launch, please fill out the form below.",
        tag="waitlist",
    )

    toolkit.print_line()

    email = toolkit.input(
        "Enter your email:",
        required=True,
        validator=TypeAdapter(EmailStr),
    )

    toolkit.print_line()

    result = model_validate(SignupToWaitingList, {"email": email})

    if toolkit.confirm(
        "Do you want to get access faster by giving us more information?",
        tag="waitlist",
    ):
        toolkit.print_line()
        form = Form("Waitlist form", style=toolkit.style)

        form.add_input("name", label="Name", placeholder="John Doe")
        form.add_input("organization", label="Organization", placeholder="Acme Inc.")
        form.add_input("team", label="Team", placeholder="Team A")
        form.add_input("role", label="Role", placeholder="Developer")
        form.add_input("location", label="Location", placeholder="San Francisco")
        form.add_input(
            "use_case",
            label="How do you plan to use FastAPI Cloud?",
            placeholder="I'm building a web app",
        )
        form.add_input("secret_code", label="Secret code", placeholder="123456")

        result = form.run()  # type: ignore

        try:
            result = model_validate(
                SignupToWaitingList,
                {
                    "email": email,
                    **result,  # type: ignore
                },
            )
        except ValidationError:
            toolkit.print(
                "[error]Invalid form data. Please try again.[/]",
            )

            return

    toolkit.print_line()

    if toolkit.confirm(
        (
            "Do you agree to\n"
            "- Terms of Service: [link=https://fastapicloud.com/legal/terms]https://fastapicloud.com/legal/terms[/link]\n"
            "- Privacy Policy: [link=https://fastapicloud.com/legal/privacy-policy]https://fastapicloud.com/legal/privacy-policy[/link]\n"
        ),
        tag="terms",
    ):
        toolkit.print_line()

        _send_waitlist_form(
            result,
            toolkit,
        )

        with contextlib.suppress(Exception):
            subprocess.run(
                ["open", "-g", "raycast://confetti?emojis=🐔⚡"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


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
    logger.debug("Deploy command started")
    logger.debug("Deploy path: %s, skip_wait: %s", path, skip_wait)

    with get_rich_toolkit() as toolkit:
        if not is_logged_in():
            logger.debug("User not logged in, prompting for login or waitlist")

            toolkit.print_title("Welcome to FastAPI Cloud!", tag="FastAPI")
            toolkit.print_line()

            toolkit.print(
                "You need to be logged in to deploy to FastAPI Cloud.",
                tag="info",
            )
            toolkit.print_line()

            choice = toolkit.ask(
                "What would you like to do?",
                tag="auth",
                options=[
                    Option({"name": "Login to my existing account", "value": "login"}),
                    Option({"name": "Join the waiting list", "value": "waitlist"}),
                ],
            )

            toolkit.print_line()

            if choice == "login":
                login()
            else:
                _waitlist_form(toolkit)
                raise typer.Exit(1)

        toolkit.print_title("Starting deployment", tag="FastAPI")
        toolkit.print_line()

        path_to_deploy = path or Path.cwd()
        logger.debug("Deploying from path: %s", path_to_deploy)

        app_config = get_app_config(path_to_deploy)

        if not app_config:
            logger.debug("No app config found, configuring new app")
            app_config = _configure_app(toolkit, path_to_deploy=path_to_deploy)
            toolkit.print_line()
        else:
            logger.debug("Existing app config found, proceeding with deployment")
            toolkit.print("Deploying app...")
            toolkit.print_line()

        with toolkit.progress("Checking app...", transient=True) as progress:
            with handle_http_errors(progress):
                logger.debug("Checking app with ID: %s", app_config.app_id)
                app = _get_app(app_config.app_id)

            if not app:
                logger.debug("App not found in API")
                progress.set_error(
                    "App not found. Make sure you're logged in the correct account."
                )

        if not app:
            toolkit.print_line()
            toolkit.print(
                "If you deleted this app, you can run [bold]fastapi cloud unlink[/] to unlink the local configuration.",
                tag="tip",
            )
            raise typer.Exit(1)

        with tempfile.TemporaryDirectory() as temp_dir:
            logger.debug("Creating archive for deployment")
            archive_path = Path(temp_dir) / "archive.tar"
            archive(path or Path.cwd(), archive_path)

            with toolkit.progress(
                title="Creating deployment"
            ) as progress, handle_http_errors(progress):
                logger.debug("Creating deployment for app: %s", app.id)
                deployment = _create_deployment(app.id)

                progress.log(
                    f"Deployment created successfully! Deployment slug: {deployment.slug}"
                )

                progress.log("Uploading deployment...")

                _upload_deployment(deployment.id, archive_path)

                progress.log("Deployment uploaded successfully!")

        toolkit.print_line()

        if not skip_wait:
            logger.debug("Waiting for deployment to complete")
            _wait_for_deployment(toolkit, app.id, deployment=deployment)
        else:
            logger.debug("Skipping deployment wait as requested")
            toolkit.print(
                f"Check the status of your deployment at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
            )
