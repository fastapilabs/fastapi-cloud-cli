from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient, CustomDomain
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.domains._app import domains_app
from fastapi_cloud_cli.commands.domains._shared import (
    _find_custom_domain,
    _select_custom_domain,
)
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class CustomDomainRemoveOutput(BaseModel):
    app_id: str
    domain_id: str
    name: str
    removed: bool = True


def _render_custom_domain_remove_output(
    data: CustomDomainRemoveOutput,
    toolkit: RichToolkit,
) -> None:
    toolkit.print(f"Removed [bold]{data.name}[/bold]", emoji="🐔")


def _print_removal_warning(toolkit: RichToolkit, domain: CustomDomain) -> None:
    toolkit.print(
        f"FastAPI Cloud resources for [bold]{domain.name}[/bold] will be removed. "
        "DNS records at your provider will not be changed.",
        emoji="⚠️",
    )


@domains_app.command("remove", cls=UserCommand)
def remove_domain(
    ctx: typer.Context,
    domain: Annotated[
        str | None,
        typer.Argument(
            help="Hostname or ID of the custom domain to remove.",
        ),
    ] = None,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app that owns the custom domain.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm removal without prompting.",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Remove a custom domain from an app.

    DNS records at your provider are not changed.
    """
    toolkit = get_user_command_context(ctx).toolkit
    app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

    if toolkit.mode == "json":
        if domain is None:
            toolkit.fail(
                "missing_required_input",
                "Custom domain is required.",
                hint="Pass DOMAIN to choose a custom domain.",
            )
        if not yes:
            toolkit.fail(
                "missing_required_input",
                "Removal confirmation is required.",
                hint="Pass --yes to confirm removal.",
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

        toolkit.print_title("custom domains")
        toolkit.print_line()

        selected_domain: CustomDomain | None
        if domain is None:
            if not domains:
                toolkit.print("No custom domains found.", bullet=False)
                return

            selected_domain = _select_custom_domain(
                toolkit,
                domains,
                prompt="Select the custom domain to remove:",
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
        _print_removal_warning(toolkit, selected_domain)

        if not yes:
            toolkit.print_line()
            should_remove = toolkit.confirm(
                f"Remove [bold]{selected_domain.name}[/bold]?",
                default=False,
                bullet=False,
            )
            if not should_remove:
                toolkit.print_line()
                toolkit.print("Removal cancelled.", bullet=False)
                raise typer.Exit(0)

        toolkit.print_line()
        with (
            toolkit.progress(
                title="Removing custom domain",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error removing custom domain. Please try again later."
                ),
                not_found_message="Custom domain not found.",
                toolkit=toolkit,
            ),
        ):
            client.remove_custom_domain(
                app_id=app_id,
                domain_id=selected_domain.id,
            )

    toolkit.success(
        CustomDomainRemoveOutput(
            app_id=app_id,
            domain_id=selected_domain.id,
            name=selected_domain.name,
        ),
        render_output=_render_custom_domain_remove_output,
    )
