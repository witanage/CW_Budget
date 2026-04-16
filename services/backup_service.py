"""
Database Backup Service

Handles automated database backups with password-protected encryption.
- Creates MySQL-compatible SQL dumps
- Compresses and encrypts backups with AES-256
- Uploads to Google Drive
"""

import io
import logging
import os
import signal
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal

from db import get_db_connection, DB_CONFIG
from services.google_drive_backup_service import get_google_drive_backup_service

logger = logging.getLogger(__name__)

# Try importing optional dependencies
try:
    import pyzipper
    PYZIPPER_AVAILABLE = True
except ImportError:
    PYZIPPER_AVAILABLE = False
    logger.warning("pyzipper not installed. Backups will be stored uncompressed and unencrypted.")


class BackupService:
    """Service for creating and uploading encrypted database backups."""

    def __init__(self):
        """Initialize the backup service."""
        self.backup_timeout = int(os.environ.get('BACKUP_TIMEOUT_SECONDS', '50'))
        self.backup_password = os.environ.get('BACKUP_ENCRYPTION_PASSWORD')
        self.drive_service = get_google_drive_backup_service()

    def _timeout_handler(self, signum, frame):
        """Signal handler for backup timeout."""
        raise TimeoutError(f"Backup exceeded {self.backup_timeout}s timeout")

    def _sql_escape(self, val):
        """Escape SQL values for safe insertion in backup."""
        if val is None:
            return 'NULL'
        if isinstance(val, bool):
            return '1' if val else '0'
        if isinstance(val, (int, float, Decimal)):
            return str(val)
        if isinstance(val, (bytes, bytearray)):
            hex_str = val.hex()
            return f"X'{hex_str}'" if hex_str else "''"
        if isinstance(val, datetime):
            return f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'"
        if isinstance(val, timedelta):
            total = int(val.total_seconds())
            h, rem = divmod(abs(total), 3600)
            m, s = divmod(rem, 60)
            sign = '-' if total < 0 else ''
            return f"'{sign}{h:02d}:{m:02d}:{s:02d}'"
        s = str(val)
        s = s.replace('\\', '\\\\')
        s = s.replace("'", "\\'")
        s = s.replace('\n', '\\n')
        s = s.replace('\r', '\\r')
        s = s.replace('\x00', '\\0')
        s = s.replace('\x1a', '\\Z')
        return f"'{s}'"

    def _generate_sql_dump(self, connection, cursor):
        """Generate a complete SQL dump of the database."""
        db_name = DB_CONFIG['database']
        output = io.StringIO()

        # Ensure SHOW CREATE TABLE uses backtick-quoted identifiers (not ANSI double quotes)
        cursor.execute("SET SESSION sql_mode = REPLACE(REPLACE(@@sql_mode, 'ANSI_QUOTES', ''), 'ANSI', '')")

        # Get MySQL version
        cursor.execute("SELECT VERSION()")
        mysql_version = cursor.fetchone()[0]

        # Write SQL header
        output.write("-- MySQL dump\n")
        output.write(f"-- Host: {DB_CONFIG['host']}    Database: {db_name}\n")
        output.write("-- ------------------------------------------------------\n")
        output.write(f"-- Server version\t{mysql_version}\n\n")
        output.write("/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;\n")
        output.write("/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;\n")
        output.write("/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;\n")
        output.write("/*!40101 SET NAMES utf8mb4 */;\n")
        output.write("/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;\n")
        output.write("/*!40103 SET TIME_ZONE='+00:00' */;\n")
        output.write("/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;\n")
        output.write("/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;\n")
        output.write("/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;\n")
        output.write("/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;\n")
        output.write("/*!80000 SET @OLD_SQL_REQUIRE_PRIMARY_KEY=@@SQL_REQUIRE_PRIMARY_KEY, SQL_REQUIRE_PRIMARY_KEY=0 */;\n\n")

        # Get database objects
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        tables = [row[0] for row in cursor.fetchall()]

        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
        views = [row[0] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
            "WHERE ROUTINE_SCHEMA = %s AND ROUTINE_TYPE = 'PROCEDURE'", (db_name,))
        procedures = [row[0] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
            "WHERE ROUTINE_SCHEMA = %s AND ROUTINE_TYPE = 'FUNCTION'", (db_name,))
        functions = [row[0] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = %s", (db_name,))
        triggers = [row[0] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT EVENT_NAME FROM INFORMATION_SCHEMA.EVENTS "
            "WHERE EVENT_SCHEMA = %s", (db_name,))
        events = [row[0] for row in cursor.fetchall()]

        logger.info("Backup objects: %d tables, %d views, %d procedures, "
                    "%d functions, %d triggers, %d events",
                    len(tables), len(views), len(procedures),
                    len(functions), len(triggers), len(events))

        # Dump tables (structure + data)
        for table in tables:
            self._dump_table(cursor, output, table)

        # Dump views
        if views:
            self._dump_views(cursor, output, views)

        # Dump stored procedures
        if procedures:
            self._dump_procedures(cursor, output, procedures, db_name)

        # Dump functions
        if functions:
            self._dump_functions(cursor, output, functions)

        # Dump triggers
        if triggers:
            self._dump_triggers(cursor, output, triggers)

        # Dump events
        if events:
            self._dump_events(cursor, output, events)

        # Write SQL footer
        output.write("/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;\n")
        output.write("/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;\n")
        output.write("/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;\n")
        output.write("/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;\n")
        output.write("/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;\n")
        output.write("/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;\n")
        output.write("/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;\n")
        output.write("/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;\n")
        output.write("/*!80000 SET SQL_REQUIRE_PRIMARY_KEY=@OLD_SQL_REQUIRE_PRIMARY_KEY */;\n\n")
        output.write(f"-- Dump completed on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        return output.getvalue()

    def _dump_table(self, cursor, output, table):
        """Dump table structure and data."""
        output.write(f"--\n-- Table structure for table `{table}`\n--\n\n")
        output.write(f"DROP TABLE IF EXISTS `{table}`;\n")
        output.write("/*!40101 SET @saved_cs_client     = @@character_set_client */;\n")
        output.write("/*!40101 SET character_set_client = utf8 */;\n")
        cursor.execute(f"SHOW CREATE TABLE `{table}`")
        output.write(f"{cursor.fetchone()[1]};\n")
        output.write("/*!40101 SET character_set_client = @saved_cs_client */;\n\n")

        cursor.execute(f"SELECT * FROM `{table}`")
        rows = cursor.fetchall()
        if rows:
            col_names = [d[0] for d in cursor.description]
            col_list = ', '.join(f'`{c}`' for c in col_names)
            output.write(f"--\n-- Dumping data for table `{table}`\n--\n\n")
            output.write(f"LOCK TABLES `{table}` WRITE;\n")
            output.write(f"/*!40000 ALTER TABLE `{table}` DISABLE KEYS */;\n")
            for i in range(0, len(rows), 100):
                batch = rows[i:i + 100]
                output.write(f"INSERT INTO `{table}` ({col_list}) VALUES\n")
                output.write(',\n'.join(
                    '(' + ', '.join(self._sql_escape(v) for v in row) + ')' for row in batch
                ))
                output.write(';\n')
            output.write(f"/*!40000 ALTER TABLE `{table}` ENABLE KEYS */;\n")
            output.write("UNLOCK TABLES;\n\n")

    def _dump_views(self, cursor, output, views):
        """Dump view definitions."""
        output.write("--\n-- Final view structure for views\n--\n\n")
        for view in views:
            output.write(f"--\n-- Final view structure for view `{view}`\n--\n\n")
            output.write(f"/*!50001 DROP VIEW IF EXISTS `{view}`*/;\n")
            output.write("/*!50001 SET @saved_cs_client          = @@character_set_client */;\n")
            output.write("/*!50001 SET @saved_cs_results         = @@character_set_results */;\n")
            output.write("/*!50001 SET @saved_col_connection     = @@collation_connection */;\n")
            output.write("/*!50001 SET character_set_client      = utf8mb4 */;\n")
            output.write("/*!50001 SET character_set_results     = utf8mb4 */;\n")
            output.write("/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;\n")
            try:
                cursor.execute(f"SHOW CREATE VIEW `{view}`")
                result = cursor.fetchone()
                if result and len(result) >= 2:
                    output.write(f"/*!50001 {result[1]} */;\n")
                    output.write("/*!50001 SET character_set_client      = @saved_cs_client */;\n")
                    output.write("/*!50001 SET character_set_results     = @saved_cs_results */;\n")
                    output.write("/*!50001 SET collation_connection      = @saved_col_connection */;\n\n")
            except Exception as e:
                output.write(f"-- Error exporting view `{view}`: {e}\n\n")

    def _dump_procedures(self, cursor, output, procedures, db_name):
        """Dump stored procedure definitions."""
        output.write("--\n-- Dumping routines for database '" + db_name + "'\n--\n")
        for proc in procedures:
            output.write(f"--\n-- Procedure `{proc}`\n--\n\n")
            output.write(f"/*!50003 DROP PROCEDURE IF EXISTS `{proc}` */;\n")
            output.write("/*!50003 SET @saved_cs_client      = @@character_set_client */ ;\n")
            output.write("/*!50003 SET @saved_cs_results     = @@character_set_results */ ;\n")
            output.write("/*!50003 SET @saved_col_connection = @@collation_connection */ ;\n")
            output.write("/*!50003 SET character_set_client  = utf8mb4 */ ;\n")
            output.write("/*!50003 SET character_set_results = utf8mb4 */ ;\n")
            output.write("/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;\n")
            output.write("/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;\n")
            output.write("/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;\n")
            output.write("DELIMITER ;;\n")
            try:
                cursor.execute(f"SHOW CREATE PROCEDURE `{proc}`")
                result = cursor.fetchone()
                if result and len(result) >= 3:
                    output.write(f"{result[2]} ;;\n")
            except Exception as e:
                output.write(f"-- Error exporting procedure `{proc}`: {e}\n")
            output.write("DELIMITER ;\n")
            output.write("/*!50003 SET sql_mode              = @saved_sql_mode */ ;\n")
            output.write("/*!50003 SET character_set_client  = @saved_cs_client */ ;\n")
            output.write("/*!50003 SET character_set_results = @saved_cs_results */ ;\n")
            output.write("/*!50003 SET collation_connection  = @saved_col_connection */ ;\n\n")

    def _dump_functions(self, cursor, output, functions):
        """Dump function definitions."""
        for func in functions:
            output.write(f"--\n-- Function `{func}`\n--\n\n")
            output.write(f"/*!50003 DROP FUNCTION IF EXISTS `{func}` */;\n")
            output.write("/*!50003 SET @saved_cs_client      = @@character_set_client */ ;\n")
            output.write("/*!50003 SET @saved_cs_results     = @@character_set_results */ ;\n")
            output.write("/*!50003 SET @saved_col_connection = @@collation_connection */ ;\n")
            output.write("/*!50003 SET character_set_client  = utf8mb4 */ ;\n")
            output.write("/*!50003 SET character_set_results = utf8mb4 */ ;\n")
            output.write("/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;\n")
            output.write("/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;\n")
            output.write("/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;\n")
            output.write("DELIMITER ;;\n")
            try:
                cursor.execute(f"SHOW CREATE FUNCTION `{func}`")
                result = cursor.fetchone()
                if result and len(result) >= 3:
                    output.write(f"{result[2]} ;;\n")
            except Exception as e:
                output.write(f"-- Error exporting function `{func}`: {e}\n")
            output.write("DELIMITER ;\n")
            output.write("/*!50003 SET sql_mode              = @saved_sql_mode */ ;\n")
            output.write("/*!50003 SET character_set_client  = @saved_cs_client */ ;\n")
            output.write("/*!50003 SET character_set_results = @saved_cs_results */ ;\n")
            output.write("/*!50003 SET collation_connection  = @saved_col_connection */ ;\n\n")

    def _dump_triggers(self, cursor, output, triggers):
        """Dump trigger definitions."""
        for trigger in triggers:
            output.write(f"--\n-- Trigger `{trigger}`\n--\n\n")
            output.write("/*!50003 SET @saved_cs_client      = @@character_set_client */ ;\n")
            output.write("/*!50003 SET @saved_cs_results     = @@character_set_results */ ;\n")
            output.write("/*!50003 SET @saved_col_connection = @@collation_connection */ ;\n")
            output.write("/*!50003 SET character_set_client  = utf8mb4 */ ;\n")
            output.write("/*!50003 SET character_set_results = utf8mb4 */ ;\n")
            output.write("/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;\n")
            output.write("/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;\n")
            output.write("/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;\n")
            output.write("DELIMITER ;;\n")
            try:
                cursor.execute(f"SHOW CREATE TRIGGER `{trigger}`")
                result = cursor.fetchone()
                if result and len(result) >= 3:
                    output.write(f"/*!50003 {result[2]} */;;\n")
            except Exception as e:
                output.write(f"-- Error exporting trigger `{trigger}`: {e}\n")
            output.write("DELIMITER ;\n")
            output.write("/*!50003 SET sql_mode              = @saved_sql_mode */ ;\n")
            output.write("/*!50003 SET character_set_client  = @saved_cs_client */ ;\n")
            output.write("/*!50003 SET character_set_results = @saved_cs_results */ ;\n")
            output.write("/*!50003 SET collation_connection  = @saved_col_connection */ ;\n\n")

    def _dump_events(self, cursor, output, events):
        """Dump event definitions."""
        output.write("--\n-- Dumping events for database\n--\n")
        for event in events:
            output.write(f"--\n-- Event `{event}`\n--\n\n")
            output.write(f"/*!50106 DROP EVENT IF EXISTS `{event}` */;\n")
            output.write("DELIMITER ;;\n")
            output.write("/*!50106 SET @save_time_zone= @@TIME_ZONE */ ;;\n")
            output.write("/*!50106 SET TIME_ZONE= 'SYSTEM' */ ;;\n")
            output.write("/*!50106 SET @saved_cs_client      = @@character_set_client */ ;;\n")
            output.write("/*!50106 SET @saved_cs_results     = @@character_set_results */ ;;\n")
            output.write("/*!50106 SET @saved_col_connection = @@collation_connection */ ;;\n")
            output.write("/*!50106 SET character_set_client  = utf8mb4 */ ;;\n")
            output.write("/*!50106 SET character_set_results = utf8mb4 */ ;;\n")
            output.write("/*!50106 SET collation_connection  = utf8mb4_0900_ai_ci */ ;;\n")
            output.write("/*!50106 SET @saved_sql_mode       = @@sql_mode */ ;;\n")
            output.write("/*!50106 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;;\n")
            try:
                cursor.execute(f"SHOW CREATE EVENT `{event}`")
                result = cursor.fetchone()
                if result and len(result) >= 4:
                    output.write(f"/*!50106 {result[3]} */ ;;\n")
            except Exception as e:
                output.write(f"-- Error exporting event `{event}`: {e}\n")
            output.write("/*!50106 SET sql_mode              = @saved_sql_mode */ ;;\n")
            output.write("/*!50106 SET character_set_client  = @saved_cs_client */ ;;\n")
            output.write("/*!50106 SET character_set_results = @saved_cs_results */ ;;\n")
            output.write("/*!50106 SET collation_connection  = @saved_col_connection */ ;;\n")
            output.write("/*!50106 SET TIME_ZONE= @save_time_zone */ ;;\n")
            output.write("DELIMITER ;\n\n")

    def _compress_and_encrypt(self, sql_bytes, filename, timestamp):
        """Compress SQL dump and encrypt with password protection."""
        if not self.backup_password:
            logger.warning("BACKUP_ENCRYPTION_PASSWORD not set. Backup will be stored unencrypted.")
            return None, filename

        if not PYZIPPER_AVAILABLE:
            logger.warning("pyzipper not available. Backup will be stored unencrypted.")
            return None, filename

        db_name = DB_CONFIG['database']
        zip_filename = f"{db_name}_{timestamp}.zip"

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Write SQL file
                sql_path = os.path.join(tmp_dir, filename)
                with open(sql_path, 'wb') as f:
                    f.write(sql_bytes if isinstance(sql_bytes, bytes) else sql_bytes.encode('utf-8'))

                # Create password-protected zip with AES-256 encryption
                zip_path = os.path.join(tmp_dir, zip_filename)
                with pyzipper.AESZipFile(
                    zip_path,
                    'w',
                    compression=pyzipper.ZIP_DEFLATED,
                    encryption=pyzipper.WZ_AES
                ) as zf:
                    zf.setpassword(self.backup_password.encode('utf-8'))
                    zf.write(sql_path, filename)

                # Read the zip file
                with open(zip_path, 'rb') as f:
                    zip_bytes = f.read()

                return zip_bytes, zip_filename
        except Exception as e:
            logger.error("Zip compression/encryption failed: %s", e, exc_info=True)
            return None, filename

    def create_and_upload_backup(self):
        """
        Create a database backup, compress and encrypt it, then upload to Google Drive.

        Returns:
            tuple: (success: bool, message: str)
        """
        # Check Google Drive availability
        if not self.drive_service.is_available():
            msg = ("Google Drive backup not configured. Set GOOGLE_DRIVE_BACKUP_FOLDER_ID "
                   "and GOOGLE_DRIVE_SA_KEY_PATH (or GOOGLE_DRIVE_SA_KEY_JSON) in .env")
            logger.error("Backup aborted: %s", msg)
            return False, msg

        # Database connection
        connection = get_db_connection()
        if not connection:
            logger.error("Backup aborted: DB connection failed")
            return False, "Database connection failed"

        cursor = connection.cursor()
        sql_bytes = None
        old_handler = None

        # Set up timeout (Unix only)
        try:
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
                signal.alarm(self.backup_timeout)
        except Exception as e:
            logger.warning("Could not set backup timeout: %s", e)

        try:
            # Generate SQL dump
            db_name = DB_CONFIG['database']
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{db_name}_{timestamp}.sql"

            sql_content = self._generate_sql_dump(connection, cursor)
            sql_bytes = sql_content.encode('utf-8')
            logger.info("Python-based backup completed (%d bytes)", len(sql_bytes))

        except TimeoutError as e:
            logger.error("Backup timeout: %s", e)
            cursor.close()
            connection.close()
            return False, f"Backup timed out after {self.backup_timeout}s"
        except Exception as e:
            logger.error("Python backup failed: %s", e, exc_info=True)
            cursor.close()
            connection.close()
            return False, f"Backup generation failed: {e}"
        finally:
            # Cancel the alarm
            if hasattr(signal, 'SIGALRM') and old_handler is not None:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            cursor.close()
            connection.close()

        if not sql_bytes:
            logger.error("Backup failed: no data generated")
            return False, "No backup data generated"

        # Compress and encrypt
        encrypted_bytes, upload_filename = self._compress_and_encrypt(sql_bytes, filename, timestamp)

        # Upload to Google Drive
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                if encrypted_bytes:
                    # Upload encrypted zip
                    tmp_path = os.path.join(tmp_dir, upload_filename)
                    with open(tmp_path, 'wb') as f:
                        f.write(encrypted_bytes)

                    success, error_msg, file_id = self.drive_service.upload_file(tmp_path, upload_filename)
                    if not success:
                        return False, f"Google Drive upload failed: {error_msg}"

                    original_mb = len(sql_bytes) / (1024 * 1024)
                    zip_mb = len(encrypted_bytes) / (1024 * 1024)
                    compression_ratio = (1 - len(encrypted_bytes) / len(sql_bytes)) * 100

                    logger.info("✅ Encrypted backup uploaded to Google Drive — file_id=%s", file_id)
                    logger.info("   Original: %.2f MB | Compressed: %.2f MB | Saved: %.1f%%",
                                original_mb, zip_mb, compression_ratio)
                    return True, f"Encrypted backup uploaded: {file_id} (Compressed: {zip_mb:.2f} MB, Saved: {compression_ratio:.1f}%)"
                else:
                    # Upload unencrypted SQL (fallback)
                    tmp_path = os.path.join(tmp_dir, upload_filename)
                    with open(tmp_path, 'wb') as f:
                        f.write(sql_bytes)

                    success, error_msg, file_id = self.drive_service.upload_file(tmp_path, upload_filename)
                    if not success:
                        return False, f"Google Drive upload failed: {error_msg}"

                    size_mb = len(sql_bytes) / (1024 * 1024)
                    logger.info("✅ Backup uploaded to Google Drive — file_id=%s (%.2f MB) [UNENCRYPTED]",
                                file_id, size_mb)
                    return True, f"Backup uploaded successfully: {file_id} ({size_mb:.2f} MB) [UNENCRYPTED]"

        except Exception as e:
            logger.error("Google Drive upload failed: %s", e, exc_info=True)
            return False, f"Upload failed: {e}"


# Singleton instance
_backup_service = None


def get_backup_service():
    """Get or create the backup service singleton."""
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService()
    return _backup_service
