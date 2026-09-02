from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient, CustomDomain
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.domains._app import domains_app
from fastapi_cloud_cli.commands.domains._shared import (
    _find_custom_domain,
    _select_custom_domain,
)
from fastapi_cloud_cli.commands.domains.rendering import render_custom_domain_details
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class CustomDomainGetOutput(BaseModel):
    app_id: str
    domain: CustomDomain
    show_title: Annotated[bool, Field(exclude=True)] = True


def _render_custom_domain_get_output(
    data: CustomDomainGetOutput,
    toolkit: RichToolkit,
) -> None:
    if data.show_title:
        toolkit.print_title("custom domains")
        toolkit.print_line()

    render_custom_domain_details(data.domain, toolkit)


@domains_app.command("get", cls=UserCommand)
def get_domain(
    ctx: typer.Context,
    domain: Annotated[
        str | None,
        typer.Argument(
            help="Hostname or ID of the custom domain to return.",
        ),
    ] = None,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app that owns the custom domain.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get a custom domain for an app.
    """
    toolkit = get_user_command_context(ctx).toolkit
    app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)
    domain_was_provided = domain is not None

    if domain is None and toolkit.mode == "json":
        toolkit.fail(
            "missing_required_input",
            "Custom domain is required.",
            hint="Pass DOMAIN to choose a custom domain.",
        )

    with APIClient() as client:
        with (
            toolkit.progress(
                title="Fetching custom domains",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error fetching custom domains. Please try again later."
                ),
                not_found_message="App not found.",
                toolkit=toolkit,
            ),
        ):
            domains = client.get_custom_domains(app_id=app_id).data

    selected_domain: CustomDomain | None

    if domain is None:
        toolkit.print_title("custom domains")
        toolkit.print_line()

        if not domains:
            toolkit.print("No custom domains found.", bullet=False)
            return

        selected_domain = _select_custom_domain(
            toolkit,
            domains,
            prompt="Select the custom domain to get:",
        )
        toolkit.print_line()
    else:
        if (selected_domain := _find_custom_domain(domains, domain)) is None:
            toolkit.fail(
                "not_found",
                f"Custom domain {domain} not found.",
                hint=(
                    "Run `fastapi cloud domains list` to see available custom domains."
                ),
            )

    assert selected_domain is not None

    toolkit.success(
        CustomDomainGetOutput(
            app_id=app_id,
            domain=selected_domain,
            show_title=domain_was_provided,
        ),
        render_output=_render_custom_domain_get_output,
    )
