import string

from rich_toolkit.menu import Option

from fastapi_cloud_cli.api import CustomDomain
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit


def _normalize_domain_name(name: str) -> str:
    return name.strip(string.whitespace + ".").lower()


def _find_custom_domain(
    domains: list[CustomDomain],
    name_or_id: str,
) -> CustomDomain | None:
    normalized = _normalize_domain_name(name_or_id)

    return next(
        (
            domain
            for domain in domains
            if domain.id.lower() == normalized
            or _normalize_domain_name(domain.name) == normalized
        ),
        None,
    )


def _select_custom_domain(
    toolkit: FastAPIRichToolkit,
    domains: list[CustomDomain],
    *,
    prompt: str,
) -> CustomDomain:
    return toolkit.ask(
        prompt,
        options=[Option({"name": domain.name, "value": domain}) for domain in domains],
        bullet=False,
    )
