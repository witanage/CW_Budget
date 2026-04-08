"""
Google Drive Backup Service

Uploads database backup files to Google Drive using OAuth 2.0 credentials.
Requires:
  - GOOGLE_DRIVE_BACKUP_FOLDER_ID: Target folder ID in Google Drive
  - GOOGLE_DRIVE_CLIENT_ID: OAuth 2.0 Client ID
  - GOOGLE_DRIVE_CLIENT_SECRET: OAuth 2.0 Client Secret
  - GOOGLE_DRIVE_REFRESH_TOKEN: OAuth 2.0 Refresh Token (from one-time consent)
"""

import logging
import os

logger = logging.getLogger(__name__)

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logger.warning("google-api-python-client or google-auth not installed. Google Drive backup will be disabled.")

SCOPES = ['https://www.googleapis.com/auth/drive.file']


class GoogleDriveBackupService:
    """Service for uploading backup files to Google Drive."""

    def __init__(self):
        self.folder_id = os.environ.get('GOOGLE_DRIVE_BACKUP_FOLDER_ID')
        self._client_id = os.environ.get('GOOGLE_DRIVE_CLIENT_ID')
        self._client_secret = os.environ.get('GOOGLE_DRIVE_CLIENT_SECRET')
        self._refresh_token = os.environ.get('GOOGLE_DRIVE_REFRESH_TOKEN')
        self._service = None

    def is_available(self):
        """Check if Google Drive backup is properly configured."""
        if not GOOGLE_DRIVE_AVAILABLE:
            return False
        if not self.folder_id:
            return False
        if not all([self._client_id, self._client_secret, self._refresh_token]):
            return False
        return True

    def _get_service(self):
        """Build and cache the Google Drive API service."""
        if self._service is not None:
            return self._service

        creds = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            client_id=self._client_id,
            client_secret=self._client_secret,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=SCOPES,
        )
        creds.refresh(Request())

        self._service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return self._service

    def upload_file(self, file_path, filename):
        """
        Upload a file to the configured Google Drive folder.

        Args:
            file_path: Local path to the file to upload.
            filename: Name to give the file in Google Drive.

        Returns:
            tuple: (success: bool, error_msg: str, file_id: str or None)
        """
        if not self.is_available():
            return False, "Google Drive backup not configured", None

        try:
            service = self._get_service()

            file_metadata = {
                'name': filename,
                'parents': [self.folder_id],
            }

            # Determine MIME type
            if filename.endswith('.zip'):
                mime_type = 'application/zip'
            else:
                mime_type = 'application/sql'

            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

            result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, size',
            ).execute()

            file_id = result.get('id')
            file_size = result.get('size', '0')
            logger.info("Uploaded '%s' to Google Drive (id=%s, size=%s bytes)", filename, file_id, file_size)
            return True, "", file_id

        except Exception as e:
            logger.error("Google Drive upload failed: %s", e, exc_info=True)
            return False, str(e), None

    def list_backups(self):
        """
        List backup files in the configured Google Drive folder.

        Returns:
            list[dict]: List of files with 'id', 'name', 'size', 'createdTime'.
        """
        if not self.is_available():
            return []

        try:
            service = self._get_service()
            query = f"'{self.folder_id}' in parents and trashed = false"
            results = service.files().list(
                q=query,
                fields="files(id, name, size, createdTime)",
                orderBy="createdTime desc",
                pageSize=100,
            ).execute()
            return results.get('files', [])
        except Exception as e:
            logger.error("Failed to list Google Drive backups: %s", e, exc_info=True)
            return []

    def delete_file(self, file_id):
        """
        Delete a file from Google Drive.

        Args:
            file_id: Google Drive file ID.

        Returns:
            tuple: (success: bool, error_msg: str)
        """
        if not self.is_available():
            return False, "Google Drive backup not configured"

        try:
            service = self._get_service()
            service.files().delete(fileId=file_id).execute()
            logger.info("Deleted Google Drive file: %s", file_id)
            return True, ""
        except Exception as e:
            logger.error("Failed to delete Google Drive file %s: %s", file_id, e, exc_info=True)
            return False, str(e)


# Singleton
_google_drive_backup_service = None


def get_google_drive_backup_service():
    """Get or create the Google Drive backup service singleton."""
    global _google_drive_backup_service
    if _google_drive_backup_service is None:
        _google_drive_backup_service = GoogleDriveBackupService()
    return _google_drive_backup_service
