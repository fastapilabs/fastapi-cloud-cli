from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option

from fastapi_cloud_cli.api import APIClient, CustomDomain
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.domains._app import domains_app
from fastapi_cloud_cli.commands.domains._shared import _normalize_domain_name
from fastapi_cloud_cli.commands.domains.rendering import render_custom_domain_setup
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class CustomDomainAddOutput(BaseModel):
    app_id: str
    domain: CustomDomain
    show_title: Annotated[bool, Field(exclude=True)] = True


def _resolve_domain_name(
    toolkit: FastAPIRichToolkit,
    *,
    domain: str | None,
) -> str:
    if domain is None:
        if toolkit.mode == "json":
            toolkit.fail(
                "missing_required_input",
                "Custom domain is required.",
                hint="Pass DOMAIN to choose the hostname to add.",
            )

        domain = toolkit.input(
            "What domain do you want to add?",
            emoji="🌐",
            bullet=False,
        )
        toolkit.print_line()

    return _normalize_domain_name(domain)


def _resolve_pre_validation(
    toolkit: FastAPIRichToolkit,
    *,
    domain: str,
    standard: bool,
    zero_downtime: bool,
) -> bool:
    if standard:
        return False
    if zero_downtime:
        return True
    if toolkit.mode == "json":
        toolkit.fail(
            "missing_required_input",
            "Custom domain setup mode is required.",
            hint="Pass either --standard or --zero-downtime.",
        )

    toolkit.print(f"Is {domain} already serving traffic?")
    toolkit.print_line()

    return toolkit.ask(
        "",
        options=[
            Option(
                {
                    "name": "No — set up a new or unused domain",
                    "value": False,
                }
            ),
            Option(
                {
                    "name": "Yes — migrate it without downtime",
                    "value": True,
                }
            ),
        ],
    )


def _render_custom_domain_add_output(
    data: CustomDomainAddOutput,
    toolkit: RichToolkit,
) -> None:
    if data.show_title:
        toolkit.print_title("custom domains")
        toolkit.print_line()

    toolkit.print(f"Added [bold]{data.domain.name}[/bold]", emoji="🐔")
    render_custom_domain_setup(data.domain, toolkit)


@domains_app.command("add", cls=UserCommand)
def add_domain(
    ctx: typer.Context,
    domain: Annotated[
        str | None,
        typer.Argument(
            help="Hostname of the custom domain to add.",
        ),
    ] = None,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app to which the custom domain should be added.",
        ),
    ] = None,
    standard: Annotated[
        bool,
        typer.Option(
            "--standard",
            help="Set up a new or unused domain.",
        ),
    ] = False,
    zero_downtime: Annotated[
        bool,
        typer.Option(
            "--zero-downtime",
            help="Migrate an already-live domain without downtime.",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Add a custom domain to an app.
    """
    toolkit = get_user_command_context(ctx).toolkit
    app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

    if standard and zero_downtime:
        toolkit.fail(
            "invalid_input",
            "Setup modes are mutually exclusive.",
            hint="Pass either --standard or --zero-downtime.",
        )

    prompts_user = domain is None or not (standard or zero_downtime)
    if prompts_user and toolkit.mode != "json":
        toolkit.print_title("custom domains")
        toolkit.print_line()

    domain = _resolve_domain_name(toolkit, domain=domain)
    is_using_pre_validation = _resolve_pre_validation(
        toolkit,
        domain=domain,
        standard=standard,
        zero_downtime=zero_downtime,
    )

    if prompts_user:
        toolkit.print_line()

    with APIClient() as client:
        with (
            toolkit.progress(
                title="Adding custom domain",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=("Error adding custom domain. Please try again later."),
                not_found_message="App not found.",
                toolkit=toolkit,
            ),
        ):
            created_domain = client.create_custom_domain(
                app_id=app_id,
                name=domain,
                is_using_pre_validation=is_using_pre_validation,
            )

    toolkit.success(
        CustomDomainAddOutput(
            app_id=app_id,
            domain=created_domain,
            show_title=not prompts_user,
        ),
        render_output=_render_custom_domain_add_output,
    )
