from dataclasses import dataclass

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import (
    CustomDomain,
    CustomDomainRecord,
    CustomDomainStatus,
)
from fastapi_cloud_cli.commands.domains._setup import (
    ATTENTION_STATUSES,
    SetupStep,
    StepStatus,
    get_setup_steps,
)
from fastapi_cloud_cli.utils.cli import get_details_table
from fastapi_cloud_cli.utils.dates import format_last_updated


@dataclass(frozen=True)
class DomainStatusMetadata:
    label: str
    title: str
    description: str


DOMAIN_STATUS: dict[CustomDomainStatus, DomainStatusMetadata] = {
    CustomDomainStatus.internal_dcv_pending: DomainStatusMetadata(
        label="Pending",
        title="Waiting domain verification",
        description=(
            "We are checking your DNS configuration to confirm domain ownership. "
            "This usually takes a few minutes."
        ),
    ),
    CustomDomainStatus.internal_dcv_missing: DomainStatusMetadata(
        label="Pending",
        title="Waiting domain verification",
        description=(
            "Your domain is missing the required DNS records. Add the records "
            "shown below to continue verification."
        ),
    ),
    CustomDomainStatus.internal_dcv_invalid: DomainStatusMetadata(
        label="Needs attention",
        title="Verification needed",
        description=(
            "The DNS records were found but don't match the expected values. "
            "Double-check your provider settings."
        ),
    ),
    CustomDomainStatus.internal_dcv_timeout: DomainStatusMetadata(
        label="Domain verification timed out",
        title="Restart domain verification",
        description=(
            "We couldn't verify the domain in time, it's possible the DNS changes "
            "may still be propagating. Please restart the domain verification process."
        ),
    ),
    CustomDomainStatus.internal_dcv_revoked: DomainStatusMetadata(
        label="Domain verification revoked",
        title="Verification needed",
        description=(
            "Domain ownership could no longer be verified. This may happen if DNS "
            "records were removed or changed."
        ),
    ),
    CustomDomainStatus.external_dcv_pending: DomainStatusMetadata(
        label="Setting up domain",
        title="Issuing certificates",
        description=(
            "Your domain is being configured and a TLS certificate is being requested."
        ),
    ),
    CustomDomainStatus.external_dcv_proxied: DomainStatusMetadata(
        label="Domain active, securing TLS",
        title="Issuing certificates",
        description=(
            "Traffic is being routed correctly. We're finalizing TLS certificate issuance."
        ),
    ),
    CustomDomainStatus.external_dcv_secured: DomainStatusMetadata(
        label="TLS certificate issued",
        title="Issuing certificates",
        description=(
            "A TLS certificate has been issued and is being applied to your domain."
        ),
    ),
    CustomDomainStatus.external_dcv_blocked: DomainStatusMetadata(
        label="Domain blocked by provider",
        title="Verification needed",
        description=(
            "This domain has been restricted and domain verification cannot proceed. "
            "Please contact support for more information."
        ),
    ),
    CustomDomainStatus.external_dcv_timeout: DomainStatusMetadata(
        label="Domain setup timed out",
        title="Restart domain verification",
        description=(
            "The domain setup took too long to complete. This is often caused by slow "
            "DNS propagation. Please restart the domain verification process."
        ),
    ),
    CustomDomainStatus.origin_setup_pending: DomainStatusMetadata(
        label="Validating",
        title="Validating DNS records",
        description=(
            "Add the following records to your authoritative DNS server to start "
            "sending traffic to your app."
        ),
    ),
    CustomDomainStatus.origin_setup_missing: DomainStatusMetadata(
        label="Missing",
        title="DNS records missing",
        description=(
            "Your domain is missing required DNS records. Add the records shown below "
            "to your authoritative DNS server."
        ),
    ),
    CustomDomainStatus.origin_setup_invalid: DomainStatusMetadata(
        label="Needs attention",
        title="DNS records invalid",
        description=(
            "The DNS records were found but don't match the expected values. "
            "Double-check your DNS records."
        ),
    ),
    CustomDomainStatus.origin_setup_timeout: DomainStatusMetadata(
        label="Timeout",
        title="Restart domain setup",
        description=(
            "The domain setup couldn't be validated in time. Please restart the "
            "domain setup process."
        ),
    ),
    CustomDomainStatus.origin_setup_success: DomainStatusMetadata(
        label="Live",
        title="Live",
        description=(
            "Your domain is fully configured, secured with TLS, and set up to route "
            "traffic to your app."
        ),
    ),
    CustomDomainStatus.origin_setup_removed: DomainStatusMetadata(
        label="Removed",
        title="DNS records removed",
        description=(
            "The required DNS records were removed after being valid. Your domain is "
            "no longer active and needs to be set up again."
        ),
    ),
}


