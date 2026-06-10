"""Google Drive API integration for uploading and sharing zip files.

Supports two authentication modes:

1. **OAuth2 (default)** — for personal Gmail accounts. The user authorizes
   once via browser; a refresh token is saved for subsequent uploads.
   Set ``GOOGLE_DRIVE_CLIENT_SECRETS_FILE`` and ``GOOGLE_DRIVE_FOLDER_ID``.

2. **Service account** — for Google Workspace with Shared Drives.
   Set ``GOOGLE_DRIVE_CREDENTIALS_FILE`` and ``GOOGLE_DRIVE_FOLDER_ID``.

The mode is selected automatically based on which settings are present.
If both are set, OAuth2 takes precedence.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_token_path() -> Path:
    """Return the path where the OAuth2 token is stored."""
    token_path = getattr(settings, "GOOGLE_DRIVE_TOKEN_FILE", "")
    if token_path:
        return Path(token_path).expanduser()
    # Default: next to the client secrets file
    secrets = Path(
        getattr(settings, "GOOGLE_DRIVE_CLIENT_SECRETS_FILE", "")
    ).expanduser()
    return secrets.parent / "google-drive-token.json"


def _get_oauth2_credentials():
    """Obtain OAuth2 user credentials, launching browser auth if needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = _get_token_path()
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        secrets_file = getattr(settings, "GOOGLE_DRIVE_CLIENT_SECRETS_FILE", "")
        if not secrets_file or not Path(secrets_file).expanduser().exists():
            raise FileNotFoundError(
                f"Google Drive client secrets file not found: {secrets_file}. "
                f"Set GOOGLE_DRIVE_CLIENT_SECRETS_FILE in settings. "
                f"See docs/google_drive_setup.md."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(Path(secrets_file).expanduser()), SCOPES
        )
        creds = flow.run_local_server(port=0)

    # Save token for next run
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    return creds


def _get_service_account_credentials():
    """Obtain service account credentials (for Shared Drives / Workspace)."""
    from google.oauth2 import service_account

    credentials_file = getattr(settings, "GOOGLE_DRIVE_CREDENTIALS_FILE", "")
    if not credentials_file or not Path(credentials_file).expanduser().exists():
        raise FileNotFoundError(
            f"Google Drive credentials file not found: {credentials_file}. "
            f"Set GOOGLE_DRIVE_CREDENTIALS_FILE in settings."
        )
    return service_account.Credentials.from_service_account_file(
        str(Path(credentials_file).expanduser()),
        scopes=SCOPES,
    )


def _get_drive_service():
    """Build and return a Google Drive API service instance.

    Uses OAuth2 if ``GOOGLE_DRIVE_CLIENT_SECRETS_FILE`` is configured,
    otherwise falls back to service account credentials.
    """
    from googleapiclient.discovery import build

    secrets_file = getattr(settings, "GOOGLE_DRIVE_CLIENT_SECRETS_FILE", "")
    sa_file = getattr(settings, "GOOGLE_DRIVE_CREDENTIALS_FILE", "")

    if secrets_file and Path(secrets_file).expanduser().exists():
        credentials = _get_oauth2_credentials()
    elif sa_file and Path(sa_file).expanduser().exists():
        credentials = _get_service_account_credentials()
    else:
        raise FileNotFoundError(
            "No Google Drive credentials configured. "
            "Set GOOGLE_DRIVE_CLIENT_SECRETS_FILE (OAuth2) or "
            "GOOGLE_DRIVE_CREDENTIALS_FILE (service account) in your .env file. "
            "See docs/google_drive_setup.md."
        )

    return build("drive", "v3", credentials=credentials)


def upload_to_drive(
    file_path: str,
    filename: str,
    folder_id: str | None = None,
    mime_type: str = "application/zip",
) -> str:
    """Upload a file to Google Drive and return a shareable download link.

    Args:
        file_path: Local path to the file to upload.
        filename: Name for the file in Google Drive.
        folder_id: Google Drive folder ID. Falls back to
            settings.GOOGLE_DRIVE_FOLDER_ID.
        mime_type: MIME type of the file.

    Returns:
        A direct download URL for the uploaded file.
    """
    from googleapiclient.http import MediaFileUpload

    service = _get_drive_service()
    target_folder = folder_id or getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", "")

    if not target_folder:
        raise ValueError(
            "No Google Drive folder ID configured. "
            "Set GOOGLE_DRIVE_FOLDER_ID in your .env file."
        )

    file_metadata: dict = {"name": filename, "parents": [target_folder]}

    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    result = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    file_id = result["id"]

    # Make the file readable by anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()

    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    logger.info("Uploaded %s to Google Drive: %s", filename, download_url)
    return download_url


def is_drive_configured() -> bool:
    """Return True if Google Drive settings are present and usable."""
    folder_id = getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", "")
    if not folder_id:
        return False

    # OAuth2 mode
    secrets_file = getattr(settings, "GOOGLE_DRIVE_CLIENT_SECRETS_FILE", "")
    if secrets_file and Path(secrets_file).expanduser().exists():
        return True

    # Service account mode
    sa_file = getattr(settings, "GOOGLE_DRIVE_CREDENTIALS_FILE", "")
    if sa_file and Path(sa_file).expanduser().exists():
        return True

    return False
