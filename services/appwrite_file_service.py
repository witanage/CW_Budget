"""
Appwrite File Service

Handles all file operations with Appwrite Cloud Storage.
- Upload files (with support for large files)
- Download files
- Get file metadata
- Delete files
- Fallback to HTTP API when SDK fails
"""

import logging
import os
import tempfile
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Try importing optional dependencies
try:
    from appwrite.client import Client
    from appwrite.services.storage import Storage
    from appwrite.input_file import InputFile
    from appwrite.id import ID

    APPWRITE_AVAILABLE = True
except ImportError:
    APPWRITE_AVAILABLE = False
    logger.warning("appwrite not installed. File storage will be disabled.")


class AppwriteFileService:
    """Service for managing files in Appwrite Cloud Storage."""

    def __init__(self):
        """Initialize the Appwrite file service."""
        self.endpoint = os.environ.get('APPWRITE_ENDPOINT')
        self.project_id = os.environ.get('APPWRITE_PROJECT_ID')
        self.api_key = os.environ.get('APPWRITE_API_KEY')
        self.bucket_id = os.environ.get('APPWRITE_BUCKET_ID')

        self.client = None
        self.storage = None
        self._initialized = False

    def _initialize_client(self):
        """Initialize Appwrite client lazily."""
        if self._initialized:
            return

        if not APPWRITE_AVAILABLE:
            logger.warning("Appwrite SDK not available")
            return

        if not all([self.endpoint, self.project_id, self.api_key, self.bucket_id]):
            logger.warning("Appwrite credentials incomplete. Set them in .env file.")
            return

        try:
            self.client = Client()
            self.client.set_endpoint(self.endpoint)
            self.client.set_project(self.project_id)
            self.client.set_key(self.api_key)
            self.storage = Storage(self.client)
            self._initialized = True
            logger.info(f"✅ Appwrite file service initialized (endpoint: {self.endpoint})")
        except Exception as e:
            logger.error(f"Failed to initialize Appwrite client: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """Check if the service is available and configured."""
        self._initialize_client()
        return self._initialized and self.storage is not None

    def get_file_metadata(self, file_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get file metadata (name and MIME type).

        Args:
            file_id: The file ID (GUID) in Appwrite storage

        Returns:
            Tuple of (file_name, mime_type), or (file_id, 'application/octet-stream') on failure
        """
        self._initialize_client()

        if not self.storage:
            logger.error("Appwrite storage not initialized")
            return file_id, 'application/octet-stream'

        # Try SDK first
        try:
            file_info = self.storage.get_file(self.bucket_id, file_id)

            # SDK returns a File object (Pydantic model), not a dict
            file_name = getattr(file_info, 'name', file_id)
            mime_type = getattr(file_info, 'mime_type', None) or getattr(file_info, 'mimeType',
                                                                         'application/octet-stream')

            logger.info(f"Got metadata for {file_id}: {file_name}, mime: {mime_type}")
            return file_name, mime_type

        except Exception as e:
            logger.warning(f"SDK get_file failed for {file_id}: {str(e)}, trying HTTP API")

            # Fallback to HTTP API
            try:
                metadata_url = f"{self.endpoint}/storage/buckets/{self.bucket_id}/files/{file_id}"
                headers = {
                    'X-Appwrite-Project': self.project_id,
                    'X-Appwrite-Key': self.api_key
                }
                metadata_response = requests.get(metadata_url, headers=headers, timeout=10)

                if metadata_response.status_code == 200:
                    file_info = metadata_response.json()
                    file_name = file_info.get('name', file_id)
                    mime_type = file_info.get('mimeType', 'application/octet-stream')
                    logger.info(f"Got metadata via HTTP: {file_name}, mime: {mime_type}")
                    return file_name, mime_type
                else:
                    logger.error(f"HTTP metadata fetch failed with status {metadata_response.status_code}")
                    return file_id, 'application/octet-stream'

            except Exception as e2:
                logger.error(f"HTTP metadata fetch also failed for {file_id}: {str(e2)}")
                return file_id, 'application/octet-stream'

    def download_file(self, file_id: str) -> Tuple[Optional[bytes], int, Optional[str]]:
        """
        Download file content from Appwrite.

        Args:
            file_id: The file ID (GUID) in Appwrite storage

        Returns:
            Tuple of (file_content, status_code, error_message)
            - On success: (bytes, 200, None)
            - On failure: (None, error_code, error_message)
        """
        self._initialize_client()

        if not all([self.endpoint, self.project_id, self.api_key]):
            return None, 500, "Appwrite configuration incomplete"

        try:
            download_url = f"{self.endpoint}/storage/buckets/{self.bucket_id}/files/{file_id}/download"

            headers = {
                'X-Appwrite-Project': self.project_id,
                'X-Appwrite-Key': self.api_key
            }

            response = requests.get(download_url, headers=headers, timeout=30)

            if response.status_code == 200:
                logger.info(f"Successfully downloaded file {file_id}, size: {len(response.content)} bytes")
                return response.content, 200, None
            else:
                error_msg = f"Download failed with status {response.status_code}"
                logger.error(error_msg)
                return None, response.status_code, error_msg

        except requests.exceptions.Timeout:
            error_msg = "Download request timed out"
            logger.error(f"{error_msg} for file {file_id}")
            return None, 504, error_msg
        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            logger.error(f"{error_msg} for file {file_id}")
            return None, 500, error_msg

    def upload_file(self, file_data: bytes, file_id: str, filename: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Upload file to Appwrite storage.

        Args:
            file_data: The file content as bytes
            file_id: The file ID (GUID) to use for storage
            filename: The original filename

        Returns:
            Tuple of (success, error_message, result_info)
            - On success: (True, None, result_dict)
            - On failure: (False, error_message, None)
        """
        self._initialize_client()

        if not self.storage:
            return False, "Appwrite storage not initialized", None

        try:
            # Use from_path with a temp file to avoid SDK chunked upload bug
            # (from_bytes calculates wrong byte range for last chunk on files >= 5MB)
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = os.path.join(tmp_dir, filename)
                with open(tmp_path, 'wb') as f:
                    f.write(file_data)

                result = self.storage.create_file(
                    self.bucket_id,
                    file_id,
                    InputFile.from_path(tmp_path)
                )

            # Handle both dict and Pydantic model response
            if hasattr(result, 'model_dump'):
                result_dict = result.model_dump()
            elif hasattr(result, 'dict'):
                result_dict = result.dict()
            else:
                result_dict = result if isinstance(result, dict) else {}

            file_size = result_dict.get('sizeOriginal', len(file_data))
            logger.info(f"✓ File uploaded successfully: {file_id}, size: {file_size} bytes")

            return True, None, result_dict

        except Exception as e:
            error_msg = f"Failed to upload file to Appwrite: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None

    def delete_file(self, file_id: str) -> Tuple[bool, Optional[str]]:
        """
        Delete file from Appwrite storage.

        Args:
            file_id: The file ID (GUID) to delete

        Returns:
            Tuple of (success, error_message)
            - On success: (True, None)
            - On failure: (False, error_message)
        """
        self._initialize_client()

        if not self.storage:
            return False, "Appwrite storage not initialized"

        try:
            self.storage.delete_file(self.bucket_id, file_id)
            logger.info(f"✓ File deleted successfully: {file_id}")
            return True, None

        except Exception as e:
            error_msg = f"Failed to delete file {file_id}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def get_download_url(self, file_id: str) -> Optional[str]:
        """
        Get the direct download URL for a file.

        Args:
            file_id: The file ID (GUID)

        Returns:
            The download URL or None if not configured
        """
        if not all([self.endpoint, self.bucket_id]):
            return None

        return f"{self.endpoint}/storage/buckets/{self.bucket_id}/files/{file_id}/download"

    def get_view_url(self, file_id: str) -> Optional[str]:
        """
        Get the direct view URL for a file.

        Args:
            file_id: The file ID (GUID)

        Returns:
            The view URL or None if not configured
        """
        if not all([self.endpoint, self.bucket_id]):
            return None

        return f"{self.endpoint}/storage/buckets/{self.bucket_id}/files/{file_id}/view"


# Singleton instance
_appwrite_file_service = None


def get_appwrite_file_service() -> AppwriteFileService:
    """Get or create the singleton Appwrite file service instance."""
    global _appwrite_file_service
    if _appwrite_file_service is None:
        _appwrite_file_service = AppwriteFileService()
    return _appwrite_file_service
