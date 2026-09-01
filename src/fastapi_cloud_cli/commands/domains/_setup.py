from dataclasses import dataclass
from typing import Literal

from fastapi_cloud_cli.api import (
    CustomDomain,
    CustomDomainRecord,
    CustomDomainStatus,
)

StepStatus = Literal["verified", "in_progress", "attention", "locked", "failed"]
StepID = Literal["ownership", "certificate", "traffic", "combined"]
PhasedStepID = Literal["ownership", "certificate", "traffic"]
RecordGroup = PhasedStepID
Phase = Literal["internal", "external", "origin"]


@dataclass(frozen=True)
class SetupStep:
    id: StepID
    title: str
    description: str
    status: StepStatus
    records: list[CustomDomainRecord]


ATTENTION_STATUSES = frozenset(
    {
        CustomDomainStatus.internal_dcv_invalid,
        CustomDomainStatus.origin_setup_invalid,
    }
)

FAILED_STATUSES = frozenset(
    {
        CustomDomainStatus.internal_dcv_timeout,
        CustomDomainStatus.internal_dcv_revoked,
        CustomDomainStatus.external_dcv_blocked,
        CustomDomainStatus.external_dcv_timeout,
        CustomDomainStatus.origin_setup_timeout,
        CustomDomainStatus.origin_setup_removed,
    }
)

PHASE_ORDER: dict[Phase, int] = {
    "internal": 0,
    "external": 1,
    "origin": 2,
}


def _phase_from_status(status: CustomDomainStatus) -> Phase:
    if status.value.startswith("internal_dcv"):
        return "internal"
    if status.value.startswith("external_dcv"):
        return "external"
    return "origin"


def _record_group(record: CustomDomainRecord) -> RecordGroup:
    if record.type == "A":
        return "traffic"
    if record.type == "TXT":
        return "ownership" if "_fc-dcv" in (record.name or "") else "certificate"
    return "certificate" if "_acme-challenge" in (record.name or "") else "traffic"


def _step_status(status: CustomDomainStatus, phase: Phase) -> StepStatus:
    current_phase = PHASE_ORDER[_phase_from_status(status)]
    step_phase = PHASE_ORDER[phase]
    if current_phase > step_phase:
        return "verified"
    if current_phase < step_phase:
        return "locked"
    if status == CustomDomainStatus.origin_setup_success:
        return "verified"
    if status in ATTENTION_STATUSES:
        return "attention"
    if status in FAILED_STATUSES:
        return "failed"
    return "in_progress"


def _describe_step(
    step_id: StepID,
    status: StepStatus,
    *,
    is_apex: bool = False,
) -> str:
    if step_id == "ownership":
        if status == "attention":
            return (
                "We found this record, but its value doesn't match. Update it to "
                "the value below. We re-check every minute, no restart needed."
            )
        if status == "failed":
            return (
                "We couldn't confirm ownership. Re-check the value below, then "
                "restart verification."
            )
        if status == "verified":
            return "Ownership confirmed."
        return (
            "Add this TXT record. We check every minute and unlock the next step "
            "automatically."
        )

    if step_id == "certificate":
        if status == "locked":
            return "Unlocks once ownership is verified."
        if status == "failed":
            return (
                "We couldn't secure your domain. Re-check the records below, then "
                "restart verification."
            )
        if status == "verified":
            return "Domain verified and TLS certificate issued."
        return (
            "Add both records so we can issue your TLS certificate. Your live site "
            "doesn't change yet."
        )

    if step_id == "traffic":
        if status == "locked":
            return (
                "Unlocks once your domain is secured. Your live site won't change "
                "until you add the records here."
            )
        if status == "attention":
            return (
                "We found these records, but they don't match. Update them to the "
                "values below. We re-check automatically."
            )
        if status == "failed":
            return (
                "We couldn't confirm your traffic records. Re-check them below, then "
                "restart verification."
            )
        if status == "verified":
            return "Your domain is live on FastAPI Cloud."
        return "Add these records to move traffic to FastAPI Cloud with no downtime."

    if status == "attention":
        return (
            "We found your records, but some values don't match. Update them to the "
            "values below. We re-check automatically."
        )
    if status == "failed":
        return (
            "We couldn't complete setup. Re-check the records below, then restart "
            "verification."
        )
    if status == "verified":
        return "Your domain is live on FastAPI Cloud."
    if is_apex:
        return (
            "Add the records below. We'll verify ownership, issue your TLS "
            "certificate, and route traffic automatically."
        )
    return (
        "Add the record below. We'll verify ownership, issue your TLS certificate, "
        "and route traffic automatically."
    )


def get_setup_steps(domain: CustomDomain) -> list[SetupStep]:
    is_apex = any(record.type == "A" for record in domain.dns_records)

    if not domain.is_using_pre_validation:
        if domain.setup_successful:
            status: StepStatus = "verified"
        elif domain.setup_failed:
            status = "failed"
        elif domain.status in ATTENTION_STATUSES:
            status = "attention"
        else:
            status = "in_progress"

        return [
            SetupStep(
                id="combined",
                title="Verify ownership and route traffic",
                description=_describe_step("combined", status, is_apex=is_apex),
                status=status,
                records=domain.dns_records,
            )
        ]

    def records_for(group: RecordGroup) -> list[CustomDomainRecord]:
        return [
            record for record in domain.dns_records if _record_group(record) == group
        ]

    def build_step(
        step_id: PhasedStepID,
        title: str,
        phase: Phase,
    ) -> SetupStep:
        status = _step_status(domain.status, phase)
        return SetupStep(
            id=step_id,
            title=title,
            description=_describe_step(step_id, status),
            status=status,
            records=records_for(step_id),
        )

    return [
        build_step("ownership", "Prove ownership", "internal"),
        build_step("certificate", "Secure your domain", "external"),
        build_step("traffic", "Switch traffic", "origin"),
    ]
