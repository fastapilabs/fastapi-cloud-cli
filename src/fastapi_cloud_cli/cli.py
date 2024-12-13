from types import TracebackType
from typing import Callable, Optional, Type

import sentry_sdk
import typer
from sentry_sdk.integrations import Integration
from sentry_sdk.utils import (
    capture_internal_exceptions,
    event_from_exception,
)

from .commands.deploy import deploy
from .commands.env import env_app
from .commands.login import login
from .commands.whoami import whoami

ExceptionHandler = Callable[
    [Type[BaseException], BaseException, Optional[TracebackType]], None
]


def _make_excepthook(
    old_excepthook: ExceptionHandler,
) -> ExceptionHandler:
    def sentry_sdk_excepthook(
        exc_type: Type[BaseException],
        exc_value: BaseException,
        tb: Optional[TracebackType],
    ) -> None:
        integration = sentry_sdk.get_client().get_integration(TyperIntegration)

        if integration is None:
            return old_excepthook(exc_type, exc_value, tb)

        with capture_internal_exceptions():
            event, hint = event_from_exception(
                (exc_type, exc_value, tb),
                client_options=sentry_sdk.get_client().options,
                mechanism={"type": "excepthook", "handled": False},
            )
            sentry_sdk.capture_event(event, hint=hint)

        return old_excepthook(exc_type, exc_value, tb)

    return sentry_sdk_excepthook


def patch_typer() -> None:
    typer.main.except_hook = _make_excepthook(typer.main.except_hook)  # type: ignore


class TyperIntegration(Integration):
    identifier = "typer"

    @staticmethod
    def setup_once() -> None:
        patch_typer()


sentry_sdk.init(
    dsn="https://230250605ea4b58a0b69c768e9ec1168@o4506985151856640.ingest.us.sentry.io/4508449198899200",
    traces_sample_rate=1.0,
    integrations=[TyperIntegration()],
)


app = typer.Typer()


# TODO: use the app structure

# Additional commands
app.command()(deploy)
app.command()(login)
app.command()(whoami)

app.add_typer(env_app, name="env")


def main() -> None:
    app()
