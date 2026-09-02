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


class CustomDomainRestartOutput(BaseModel):
    app_id: str
    domain: CustomDomain
    show_title: Annotated[bool, Field(exclude=True)] = True


def _render_custom_domain_restart_output(
    data: CustomDomainRestartOutput,
    toolkit: RichToolkit,
) -> None:
    if data.show_title:
        toolkit.print_title("custom domains")
        toolkit.print_line()

    toolkit.print(
        f"Restarted verification for [bold]{data.domain.name}[/bold]",
        emoji="🐔",
    )
    toolkit.print_line()
    render_custom_domain_details(data.domain, toolkit)
    toolkit.print_line()
    toolkit.print(
        "[dim]hint: Run `fastapi cloud domains get "
        f"{data.domain.name}` to check progress.[/dim]"
    )


@domains_app.command("restart", cls=UserCommand)
def restart_domain(
    ctx: typer.Context,
    domain: Annotated[
        str | None,
        typer.Argument(
            help="Hostname or ID of the custom domain whose setup should restart.",
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
    Restart failed custom domain setup for an app.
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
            failed_domains = [domain for domain in domains if domain.setup_failed]

            if not failed_domains:
                toolkit.print("No failed custom domains found.", bullet=False)
                return

            selected_domain = _select_custom_domain(
                toolkit,
                failed_domains,
                prompt="Select the custom domain to restart:",
            )
            toolkit.print_line()
        else:
            selected_domain = _find_custom_domain(domains, domain)
            if selected_domain is None:
                toolkit.fail(
                    "not_found",
                    f"Custom domain {domain} not found.",
                    hint=(
                        "Run `fastapi cloud domains list` to see available "
                        "custom domains."
                    ),
                )

        assert selected_domain is not None
        with (
            toolkit.progress(
                title="Restarting custom domain setup",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error restarting custom domain setup. Please try again later."
                ),
                not_found_message="Custom domain not found.",
                toolkit=toolkit,
            ),
        ):
            restarted_domain = client.restart_custom_domain_setup(
                app_id=app_id,
                domain_id=selected_domain.id,
            )

    toolkit.success(
        CustomDomainRestartOutput(
            app_id=app_id,
            domain=restarted_domain,
            show_title=domain_was_provided,
        ),
        render_output=_render_custom_domain_restart_output,
    )
