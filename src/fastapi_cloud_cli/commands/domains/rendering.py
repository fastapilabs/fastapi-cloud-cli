from dataclasses import dataclass

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
    get_setup_steps,
)
from fastapi_cloud_cli.utils.dates import format_last_updated


@dataclass(frozen=True)
class DomainStatusMetadata:
    label: str
    title: str
    description: str
    emoji: str = "⏳"


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
        emoji="⚠️",
    ),
    CustomDomainStatus.internal_dcv_timeout: DomainStatusMetadata(
        label="Domain verification timed out",
        title="Restart domain verification",
        description=(
            "We couldn't verify the domain in time, it's possible the DNS changes "
            "may still be propagating. Please restart the domain verification process."
        ),
        emoji="⚠️",
    ),
    CustomDomainStatus.internal_dcv_revoked: DomainStatusMetadata(
        label="Domain verification revoked",
        title="Verification needed",
        description=(
            "Domain ownership could no longer be verified. This may happen if DNS "
            "records were removed or changed."
        ),
        emoji="⚠️",
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
        emoji="⚠️",
    ),
    CustomDomainStatus.external_dcv_timeout: DomainStatusMetadata(
        label="Domain setup timed out",
        title="Restart domain verification",
        description=(
            "The domain setup took too long to complete. This is often caused by slow "
            "DNS propagation. Please restart the domain verification process."
        ),
        emoji="⚠️",
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
        emoji="⚠️",
    ),
    CustomDomainStatus.origin_setup_timeout: DomainStatusMetadata(
        label="Timeout",
        title="Restart domain setup",
        description=(
            "The domain setup couldn't be validated in time. Please restart the "
            "domain setup process."
        ),
        emoji="⚠️",
    ),
    CustomDomainStatus.origin_setup_success: DomainStatusMetadata(
        label="Live",
        title="Live",
        description=(
            "Your domain is fully configured, secured with TLS, and set up to route "
            "traffic to your app."
        ),
        emoji="✅",
    ),
    CustomDomainStatus.origin_setup_removed: DomainStatusMetadata(
        label="Removed",
        title="DNS records removed",
        description=(
            "The required DNS records were removed after being valid. Your domain is "
            "no longer active and needs to be set up again."
        ),
        emoji="⚠️",
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


STEP_NUMBER_EMOJIS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
}


def _get_dns_records_table(records: list[CustomDomainRecord]) -> Table:
    if len(records) == 1:
        record = records[0]
        generating = Text("Generating; check again shortly", style="dim italic")
        table = Table.grid(padding=(0, 2), pad_edge=False)
        table.add_column(style="dim", no_wrap=True)
        table.add_column(overflow="fold")
        table.add_row("type", record.type)
        table.add_row(
            "name",
            Text(record.name) if record.name is not None else generating,
        )
        table.add_row(
            "value",
            Text(record.value) if record.value is not None else generating,
        )
        return table

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


def _get_concise_step_description(
    step: SetupStep,
    records: list[CustomDomainRecord],
) -> str:
    if not records:
        return step.description

    records_label = (
        f"this {records[0].type} record" if len(records) == 1 else "these records"
    )
    if step.id == "combined":
        return (
            "[bold]To verify ownership and route traffic[/bold], add "
            f"{records_label} at your DNS provider:"
        )
    return f"Add {records_label} at your DNS provider:"


def _render_setup_step(
    step: SetupStep,
    toolkit: RichToolkit,
    *,
    number: int,
    show_number: bool,
) -> None:
    if step.status == "verified":
        toolkit.print(f"[bold]{step.title}[/bold]", emoji="✅")
        return

    records = step.records if step.status != "locked" else []
    hint_emoji = "" if show_number else "💡"

    if show_number:
        toolkit.print(
            f"[bold]{step.title}[/bold]",
            emoji=STEP_NUMBER_EMOJIS[number],
        )

    if step.status == "locked":
        return

    toolkit.print(_get_concise_step_description(step, records))

    if not records:
        return

    toolkit.print_line()
    toolkit.print(_get_dns_records_table(records))

    has_trailing_dot = any(
        record.type == "CNAME" and (record.value or "").endswith(".")
        for record in records
    )
    show_cloudflare_warning = any(record.type in {"CNAME", "A"} for record in records)

    if has_trailing_dot or show_cloudflare_warning:
        toolkit.print_line()

    if has_trailing_dot:
        toolkit.print(
            "Copy as shown; remove the trailing dot only if your provider rejects it.",
            emoji=hint_emoji,
        )
        hint_emoji = ""

    if show_cloudflare_warning:
        toolkit.print(
            "Cloudflare: use DNS only (gray cloud).",
            emoji=hint_emoji,
        )


def render_custom_domain_setup(
    domain: CustomDomain,
    toolkit: RichToolkit,
) -> None:
    steps = get_setup_steps(domain)
    show_number = len(steps) > 1
    for number, step in enumerate(steps, start=1):
        toolkit.print_line()
        _render_setup_step(
            step,
            toolkit,
            number=number,
            show_number=show_number,
        )


def _get_next_action(domain: CustomDomain) -> str | None:
    if domain.setup_failed:
        return (
            "Correct the DNS records, then run "
            f"`fastapi cloud domains restart {domain.name}`."
        )
    if domain.status in ATTENTION_STATUSES:
        return "Correct the DNS records shown. We'll check again automatically."
    return None


def render_custom_domain_details(
    domain: CustomDomain,
    toolkit: RichToolkit,
) -> None:
    if domain.setup_successful:
        url = f"https://{domain.name}"
        toolkit.print(Text(url, style=f"bold link {url}"), emoji="🌐")
        toolkit.print_line()
        toolkit.print("Your domain is live.", emoji="✅")
        return

    metadata = DOMAIN_STATUS[domain.status]
    toolkit.print(Text(domain.name, style="bold"), emoji="🌐")
    toolkit.print_line()
    toolkit.print(
        f"[bold]{metadata.title}[/bold]\n{metadata.description}",
        emoji=metadata.emoji,
    )
    render_custom_domain_setup(domain, toolkit)
    if next_action := _get_next_action(domain):
        toolkit.print_line()
        toolkit.print(next_action)
