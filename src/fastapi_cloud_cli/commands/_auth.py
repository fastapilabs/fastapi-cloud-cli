from dataclasses import dataclass
from typing import Any, cast

from typer._click import Context
from typer.core import TyperCommand

from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit

_CONTEXT_KEY = "fastapi_cloud_cli.user_command"


@dataclass(frozen=True)
class UserCommandContext:
    toolkit: FastAPIRichToolkit
    identity: Identity


def get_user_command_context(ctx: Context) -> UserCommandContext:
    return cast(UserCommandContext, ctx.meta[_CONTEXT_KEY])


class UserCommand(TyperCommand):
    def invoke(self, ctx: Context) -> Any:
        json_output = bool(ctx.params.get("json_output", False))

        with get_rich_toolkit(json_output=json_output) as toolkit:
            identity = Identity()

            if not identity.is_logged_in():
                toolkit.fail(
                    "not_logged_in",
                    "No credentials found.",
                    hint="Run `fastapi cloud login`.",
                )

            ctx.meta[_CONTEXT_KEY] = UserCommandContext(
                toolkit=toolkit,
                identity=identity,
            )
            return super().invoke(ctx)
