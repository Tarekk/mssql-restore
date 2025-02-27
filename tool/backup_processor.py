"""
Backup processor for MSSQL Backup Tool.

Extracts and restores SQL Server backup files.
"""

import logging
import os
import shutil
import tempfile
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import patoolib
import pymssql

logger = logging.getLogger(__name__)


class BackupProcessor:
    """
    Processes MSSQL backup files (extraction and restoration).

    Handles both direct backup files (.dat) and archives containing
    backup files (.rar).
    """

    def __init__(
        self,
        mssql_settings: Dict[str, Any],
        shared_backup_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize processor with MSSQL connection settings.

        Args:
            mssql_settings: Dictionary of MSSQL connection settings
            shared_backup_dir: Directory accessible by both tool and SQL Server
            progress_callback: Callback for progress updates
        """
        self.mssql_settings = mssql_settings
        self.shared_backup_dir = shared_backup_dir or "/shared_backup"
        self.progress_callback = progress_callback or (lambda *args: None)

        # Ensure shared backup directory exists
        os.makedirs(self.shared_backup_dir, exist_ok=True)

    def process_backup(
        self,
        backup_path: str,
        target_db_name: Optional[str] = None,
        archive_processed: bool = True,
    ) -> Dict[str, Any]:
        """
        Process a backup file and restore it to SQL Server.

        Args:
            backup_path: Path to backup file (DAT or RAR)
            target_db_name: Optional name for restored database
            archive_processed: Whether to archive processed file

        Returns:
            Dict[str, Any]: Result containing database name and restored files

        Raises:
            ValueError: For unsupported file types
            IOError: For file access errors
            Exception: For other processing errors
        """
        # Report progress
        file_name = os.path.basename(backup_path)
        file_size = os.path.getsize(backup_path)
        file_ext = os.path.splitext(backup_path)[1].lower()

        self.progress_callback(
            "processing",
            f"Processing {file_name}",
            {"file_name": file_name, "file_size": file_size, "file_type": file_ext},
        )

        # Process based on file type
        result = None
        if file_ext == ".rar":
            result = self._process_rar(backup_path, target_db_name)
        elif file_ext == ".dat":
            result = self._process_dat(backup_path, target_db_name)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        # Archive processed file if requested
        if archive_processed:
            archive_path = self._archive_file(backup_path)
            result["archived_path"] = archive_path

        return result

    def _process_rar(
        self, rar_path: str, target_db_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a RAR file containing a backup.

        Args:
            rar_path: Path to RAR file
            target_db_name: Optional name for restored database

        Returns:
            Dict[str, Any]: Result with database info

        Raises:
            IOError: For extraction errors
            Exception: For other processing errors
        """
        temp_dir = None
        try:
            # Create temporary directory for extraction
            temp_dir = tempfile.mkdtemp()

            self.progress_callback(
                "processing",
                f"Extracting RAR archive",
                {"step": "extracting", "temp_dir": temp_dir},
            )

            # Extract RAR file
            patoolib.extract_archive(rar_path, outdir=temp_dir)

            # Look for DAT files
            dat_files = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith(".dat"):
                        dat_files.append(os.path.join(root, file))

            if not dat_files:
                raise ValueError("No .dat backup files found in RAR archive")

            # Process the first DAT file found
            self.progress_callback(
                "processing",
                f"Found backup file in archive",
                {"dat_file": os.path.basename(dat_files[0])},
            )

            return self._process_dat(dat_files[0], target_db_name)

        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def _process_dat(
        self, dat_path: str, target_db_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a DAT backup file.

        Args:
            dat_path: Path to DAT file
            target_db_name: Optional name for restored database

        Returns:
            Dict[str, Any]: Result with database info

        Raises:
            IOError: For file access errors
            Exception: For restore errors
        """
        # Validate backup file before processing
        self._validate_backup_file(dat_path)

        # Copy to shared backup directory
        shared_path = self._copy_to_shared_dir(dat_path)

        # Restore the backup
        self.progress_callback(
            "processing",
            f"Restoring database backup",
            {"step": "restoring", "backup_file": os.path.basename(dat_path)},
        )

        db_name, restored_files = self._restore_backup(shared_path, target_db_name)

        return {
            "database_name": db_name,
            "files_restored": restored_files,
            "original_file": os.path.basename(dat_path),
        }

    def _copy_to_shared_dir(self, file_path: str) -> str:
        """
        Copy a file to the shared backup directory.

        Args:
            file_path: Path to the file to copy

        Returns:
            str: Path in the shared directory

        Raises:
            IOError: For copy errors
        """
        filename = os.path.basename(file_path)
        shared_path = os.path.join(self.shared_backup_dir, filename)

        self.progress_callback(
            "processing",
            f"Copying to shared directory",
            {"step": "copying", "source": file_path, "destination": shared_path},
        )

        shutil.copy2(file_path, shared_path)
        return shared_path

    def _restore_backup(
        self, backup_path: str, target_db_name: Optional[str] = None
    ) -> Tuple[str, List[str]]:
        """
        Restore a backup file to SQL Server.

        Args:
            backup_path: Path to backup file
            target_db_name: Optional name for restored database

        Returns:
            Tuple[str, List[str]]: Database name and list of restored files

        Raises:
            Exception: For restore errors
        """
        conn = None
        cursor = None

        # Handle both dictionary and Pydantic model settings
        if hasattr(self.mssql_settings, "model_dump"):
            # For Pydantic v2+
            settings_dict = self.mssql_settings.model_dump()
        elif hasattr(self.mssql_settings, "dict"):
            # For older Pydantic versions
            settings_dict = self.mssql_settings.dict()
        elif isinstance(self.mssql_settings, dict):
            # Already a dictionary
            settings_dict = self.mssql_settings
        else:
            # Direct attribute access as fallback
            settings_dict = {
                "retry_attempts": getattr(self.mssql_settings, "retry_attempts", 3),
                "retry_delay": getattr(self.mssql_settings, "retry_delay", 5),
                "server": self.mssql_settings.server,
                "user": self.mssql_settings.user,
                "password": getattr(
                    self.mssql_settings.password,
                    "get_secret_value",
                    lambda: self.mssql_settings.password,
                )(),
                "port": getattr(self.mssql_settings, "port", 1433),
                "timeout": getattr(self.mssql_settings, "timeout", 60),
            }

        retry_attempts = settings_dict.get("retry_attempts", 3)
        retry_delay = settings_dict.get("retry_delay", 5)
        attempt = 0
        last_error = None

        while attempt < retry_attempts:
            try:
                # Connect to SQL Server
                attempt += 1
                self.progress_callback(
                    "processing",
                    f"Connecting to SQL Server (attempt {attempt}/{retry_attempts})",
                    {"step": "connecting", "attempt": attempt},
                )

                # Use dictionary for connection
                conn = pymssql.connect(
                    server=settings_dict.get("server", "localhost"),
                    user=settings_dict.get("user", "sa"),
                    password=settings_dict.get("password", ""),
                    database="master",
                    port=int(settings_dict.get("port", 1433)),
                    autocommit=True,
                    timeout=int(settings_dict.get("timeout", 60)),
                )
                cursor = conn.cursor(as_dict=True)
                break

            except Exception as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt} failed: {str(e)}")
                if attempt < retry_attempts:
                    time.sleep(retry_delay)
                else:
                    raise ConnectionError(
                        f"Failed to connect to SQL Server after {retry_attempts} attempts: {str(e)}"
                    )

        try:

            # Get backup file info
            cursor.execute(f"RESTORE FILELISTONLY FROM DISK = %s", (backup_path,))
            file_info = cursor.fetchall()

            if not file_info:
                raise ValueError("No file information found in backup")

            # Determine database name
            db_name = target_db_name
            if not db_name:
                # Use logical name from first file or generate a name
                db_name = file_info[0].get("LogicalName")
                if not db_name:
                    db_name = f"restored_db_{int(time.time())}"

            # Build MOVE commands for restore
            move_commands = []
            file_list = []

            for file in file_info:
                logical_name = file.get("LogicalName")
                file_list.append(logical_name)

                # Determine file extension
                file_type = file.get("Type")
                ext = ".ldf" if file_type == "L" else ".mdf"

                # Create move command
                move_cmd = f"MOVE N'{logical_name}' TO N'/var/opt/mssql/data/{logical_name}{ext}'"
                move_commands.append(move_cmd)

            # Build restore command
            move_clause = ",\n".join(move_commands)
            restore_sql = f"""
            RESTORE DATABASE [{db_name}]
            FROM DISK = %s
            WITH REPLACE,
            RECOVERY,
            STATS = 10,
            {move_clause}
            """

            # Execute restore
            self.progress_callback(
                "processing",
                f"Executing SQL restore command",
                {"step": "sql_restore", "database": db_name},
            )

            cursor.execute(restore_sql, (backup_path,))

            # Wait for database to come online
            self._wait_for_db_online(cursor, db_name)

            return db_name, file_list

        finally:
            # Clean up resources
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _wait_for_db_online(
        self, cursor, db_name: str, timeout: int = 300, check_interval: int = 5
    ) -> None:
        """
        Wait for a database to come online.

        Args:
            cursor: Active database cursor
            db_name: Database name
            timeout: Maximum wait time in seconds
            check_interval: Interval between checks in seconds

        Raises:
            TimeoutError: If database doesn't come online within timeout
        """
        start_time = time.time()
        last_state = None

        self.progress_callback(
            "processing",
            f"Waiting for database to come online",
            {"step": "waiting_for_online", "database": db_name, "timeout": timeout},
        )

        while time.time() - start_time < timeout:
            cursor.execute(
                "SELECT state_desc FROM sys.databases WHERE name = %s", (db_name,)
            )
            result = cursor.fetchone()

            if not result:
                time.sleep(check_interval)
                continue

            state = result.get("state_desc")
            if state != last_state:
                self.progress_callback(
                    "processing",
                    f"Database state: {state}",
                    {
                        "step": "waiting_for_online",
                        "database": db_name,
                        "state": state,
                        "elapsed_time": int(time.time() - start_time),
                    },
                )
                last_state = state

            if state == "ONLINE":
                self.progress_callback(
                    "processing",
                    f"Database is now online",
                    {
                        "step": "online",
                        "database": db_name,
                        "elapsed_time": int(time.time() - start_time),
                    },
                )
                return

            time.sleep(check_interval)

        raise TimeoutError(f"Timeout waiting for database {db_name} to come online")

    def _validate_backup_file(self, file_path: str) -> None:
        """
        Validate that a file is a valid SQL Server backup.

        Args:
            file_path: Path to backup file

        Raises:
            ValueError: If file is not a valid backup file
            IOError: For file access errors
        """
        # Check if file exists and has content
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Backup file not found: {file_path}")

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise ValueError(f"Backup file is empty: {file_path}")

        self.progress_callback(
            "processing",
            f"Validating backup file integrity",
            {
                "step": "validating",
                "file": os.path.basename(file_path),
                "size": file_size,
            },
        )

        # Basic header check for SQL Server backup files
        # SQL Server backup files start with "SQLBAK"
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)
                if not header.startswith(b"SQLBAK") and not b"MSSQL" in header[:1024]:
                    # This is a basic check, we'll still attempt to restore as the file might be compressed or encrypted
                    logger.warning(
                        f"File does not appear to be a standard SQL Server backup: {file_path}"
                    )
                    self.progress_callback(
                        "processing",
                        f"File doesn't have standard SQL backup header, will still attempt to process",
                        {"step": "validating", "warning": "non_standard_format"},
                    )
        except Exception as e:
            logger.warning(f"Error reading backup file header: {e}")

    def _archive_file(self, file_path: str) -> str:
        """
        Archive a processed file.

        Args:
            file_path: Path to the file to archive

        Returns:
            str: Path to the archived file

        Raises:
            IOError: For archive errors
        """
        # Create archive directory
        archive_dir = os.path.join(os.path.dirname(file_path), "archived")
        os.makedirs(archive_dir, exist_ok=True)

        # Generate archived filename with timestamp
        file_base, file_ext = os.path.splitext(os.path.basename(file_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived_filename = f"{file_base}_{timestamp}{file_ext}"
        archived_path = os.path.join(archive_dir, archived_filename)

        # Move the file
        self.progress_callback(
            "processing",
            f"Archiving processed file",
            {"step": "archiving", "source": file_path, "destination": archived_path},
        )

        shutil.move(file_path, archived_path)
        return archived_path
