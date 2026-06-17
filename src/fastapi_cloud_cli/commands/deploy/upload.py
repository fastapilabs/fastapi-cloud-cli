import logging
from pathlib import Path
from typing import BinaryIO, cast

from httpx import Client
from pydantic import BaseModel
from rich_toolkit.progress import Progress

from fastapi_cloud_cli.commands.deploy.cloud import CreateDeploymentResponse
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.progress_file import ProgressFile

logger = logging.getLogger(__name__)


class RequestUploadResponse(BaseModel):
    url: str
    fields: dict[str, str]


def _cancel_upload(client: APIClient, deployment_id: str) -> None:
    logger.debug("Cancelling upload for deployment: %s", deployment_id)

    try:
        response = client.post(f"/deployments/{deployment_id}/upload-cancelled")
        response.raise_for_status()

        logger.debug("Upload cancellation notification sent successfully")
    except Exception as e:
        logger.debug("Failed to notify server about upload cancellation: %s", e)


def _format_size(size_in_bytes: int) -> str:
    if size_in_bytes >= 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"
    elif size_in_bytes >= 1024:
        return f"{size_in_bytes / 1024:.2f} KB"
    else:
        return f"{size_in_bytes} bytes"


def _upload_deployment(
    fastapi_client: APIClient,
    deployment_id: str,
    archive_path: Path,
    progress: Progress,
) -> CreateDeploymentResponse:
    archive_size = archive_path.stat().st_size
    archive_size_str = _format_size(archive_size)

    progress.log(f"Uploading deployment ({archive_size_str})...")
    logger.debug(
        "Starting deployment upload for deployment: %s",
        deployment_id,
    )
    logger.debug("Archive path: %s, size: %s bytes", archive_path, archive_size)

    def progress_callback(bytes_read: int) -> None:
        progress.log(
            f"Uploading deployment ({_format_size(bytes_read)} of {archive_size_str})..."
        )

    logger.debug("Requesting upload URL from API")
    response = fastapi_client.post(f"/deployments/{deployment_id}/upload")
    response.raise_for_status()

    upload_data = RequestUploadResponse.model_validate(response.json())
    logger.debug("Received upload URL: %s", upload_data.url)

    logger.debug("Starting file upload to S3")
    with Client() as s3_client:
        with open(archive_path, "rb") as archive_file:
            archive_file_with_progress = ProgressFile(
                archive_file, progress_callback=progress_callback
            )
            upload_response = s3_client.post(
                upload_data.url,
                data=upload_data.fields,
                files={"file": cast(BinaryIO, archive_file_with_progress)},
            )

    upload_response.raise_for_status()
    logger.debug("File upload completed successfully")

    logger.debug("Notifying API that upload is complete")
    notify_response = fastapi_client.post(
        f"/deployments/{deployment_id}/upload-complete"
    )

    notify_response.raise_for_status()
    logger.debug("Upload notification sent successfully")

    return CreateDeploymentResponse.model_validate(notify_response.json())
