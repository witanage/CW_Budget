"""
Google Drive File Service

Handles all file operations with Google Drive for bill attachment storage.
Reuses the same OAuth 2.0 credentials as the backup service but targets a
separate folder (google_drive_bills_folder_id in app_settings).

- Upload files (bill images and PDFs)
- Download files
- Get file metadata
- Delete files
"""

import io
import logging
import os
import ssl
import tempfile
import threading
from typing import Dict, Optional, Tuple

from db import get_setting

logger = logging.getLogger(__name__)

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logger.warning("google-api-python-client or google-auth not installed. Google Drive file storage will be disabled.")

SCOPES = ['https://www.googleapis.com/auth/drive.file']

# MIME type mapping for bill attachments
MIME_TYPES = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'pdf': 'application/pdf',
}


class GoogleDriveFileService:
    """Service for managing bill attachment files in Google Drive."""

    # Max retries on transient connection/SSL errors
    _MAX_RETRIES = 2

    def __init__(self):
        self.folder_id = get_setting('google_drive_bills_folder_id')
        self._client_id = get_setting('google_drive_client_id')
        self._client_secret = get_setting('google_drive_client_secret')
        self._refresh_token = get_setting('google_drive_refresh_token')
        self._local = threading.local()

    def is_available(self) -> bool:
        """Check if Google Drive file storage is properly configured."""
        if not GOOGLE_DRIVE_AVAILABLE:
            return False
        if not self.folder_id:
            return False
        if not all([self._client_id, self._client_secret, self._refresh_token]):
            return False
        return True

    def _get_service(self):
        """Build and return a thread-local Google Drive API service."""
        service = getattr(self._local, 'service', None)
        if service is not None:
            return service

        creds = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            client_id=self._client_id,
            client_secret=self._client_secret,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=SCOPES,
        )
        creds.refresh(Request())

        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        self._local.service = service
        return service

    def _reset_service(self):
        """Discard cached service so the next call builds a fresh connection."""
        self._local.service = None

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        """Return True if the exception looks like a transient connection error."""
        if isinstance(exc, (ssl.SSLError, ConnectionError, OSError)):
            return True
        msg = str(exc).lower()
        return any(term in msg for term in (
            'ssl', 'record_layer_failure', 'connection reset',
            'broken pipe', 'timed out', 'eof occurred',
        ))

    def upload_file(self, file_data: bytes, file_id: str, filename: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Upload file to Google Drive bills folder.

        Args:
            file_data: The file content as bytes
            file_id: Ignored (Google Drive assigns its own ID). Kept for interface compatibility.
            filename: The filename (used for naming and MIME detection)

        Returns:
            Tuple of (success, error_message, result_info)
            - On success: (True, None, {'id': drive_file_id, 'sizeOriginal': size})
            - On failure: (False, error_message, None)
        """
        if not self.is_available():
            return False, "Google Drive file storage not configured", None

        try:
            last_exc = None
            for attempt in range(self._MAX_RETRIES + 1):
                try:
                    service = self._get_service()

                    # Detect MIME type from filename
                    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                    mime_type = MIME_TYPES.get(ext, 'application/octet-stream')

                    file_metadata = {
                        'name': filename,
                        'parents': [self.folder_id],
                    }

                    # Write to temp file for upload
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_path = os.path.join(tmp_dir, filename)
                        with open(tmp_path, 'wb') as f:
                            f.write(file_data)

                        media = MediaFileUpload(tmp_path, mimetype=mime_type, resumable=True)

                        result = service.files().create(
                            body=file_metadata,
                            media_body=media,
                            fields='id, name, size, mimeType',
                        ).execute()

                    drive_file_id = result.get('id')
                    file_size = result.get('size', str(len(file_data)))
                    logger.info(f"✓ File uploaded to Google Drive: {filename} (id={drive_file_id}, size={file_size} bytes)")

                    return True, None, {
                        'id': drive_file_id,
                        'sizeOriginal': int(file_size),
                    }
                except Exception as e:
                    last_exc = e
                    if self._is_transient(e) and attempt < self._MAX_RETRIES:
                        logger.warning(f"Transient error on upload (attempt {attempt + 1}), retrying: {e}")
                        self._reset_service()
                        continue
                    raise

        except Exception as e:
            error_msg = f"Failed to upload file to Google Drive: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg, None

    def download_file(self, file_id: str) -> Tuple[Optional[bytes], int, Optional[str]]:
        """
        Download file content from Google Drive.

        Args:
            file_id: The Google Drive file ID

        Returns:
            Tuple of (file_content, status_code, error_message)
            - On success: (bytes, 200, None)
            - On failure: (None, error_code, error_message)
        """
        if not self.is_available():
            return None, 500, "Google Drive file storage not configured"

        try:
            for attempt in range(self._MAX_RETRIES + 1):
                try:
                    service = self._get_service()
                    request = service.files().get_media(fileId=file_id)

                    buffer = io.BytesIO()
                    downloader = MediaIoBaseDownload(buffer, request)

                    done = False
                    while not done:
                        _, done = downloader.next_chunk()

                    file_content = buffer.getvalue()
                    logger.info(f"Successfully downloaded file {file_id}, size: {len(file_content)} bytes")
                    return file_content, 200, None
                except Exception as e:
                    if self._is_transient(e) and attempt < self._MAX_RETRIES:
                        logger.warning(f"Transient error on download (attempt {attempt + 1}), retrying: {e}")
                        self._reset_service()
                        continue
                    raise

        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            logger.error(f"{error_msg} for file {file_id}", exc_info=True)
            return None, 500, error_msg

    def get_file_metadata(self, file_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get file metadata (name and MIME type).

        Args:
            file_id: The Google Drive file ID

        Returns:
            Tuple of (file_name, mime_type), or (file_id, 'application/octet-stream') on failure
        """
        if not self.is_available():
            return file_id, 'application/octet-stream'

        try:
            for attempt in range(self._MAX_RETRIES + 1):
                try:
                    service = self._get_service()
                    result = service.files().get(
                        fileId=file_id,
                        fields='name, mimeType'
                    ).execute()

                    file_name = result.get('name', file_id)
                    mime_type = result.get('mimeType', 'application/octet-stream')
                    logger.info(f"Got metadata for {file_id}: {file_name}, mime: {mime_type}")
                    return file_name, mime_type
                except Exception as e:
                    if self._is_transient(e) and attempt < self._MAX_RETRIES:
                        logger.warning(f"Transient error on metadata (attempt {attempt + 1}), retrying: {e}")
                        self._reset_service()
                        continue
                    raise

        except Exception as e:
            logger.error(f"Failed to get metadata for {file_id}: {str(e)}", exc_info=True)
            return file_id, 'application/octet-stream'

    def delete_file(self, file_id: str) -> Tuple[bool, Optional[str]]:
        """
        Delete file from Google Drive.

        Args:
            file_id: The Google Drive file ID

        Returns:
            Tuple of (success, error_message)
            - On success: (True, None)
            - On failure: (False, error_message)
        """
        if not self.is_available():
            return False, "Google Drive file storage not configured"

        try:
            for attempt in range(self._MAX_RETRIES + 1):
                try:
                    service = self._get_service()
                    service.files().delete(fileId=file_id).execute()
                    logger.info(f"✓ File deleted from Google Drive: {file_id}")
                    return True, None
                except Exception as e:
                    if self._is_transient(e) and attempt < self._MAX_RETRIES:
                        logger.warning(f"Transient error on delete (attempt {attempt + 1}), retrying: {e}")
                        self._reset_service()
                        continue
                    raise

        except Exception as e:
            error_msg = f"Failed to delete file {file_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg


# Singleton
_google_drive_file_service = None


def get_google_drive_file_service() -> GoogleDriveFileService:
    """Get or create the singleton Google Drive file service instance."""
    global _google_drive_file_service
    if _google_drive_file_service is None:
        _google_drive_file_service = GoogleDriveFileService()
    return _google_drive_file_service


def reset_google_drive_file_service():
    """Discard the cached singleton so the next call re-reads credentials from DB."""
    global _google_drive_file_service
    _google_drive_file_service = None
