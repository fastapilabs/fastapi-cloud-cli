import time
from itertools import cycle
from textwrap import dedent

import typer
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.deploy.cloud import CreateDeploymentResponse
from fastapi_cloud_cli.utils.api import (
    SUCCESSFUL_STATUSES,
    APIClient,
    DeploymentStatus,
    StreamLogError,
    TooManyRetriesError,
)

# (bullet emoji, message) — the emoji replaces the progress animation
WAITING_MESSAGES = [
    ("🚀", "Preparing for liftoff! Almost there..."),
    ("👹", "Sneaking past the dependency gremlins... Don't wake them up!"),
    ("🤏", "Squishing code into a tiny digital sandwich. Nom nom nom."),
    ("🐱", "Removing cat videos from our servers to free up space."),
    ("🐢", "Uploading at blazing speeds of 1 byte per hour. Patience, young padawan."),
    ("🔌", "Connecting to server... Please stand by while we argue with the firewall."),
    (
        "💥",
        "Oops! We've angered the Python God. Sacrificing a rubber duck to appease it.",
    ),
    ("🧙", "Sprinkling magic deployment dust. Abracadabra!"),
    ("👀", "Hoping that @tiangolo doesn't find out about this deployment."),
    ("🍪", "Cookie monster detected on server. Deploying anti-cookie shields."),
]

LONG_WAIT_MESSAGES = [
    (
        "😅",
        "Well, that's embarrassing. We're still waiting for the deployment to finish...",
    ),
    ("🤔", "Maybe we should have brought snacks for this wait..."),
    ("🥱", "Yawn... Still waiting..."),
    ("🤯", "Time is relative... Especially when you're waiting for a deployment..."),
]


def _verify_deployment(
    toolkit: RichToolkit,
    client: APIClient,
    app_id: str,
    deployment: CreateDeploymentResponse,
) -> None:
    failed_status: str | None = None

    with toolkit.progress(
        title="Verifying deployment...",
        inline_logs=True,
        done_emoji="✅",
    ) as progress:
        try:
            final_status = client.poll_deployment_status(app_id, deployment.id)
        except (TimeoutError, TooManyRetriesError, StreamLogError):
            progress.metadata["done_emoji"] = "⚠️"
            progress.current_message = (
                f"Could not confirm deployment status. "
                f"Check the dashboard: [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
            )
            return

        if final_status in SUCCESSFUL_STATUSES:
            progress.current_message = "Ready the chicken! 🐔"
        else:
            progress.metadata["done_emoji"] = "❌"
            progress.current_message = "Deployment failed"

            failed_status = DeploymentStatus.to_human_readable(final_status)

    if failed_status is not None:
        toolkit.print_line()
        toolkit.print(
            f"Oh no! Deployment failed: {failed_status}. "
            f"Check out the logs at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]",
            emoji="😔",
        )
        raise typer.Exit(1)

    toolkit.print_line()
    toolkit.print(
        f"Your app is ready at [link={deployment.url}]{deployment.url}[/link]"
    )


def _wait_for_deployment(
    toolkit: RichToolkit,
    client: APIClient,
    app_id: str,
    deployment: CreateDeploymentResponse,
) -> None:
    messages = cycle(WAITING_MESSAGES)

    time_elapsed = 0.0

    started_at = time.monotonic()

    last_message_changed_at = time.monotonic()

    with (
        toolkit.progress(
            "Checking the status of your deployment",
            inline_logs=True,
            lines_to_show=20,
            emoji="👀",
            done_emoji="🚀",
        ) as progress,
    ):
        build_complete = False
        build_failed = False

        try:
            for log in client.stream_build_logs(deployment.id):
                time_elapsed = time.monotonic() - started_at

                if log.type == "message":
                    progress.log(Text.from_ansi(log.message.rstrip()))  # ty: ignore[unresolved-attribute]

                if log.type == "complete":
                    build_complete = True
                    progress.title = "Build complete!"
                    break

                if log.type == "failed":
                    build_failed = True
                    # the headline comes from the title once there are log
                    # lines, and from current_message when there are none
                    progress.title = "Build failed"
                    progress.current_message = "Build failed"
                    progress.metadata["done_emoji"] = "❌"
                    break

                if time_elapsed > 30:
                    messages = cycle(LONG_WAIT_MESSAGES)

                if (time.monotonic() - last_message_changed_at) > 2:
                    emoji, title = next(messages)
                    progress.metadata["emoji"] = emoji
                    progress.title = title

                    last_message_changed_at = time.monotonic()

        except (StreamLogError, TooManyRetriesError, TimeoutError) as e:
            progress.set_error(
                dedent(f"""
                    [error]Build log streaming failed: {e}[/]

                    Unable to stream build logs. Check the dashboard for status: [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]
                    """).strip()
            )

            raise typer.Exit(1) from None

    if build_failed:
        toolkit.print_line()
        toolkit.print(
            f"Oh no! Something went wrong. Check out the logs at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]",
            emoji="😔",
        )
        raise typer.Exit(1)

    if build_complete:
        toolkit.print_line()

        _verify_deployment(
            toolkit=toolkit, client=client, app_id=app_id, deployment=deployment
        )
