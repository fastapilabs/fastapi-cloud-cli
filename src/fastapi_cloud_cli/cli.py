# Import decorated callbacks so they register themselves with their Typer apps.
from fastapi_cloud_cli._app import app as app
from fastapi_cloud_cli._app import cloud_app as cloud_app
from fastapi_cloud_cli.commands.apps._app import apps_app
from fastapi_cloud_cli.commands.apps.create import create_app as create_app
from fastapi_cloud_cli.commands.apps.get import get_app as get_app
from fastapi_cloud_cli.commands.apps.link import link_app as link_app
from fastapi_cloud_cli.commands.apps.list import list_apps as list_apps
from fastapi_cloud_cli.commands.apps.unlink import unlink_app as unlink_app
from fastapi_cloud_cli.commands.apps.update import update_app as update_app
from fastapi_cloud_cli.commands.auth._app import auth_app
from fastapi_cloud_cli.commands.auth.wait import wait as wait
from fastapi_cloud_cli.commands.ci._app import ci_app
from fastapi_cloud_cli.commands.ci.print_workflow import (
    print_workflow as print_workflow,
)
from fastapi_cloud_cli.commands.deploy.command import deploy as deploy
from fastapi_cloud_cli.commands.deployments import deployments_app
from fastapi_cloud_cli.commands.domains._app import domains_app
from fastapi_cloud_cli.commands.domains.add import add_domain as add_domain
from fastapi_cloud_cli.commands.domains.get import get_domain as get_domain
from fastapi_cloud_cli.commands.domains.list import list_domains as list_domains
from fastapi_cloud_cli.commands.domains.remove import remove_domain as remove_domain
from fastapi_cloud_cli.commands.domains.restart import restart_domain as restart_domain
from fastapi_cloud_cli.commands.env._app import env_app
from fastapi_cloud_cli.commands.env.delete import delete as delete
from fastapi_cloud_cli.commands.env.get import get_variable as get_variable
from fastapi_cloud_cli.commands.env.list import list_variables as list_variables
from fastapi_cloud_cli.commands.env.set import set as set
from fastapi_cloud_cli.commands.integrations import integrations_app
from fastapi_cloud_cli.commands.integrations.providers.list import (
    list_providers as list_providers,
)
from fastapi_cloud_cli.commands.integrations.resources.connect import (
    connect_resource as connect_resource,
)
from fastapi_cloud_cli.commands.integrations.resources.disconnect import (
    disconnect_resource as disconnect_resource,
)
from fastapi_cloud_cli.commands.integrations.resources.get import (
    get_resource as get_resource,
)
from fastapi_cloud_cli.commands.integrations.resources.list import (
    list_resources as list_resources,
)
from fastapi_cloud_cli.commands.login import login as login
from fastapi_cloud_cli.commands.logout import logout as logout
from fastapi_cloud_cli.commands.logs import logs as logs
from fastapi_cloud_cli.commands.setup_ci import setup_ci as setup_ci
from fastapi_cloud_cli.commands.teams._app import teams_app
from fastapi_cloud_cli.commands.teams.get import get_team as get_team
from fastapi_cloud_cli.commands.teams.list import list_teams as list_teams
from fastapi_cloud_cli.commands.tokens._app import tokens_app
from fastapi_cloud_cli.commands.tokens.create import create_token as create_token
from fastapi_cloud_cli.commands.tokens.delete import delete_token as delete_token
from fastapi_cloud_cli.commands.tokens.list import list_tokens as list_tokens
from fastapi_cloud_cli.commands.whoami import whoami as whoami
from fastapi_cloud_cli.logging import setup_logging
from fastapi_cloud_cli.utils.sentry import init_sentry

setup_logging()

cloud_app.add_typer(env_app, name="env")
cloud_app.add_typer(auth_app, name="auth")
cloud_app.add_typer(apps_app, name="apps")
cloud_app.add_typer(ci_app, name="ci")
cloud_app.add_typer(deployments_app, name="deployments")
cloud_app.add_typer(domains_app, name="domains")
cloud_app.add_typer(integrations_app, name="integrations")
cloud_app.add_typer(teams_app, name="teams")
cloud_app.add_typer(tokens_app, name="tokens")

app.add_typer(cloud_app, name="cloud")


def main() -> None:
    init_sentry()
    app()