def get_setup_mode_label(domain: CustomDomain) -> str:
    if domain.is_using_pre_validation:
        return "Zero-downtime"

    return "Standard"


def get_custom_domains_table(domains: list[CustomDomain]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Domain", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Setup mode", no_wrap=True)
    table.add_column("Last check", no_wrap=True)
    table.add_row(
        Text("Domain", style="bold"),
        Text("Status", style="bold"),
        Text("Setup mode", style="bold"),
        Text("Last check", style="bold"),
    )
    table.add_row("", "", "", "")

    for domain in domains:
        table.add_row(
            Text(domain.name),
            Text(DOMAIN_STATUS[domain.status].label),
            Text(get_setup_mode_label(domain)),
            Text(format_last_updated(domain.setup_checked_at), style="dim"),
        )

    return table


STEP_LABELS: dict[StepStatus, str] = {
    "verified": "Verified",
    "in_progress": "In progress",
    "attention": "Needs attention",
    "locked": "Locked",
    "failed": "Action needed",
}


def _get_dns_records_table(records: list[CustomDomainRecord]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Type", no_wrap=True)
    table.add_column("Name", overflow="fold")
    table.add_column("Value", overflow="fold")
    table.add_row(
        Text("Type", style="bold"),
        Text("Name", style="bold"),
        Text("Value", style="bold"),
    )

    generating = Text("Generating; check again shortly", style="dim italic")
    for record in records:
        table.add_row(
            Text(record.type),
            Text(record.name) if record.name is not None else generating,
            Text(record.value) if record.value is not None else generating,
        )

    return table


def _render_setup_step(
    step: SetupStep,
    toolkit: RichToolkit,
    *,
    number: int,
) -> None:
    toolkit.print(
        f"[bold]{number}  {step.title}[/bold]  [dim]{STEP_LABELS[step.status]}[/dim]",
        bullet=False,
    )
    toolkit.print(step.description, bullet=False)

    records = step.records if step.status != "locked" else []
    if not records:
        return

    toolkit.print_line()
    toolkit.print(_get_dns_records_table(records), bullet=False)

    if any(
        record.type == "CNAME" and (record.value or "").endswith(".")
        for record in records
    ):
        toolkit.print_line()
        toolkit.print(
            "Copy CNAME values as shown. If your DNS provider rejects the trailing "
            "dot, remove it and try again.",
            emoji="💡",
        )

    if step.status != "verified" and any(
        record.type in {"CNAME", "A"} for record in records
    ):
        toolkit.print_line()
        toolkit.print(
            "Using Cloudflare? Set these records to DNS only (gray cloud), not "
            "Proxied (orange cloud).",
            emoji="💡",
        )


def _get_next_action(domain: CustomDomain) -> str:
    if domain.setup_successful:
        return "No action needed. Your domain is live."
    if domain.setup_failed:
        return (
            "Correct the DNS records, then run "
            f"`fastapi cloud domains restart {domain.name}`."
        )
    if domain.status in ATTENTION_STATUSES:
        return "Correct the DNS records shown. We'll check again automatically."
    return (
        "Wait for automatic verification. DNS changes can take up to 48 hours "
        "to propagate."
    )


def render_custom_domain_details(
    domain: CustomDomain,
    toolkit: RichToolkit,
) -> None:
    metadata = DOMAIN_STATUS[domain.status]
    rows: list[tuple[str, RenderableType]] = [
        ("hostname", domain.name),
        ("status", metadata.label),
        ("raw status", domain.status.value),
        ("setup mode", get_setup_mode_label(domain)),
        ("id", domain.id),
        ("created", format_last_updated(domain.created_at)),
        ("updated", format_last_updated(domain.updated_at)),
        ("setup started", format_last_updated(domain.setup_started_at)),
        ("last checked", format_last_updated(domain.setup_checked_at)),
    ]
    if domain.setup_successful:
        url = f"https://{domain.name}"
        rows.insert(1, ("url", Text(url, style=f"link {url}")))

    toolkit.print(Text(domain.name, style="bold"), emoji="🌐")
    toolkit.print_line()
    toolkit.print(get_details_table(rows))
    toolkit.print_line()
    toolkit.print(f"[bold]{metadata.title}[/bold]\n{metadata.description}")

    for number, step in enumerate(get_setup_steps(domain), start=1):
        toolkit.print_line()
        _render_setup_step(step, toolkit, number=number)

    toolkit.print_line()
    toolkit.print(_get_next_action(domain), emoji="⏳")
