"""Google Drive API integration for uploading and sharing zip files."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Build and return a Google Drive API service instance."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials_file = getattr(settings, "GOOGLE_DRIVE_CREDENTIALS_FILE", "")
    if not credentials_file or not Path(credentials_file).exists():
        raise FileNotFoundError(
            f"Google Drive credentials file not found: {credentials_file}. "
            f"Set GOOGLE_DRIVE_CREDENTIALS_FILE in settings."
        )

    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=["https://www.googleapis.com/auth/drive.file"],
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

    file_metadata: dict = {"name": filename}
    if target_folder:
        file_metadata["parents"] = [target_folder]

    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    result = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id,webViewLink")
        .execute()
    )
    file_id = result["id"]

    # Make the file readable by anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # Return a direct download link
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    logger.info("Uploaded %s to Google Drive: %s", filename, download_url)
    return download_url


def is_drive_configured() -> bool:
    """Return True if Google Drive settings are present."""
    credentials_file = getattr(settings, "GOOGLE_DRIVE_CREDENTIALS_FILE", "")
    folder_id = getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", "")
    return bool(credentials_file and folder_id and Path(credentials_file).exists())
