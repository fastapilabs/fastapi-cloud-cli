from pathlib import Path
from unittest.mock import ANY, patch

from fastapi_cloud_cli.utils.sentry import SENTRY_DSN, init_sentry


def test_init_sentry_when_logged_in(logged_in_cli: Path) -> None:
    with patch("fastapi_cloud_cli.utils.sentry.sentry_sdk.init") as mock_init:
        init_sentry()

        mock_init.assert_called_once_with(
            dsn=SENTRY_DSN,
            integrations=[ANY],  # TyperIntegration instance
            send_default_pii=False,
        )


def test_init_sentry_when_logged_out(logged_out_cli: Path) -> None:
    with patch("fastapi_cloud_cli.utils.sentry.sentry_sdk.init") as mock_init:
        init_sentry()

        mock_init.assert_not_called()
