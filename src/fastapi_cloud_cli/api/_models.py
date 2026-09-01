from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class AppLogEntry(BaseModel):
    timestamp: str
    message: str
    level: str


class BuildLogLineGeneric(BaseModel):
    type: Literal["complete", "failed", "timeout", "heartbeat"]
    id: str | None = None


class BuildLogLineMessage(BaseModel):
    type: Literal["message"] = "message"
    message: str
    id: str | None = None


BuildLogLine = BuildLogLineMessage | BuildLogLineGeneric
BuildLogAdapter: TypeAdapter[BuildLogLine] = TypeAdapter(
    Annotated[BuildLogLine, Field(discriminator="type")]
)


class CustomDomainStatus(str, Enum):
    internal_dcv_pending = "internal_dcv_pending"
    internal_dcv_missing = "internal_dcv_missing"
    internal_dcv_invalid = "internal_dcv_invalid"
    internal_dcv_timeout = "internal_dcv_timeout"
    internal_dcv_revoked = "internal_dcv_revoked"
    external_dcv_pending = "external_dcv_pending"
    external_dcv_proxied = "external_dcv_proxied"
    external_dcv_secured = "external_dcv_secured"
    external_dcv_blocked = "external_dcv_blocked"
    external_dcv_timeout = "external_dcv_timeout"
    origin_setup_pending = "origin_setup_pending"
    origin_setup_missing = "origin_setup_missing"
    origin_setup_invalid = "origin_setup_invalid"
    origin_setup_timeout = "origin_setup_timeout"
    origin_setup_success = "origin_setup_success"
    origin_setup_removed = "origin_setup_removed"


class CustomDomainRecord(BaseModel):
    type: Literal["TXT", "CNAME", "A"]
    name: str | None
    value: str | None


class CustomDomain(BaseModel):
    id: str
    name: str
    status: CustomDomainStatus
    setup_in_progress: bool
    setup_failed: bool
    setup_successful: bool
    is_using_pre_validation: bool
    dns_records: list[CustomDomainRecord]
    created_at: str
    updated_at: str
    setup_started_at: str | None
    setup_checked_at: str | None
    app_id: str


class CustomDomainsAPIResponse(BaseModel):
    data: list[CustomDomain]
    count: int


class DeploymentStatus(str, Enum):
    waiting_upload = "waiting_upload"
    upload_cancelled = "upload_cancelled"
    ready_for_build = "ready_for_build"
    building = "building"
    extracting = "extracting"
    extracting_failed = "extracting_failed"
    extracting_failed_archive_too_large = "extracting_failed_archive_too_large"
    building_image = "building_image"
    building_image_failed = "building_image_failed"
    building_image_failed_timeout = "building_image_failed_timeout"
    deploying = "deploying"
    deploying_skipped = "deploying_skipped"
    deploying_failed = "deploying_failed"
    verifying = "verifying"
    verifying_failed = "verifying_failed"
    verification_failed_oom = "verification_failed_oom"
    verifying_skipped = "verifying_skipped"
    success = "success"
    degraded_oom = "degraded_oom"
    degraded = "degraded"
    expired = "expired"
    failed = "failed"

    @classmethod
    def to_human_readable(cls, status: "DeploymentStatus") -> str:
        return {
            cls.waiting_upload: "Awaiting Upload",
            cls.upload_cancelled: "Upload Cancelled",
            cls.ready_for_build: "Build Queued",
            cls.building: "Building",
            cls.extracting: "Extracting Upload",
            cls.extracting_failed: "Extraction Failed",
            cls.extracting_failed_archive_too_large: "Archive Too Large",
            cls.building_image: "Building Image",
            cls.building_image_failed: "Build Failed",
            cls.building_image_failed_timeout: "Build Timed Out",
            cls.deploying: "Deploying Image",
            cls.deploying_skipped: "Deployment Skipped",
            cls.deploying_failed: "Deployment Failed",
            cls.verifying: "Verifying Readiness",
            cls.verifying_failed: "Verification Failed",
            cls.verification_failed_oom: "Verification Failed (OOM)",
            cls.verifying_skipped: "Verification Skipped",
            cls.success: "Ready",
            cls.degraded_oom: "Degraded (OOM)",
            cls.degraded: "Degraded",
            cls.expired: "Expired",
            cls.failed: "Failed",
        }[status]


SUCCESSFUL_STATUSES = {DeploymentStatus.success, DeploymentStatus.verifying_skipped}
FAILED_STATUSES = {
    DeploymentStatus.failed,
    DeploymentStatus.verifying_failed,
    DeploymentStatus.verification_failed_oom,
    DeploymentStatus.deploying_failed,
    DeploymentStatus.deploying_skipped,
    DeploymentStatus.building_image_failed,
    DeploymentStatus.building_image_failed_timeout,
    DeploymentStatus.extracting_failed,
    DeploymentStatus.extracting_failed_archive_too_large,
}
TERMINAL_STATUSES = SUCCESSFUL_STATUSES | FAILED_STATUSES
