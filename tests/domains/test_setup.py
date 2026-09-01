from typing import Any

import pytest

from fastapi_cloud_cli.api import CustomDomain, CustomDomainStatus
from fastapi_cloud_cli.commands.domains._setup import get_setup_steps

APP_ID = "00000000-0000-4000-8000-000000000002"
DOMAIN_ID = "00000000-0000-4000-8000-000000000003"

STANDARD_CNAME_RECORD = {
    "type": "CNAME",
    "name": "www",
    "value": f"{DOMAIN_ID}.endpoints.fastapicloud.dev.",
}
PRE_VALIDATION_RECORDS = [
    {"type": "TXT", "name": "_fc-dcv.www", "value": "ownership-value"},
    {"type": "TXT", "name": None, "value": None},
    {
        "type": "CNAME",
        "name": "_acme-challenge.www",
        "value": "certificate-value",
    },
    {"type": "A", "name": "@", "value": "192.0.2.10"},
    {"type": "CNAME", "name": "www", "value": "traffic-value"},
]


def _custom_domain(**overrides: Any) -> CustomDomain:
    return CustomDomain.model_validate(
        {
            "id": DOMAIN_ID,
            "name": "www.example.com",
            "status": CustomDomainStatus.internal_dcv_pending,
            "setup_in_progress": True,
            "setup_failed": False,
            "setup_successful": False,
            "is_using_pre_validation": False,
            "dns_records": [STANDARD_CNAME_RECORD],
            "created_at": "2026-08-28T10:00:00Z",
            "updated_at": "2026-08-28T10:01:00Z",
            "setup_started_at": "2026-08-28T10:00:00Z",
            "setup_checked_at": "2026-08-28T10:01:00Z",
            "app_id": APP_ID,
            **overrides,
        }
    )


@pytest.mark.parametrize(
    ("statuses", "expected_statuses"),
    [
        (
            (
                CustomDomainStatus.internal_dcv_pending,
                CustomDomainStatus.internal_dcv_missing,
            ),
            ("in_progress", "locked", "locked"),
        ),
        (
            (CustomDomainStatus.internal_dcv_invalid,),
            ("attention", "locked", "locked"),
        ),
        (
            (
                CustomDomainStatus.internal_dcv_timeout,
                CustomDomainStatus.internal_dcv_revoked,
            ),
            ("failed", "locked", "locked"),
        ),
        (
            (
                CustomDomainStatus.external_dcv_pending,
                CustomDomainStatus.external_dcv_proxied,
                CustomDomainStatus.external_dcv_secured,
            ),
            ("verified", "in_progress", "locked"),
        ),
        (
            (
                CustomDomainStatus.external_dcv_blocked,
                CustomDomainStatus.external_dcv_timeout,
            ),
            ("verified", "failed", "locked"),
        ),
        (
            (
                CustomDomainStatus.origin_setup_pending,
                CustomDomainStatus.origin_setup_missing,
            ),
            ("verified", "verified", "in_progress"),
        ),
        (
            (CustomDomainStatus.origin_setup_invalid,),
            ("verified", "verified", "attention"),
        ),
        (
            (
                CustomDomainStatus.origin_setup_timeout,
                CustomDomainStatus.origin_setup_removed,
            ),
            ("verified", "verified", "failed"),
        ),
        (
            (CustomDomainStatus.origin_setup_success,),
            ("verified", "verified", "verified"),
        ),
    ],
)
def test_pre_validation_setup_steps_follow_domain_phase(
    statuses: tuple[CustomDomainStatus, ...],
    expected_statuses: tuple[str, str, str],
) -> None:
    for status in statuses:
        steps = get_setup_steps(
            _custom_domain(
                status=status,
                is_using_pre_validation=True,
                dns_records=PRE_VALIDATION_RECORDS,
            )
        )

        assert tuple(step.status for step in steps) == expected_statuses
        assert [[record.name for record in step.records] for step in steps] == [
            ["_fc-dcv.www"],
            [None, "_acme-challenge.www"],
            ["@", "www"],
        ]


@pytest.mark.parametrize(
    ("overrides", "expected_status", "expected_description"),
    [
        (
            {},
            "in_progress",
            (
                "Add the record below. We'll verify ownership, issue your TLS "
                "certificate, and route traffic automatically."
            ),
        ),
        (
            {"dns_records": [{"type": "A", "name": "@", "value": "192.0.2.10"}]},
            "in_progress",
            (
                "Add the records below. We'll verify ownership, issue your TLS "
                "certificate, and route traffic automatically."
            ),
        ),
        (
            {"status": CustomDomainStatus.internal_dcv_invalid},
            "attention",
            (
                "We found your records, but some values don't match. Update them to "
                "the values below. We re-check automatically."
            ),
        ),
        (
            {
                "status": CustomDomainStatus.internal_dcv_timeout,
                "setup_in_progress": False,
                "setup_failed": True,
            },
            "failed",
            (
                "We couldn't complete setup. Re-check the records below, then restart "
                "verification."
            ),
        ),
        (
            {
                "status": CustomDomainStatus.origin_setup_success,
                "setup_in_progress": False,
                "setup_successful": True,
            },
            "verified",
            "Your domain is live on FastAPI Cloud.",
        ),
    ],
)
def test_standard_setup_step_reflects_domain_state(
    overrides: dict[str, Any],
    expected_status: str,
    expected_description: str,
) -> None:
    [step] = get_setup_steps(_custom_domain(**overrides))

    assert step.id == "combined"
    assert step.status == expected_status
    assert step.description == expected_description
