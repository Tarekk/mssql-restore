"""
Backup file processing handler.

This module handles the detection, extraction, and restoration of
MSSQL backup files from various formats (RAR, DAT).
"""

import logging
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Tuple, Union
import uuid
from functools import wraps
import json

import patoolib
import pymssql
from watchdog.events import FileSystemEventHandler

# Configure logging
logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, delay: int = 5):
    """Retry decorator for functions that might fail temporarily.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Delay between attempts in seconds
        
    Returns:
        Decorated function that will retry on exception
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {str(e)}"
                    )
                    if attempt < max_attempts:
                        logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
                        raise last_exception
        return wrapper
    return decorator


def default_status_callback(filename: str, status: str, details: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Default no-op callback for status updates.
    
    Args:
        filename: The name of the file being processed
        status: Current status (processing, completed, failed)
        details: Human-readable details about the status
        metadata: Optional additional information about the processing
    """
    pass


class BackupFileHandler(FileSystemEventHandler):
    """Handles the detection and processing of new backup files.
    
    This class extends FileSystemEventHandler to detect and process
    backup files (RAR and DAT), extract them, and restore them to MSSQL.
    
    Attributes:
        mssql_server: SQL Server hostname or IP
        mssql_user: SQL Server username
        mssql_password: SQL Server password
        status_callback: Callback function for status updates
        shared_backup_dir: Directory for temporary backup files
        file_patterns: File extensions to process
        connection_timeout: SQL Server connection timeout
    """

    def __init__(
        self,
        mssql_server: str,
        mssql_user: str,
        mssql_password: str,
        status_callback: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
        shared_backup_dir: str = "/shared_backup",
        file_patterns: Optional[List[str]] = None,
        connection_timeout: int = 60,
    ):
        """Initialize the backup file handler.
        
        Args:
            mssql_server: SQL Server hostname or IP
            mssql_user: SQL Server username
            mssql_password: SQL Server password
            status_callback: Callback function for status updates
            shared_backup_dir: Directory for temporary backup files
            file_patterns: File extensions to process (default: [".rar", ".dat"])
            connection_timeout: SQL Server connection timeout in seconds
        """
        super().__init__()
        self.mssql_server = mssql_server
        self.mssql_user = mssql_user
        self.mssql_password = mssql_password
        self.status_callback = status_callback or default_status_callback
        self.shared_backup_dir = shared_backup_dir
        self.file_patterns = file_patterns or [".rar", ".dat"]
        self.connection_timeout = connection_timeout
        
        # Ensure shared backup directory exists
        os.makedirs(self.shared_backup_dir, exist_ok=True)
        
        logger.info("BackupFileHandler initialized with:")
        logger.info(f"MSSQL server: {mssql_server}")
        logger.info(f"Shared backup directory: {shared_backup_dir}")
        logger.info(f"File patterns: {self.file_patterns}")
        logger.info(f"Status callback: {'Provided' if status_callback else 'Default no-op'}")

    def update_file_status(
        self, 
        filename: str, 
        status: str, 
        details: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update file processing status using the provided callback.
        
        Args:
            filename: The name of the file being processed
            status: Current status (processing, completed, failed)
            details: Human-readable details about the status
            metadata: Optional additional information about the processing
        """
        try:
            # Extract just the base filename without path for consistency
            base_filename = os.path.basename(filename)
            
            # Default metadata if none provided
            if metadata is None:
                metadata = {}
                
            # Add common metadata fields
            metadata.update({
                "timestamp": datetime.now().isoformat(),
                "file_path": filename,
            })
                
            # Call the status callback
            self.status_callback(base_filename, status, details, metadata)
            logger.debug(f"Status update for {base_filename}: {status} - {details}")
                
        except Exception as e:
            logger.error(f"Error in status callback for {filename}: {str(e)}")
    
    def on_created(self, event) -> None:
        """Handle new backup file creation event.
        
        This method is called by the watchdog observer when a new file
        is created in the watched directory.
        
        Args:
            event: File system event containing the path to the new file
        """
        if event.is_directory:
            return
            
        file_path = event.src_path
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()

        # Skip files with unwanted extensions or temporary files
        if any(pattern in file_path for pattern in [".lock", ".tmp", ".part"]):
            logger.info(f"Skipping temporary file: {file_path}")
            return
            
        # Skip files with extensions not in our patterns
        if not any(file_path.lower().endswith(pattern) for pattern in self.file_patterns):
            logger.debug(f"Skipping file with unsupported extension: {file_path}")
            return

        logger.info(f"New backup file detected: {file_path}")
        
        # Update status to processing
        file_metadata = {
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "file_type": file_ext,
            "detection_time": datetime.now().isoformat(),
        }
        self.update_file_status(
            filename, 
            "processing", 
            "File detected and queued for processing",
            file_metadata
        )
        
        # Process the file based on its extension
        try:
            # Wait for the file to stabilize (no more changes in size)
            if not self._wait_for_file_stability(file_path):
                logger.warning(f"File {file_path} is still being modified, will be processed later")
                return
                
            # Update status to indicate processing has started
            self.update_file_status(
                filename,
                "processing",
                "File processing started",
                {"process_start_time": datetime.now().isoformat()}
            )
            
            db_name = None
            
            # Choose processing method based on file extension
            if file_path.lower().endswith(".rar"):
                logger.info(f"Processing RAR file: {file_path}")
                db_name = self.process_rar_file(file_path)
            elif file_path.lower().endswith(".dat"):
                logger.info(f"Processing DAT backup file: {file_path}")
                db_name = self.process_backup_file(file_path)
            else:
                logger.warning(f"Unhandled file type: {file_ext}")
                return
                
            # Check processing result
            if db_name:
                # Processing succeeded
                self.update_file_status(
                    filename, 
                    "completed", 
                    f"Processing completed successfully, restored to database {db_name}", 
                    {
                        "database_name": db_name,
                        "process_end_time": datetime.now().isoformat(),
                    }
                )
            else:
                # Processing failed
                self.update_file_status(
                    filename, 
                    "failed", 
                    "Processing failed to restore database",
                    {
                        "process_end_time": datetime.now().isoformat(),
                        "error_type": "DatabaseRestoreFailure"
                    }
                )
                
        except Exception as e:
            logger.exception(f"Error processing file {file_path}")
            # Update status to failed
            self.update_file_status(
                filename, 
                "failed", 
                f"Processing failed: {str(e)}",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": logging.traceback.format_exc()
                }
            )

    def _wait_for_file_stability(self, file_path: str, timeout: int = 60, check_interval: int = 2) -> bool:
        """Wait for a file to stop changing in size.
        
        Args:
            file_path: Path to the file to monitor
            timeout: Maximum time to wait in seconds
            check_interval: Time between size checks in seconds
            
        Returns:
            bool: True if file size stabilized, False if timeout occurred
        """
        start_time = time.time()
        last_size = os.path.getsize(file_path)
        logger.info(f"Waiting for file {file_path} to stabilize, current size: {last_size} bytes")
        
        while time.time() - start_time < timeout:
            time.sleep(check_interval)
            
            try:
                current_size = os.path.getsize(file_path)
                
                if current_size == last_size:
                    logger.info(f"File {file_path} size has stabilized at {current_size} bytes")
                    return True
                    
                logger.info(f"File {file_path} size changed: {last_size} → {current_size} bytes")
                last_size = current_size
                
            except OSError as e:
                logger.warning(f"Error checking file size: {e}")
                # File might have been moved or deleted
                return False
                
        logger.warning(f"Timeout waiting for file {file_path} to stabilize")
        return False

    @retry(max_attempts=3, delay=5)
    def process_rar_file(self, rar_path: str) -> Optional[str]:
        """Process a RAR file containing a backup.
        
        Extracts the RAR archive and processes any DAT files found inside.
        
        Args:
            rar_path: Path to the RAR file
            
        Returns:
            Optional[str]: Database name if successful, None otherwise
            
        Raises:
            FileNotFoundError: If the RAR file doesn't exist
            Exception: For extraction or processing errors
        """
        temp_dir = None
        restored_db = None
        try:
            # Create temporary directory for extraction
            temp_dir = tempfile.mkdtemp()
            logger.info(f"Created temporary directory for extraction: {temp_dir}")

            # Verify RAR file exists and is readable
            if not os.path.exists(rar_path):
                raise FileNotFoundError(f"RAR file not found: {rar_path}")

            logger.info(f"RAR file size: {os.path.getsize(rar_path)} bytes")
            logger.info(f"RAR file permissions: {oct(os.stat(rar_path).st_mode)[-3:]}")

            # Extract RAR file using patool
            logger.info(f"Extracting RAR file: {rar_path}")
            patoolib.extract_archive(rar_path, outdir=temp_dir, verbosity=1)
            logger.info("RAR extraction completed successfully")

            # Look for .dat files in the extracted contents
            dat_found = False
            for root, _, files in os.walk(temp_dir):
                logger.info(f"Scanning directory: {root}")
                dat_files = [f for f in files if f.endswith(".dat")]
                
                if dat_files:
                    logger.info(f"Found {len(dat_files)} DAT files: {dat_files}")
                    for dat_file in dat_files:
                        dat_path = os.path.join(root, dat_file)
                        logger.info(f"Processing DAT file from RAR: {dat_path}")
                        restored_db = self.process_backup_file(dat_path)
                        if restored_db:
                            dat_found = True
                            break
                if dat_found:
                    break

            if not dat_found:
                logger.warning(f"No valid .dat backup files found in RAR: {rar_path}")

            return restored_db

        except Exception as e:
            logger.exception(f"Error processing RAR file {rar_path}")
            raise
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary directory: {str(e)}")

            # Archive processed RAR file if successful
            if restored_db:
                try:
                    archived_path = self.archive_processed_file(rar_path)
                    logger.info(f"Archived RAR file: {rar_path} to {archived_path}")
                except Exception as e:
                    logger.error(f"Error archiving RAR file: {str(e)}")

    def archive_processed_file(self, file_path: str) -> str:
        """Move processed file to an archived directory.
        
        Args:
            file_path: Path to the file to archive
            
        Returns:
            str: Path to the archived file
            
        Raises:
            OSError: If file cannot be moved
        """
        # Create archive directory
        archive_dir = os.path.join(os.path.dirname(file_path), "archived")
        os.makedirs(archive_dir, exist_ok=True)
        
        # Generate unique archived filename with timestamp
        file_base, file_ext = os.path.splitext(os.path.basename(file_path))
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archived_filename = f"{file_base}_{timestamp}{file_ext}"
        archived_path = os.path.join(archive_dir, archived_filename)
        
        # Move the file
        shutil.move(file_path, archived_path)
        logger.info(f"Moved {file_path} to {archived_path}")
        
        return archived_path

    @retry(max_attempts=3, delay=5)
    def process_backup_file(self, file_path: str) -> Optional[str]:
        """Process a backup file (.dat).
        
        Restores the backup file to SQL Server.
        
        Args:
            file_path: Path to the backup file
            
        Returns:
            Optional[str]: Database name if successful, None otherwise
            
        Raises:
            FileNotFoundError: If the backup file doesn't exist
            Exception: For restore errors
        """
        try:
            # Verify file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Backup file not found: {file_path}")
                
            logger.info(f"Processing backup file: {file_path}")
            file_name = os.path.basename(file_path)
            
            # Restore backup to MSSQL
            db_info = self.restore_backup(file_path)
            if not db_info:
                logger.error(f"Failed to restore backup: {file_path}")
                return None
                
            db_name, file_list = db_info
            logger.info(f"Successfully restored backup to database '{db_name}'")
            logger.info(f"Restored {len(file_list)} database files: {', '.join(file_list)}")
            
            # Archive the processed file
            try:
                archived_path = self.archive_processed_file(file_path)
                logger.info(f"Archived backup file: {file_path} to {archived_path}")
            except Exception as e:
                logger.warning(f"Could not archive processed file: {str(e)}")
            
            return db_name
            
        except Exception as e:
            logger.exception(f"Error processing backup file {file_path}")
            raise

    @retry(max_attempts=3, delay=5)
    def restore_backup(self, backup_path: str) -> Optional[Tuple[str, List[str]]]:
        """Restore backup file to MSSQL Server.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            Optional[Tuple[str, List[str]]]: Tuple of (database_name, file_list) if successful,
                                             None otherwise
                                             
        Raises:
            FileNotFoundError: If backup file doesn't exist
            pymssql.OperationalError: If database connection fails
            Exception: For other restoration errors
        """
        conn = None
        cursor = None
        temp_backup_path = None
        db_name = None
        file_list = []
        
        try:
            # Verify backup file exists
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
                
            # Copy the backup file to the shared volume accessible by both containers
            os.makedirs(self.shared_backup_dir, exist_ok=True)
            backup_filename = os.path.basename(backup_path)
            temp_backup_path = os.path.join(self.shared_backup_dir, backup_filename)

            logger.info(f"Copying backup from {backup_path} to shared volume at {temp_backup_path}")
            shutil.copy2(backup_path, temp_backup_path)
            logger.info(f"Backup file copied successfully to shared volume")

            # The path that SQL Server will use (from its container perspective)
            sql_server_backup_path = f"{self.shared_backup_dir}/{backup_filename}"
            logger.info(f"SQL Server will access the backup at: {sql_server_backup_path}")

            # Set autocommit=True to avoid transaction issues with RESTORE operations
            conn = pymssql.connect(
                server=self.mssql_server,
                user=self.mssql_user,
                password=self.mssql_password,
                database="master",
                autocommit=True,
                timeout=self.connection_timeout,
            )
            cursor = conn.cursor(as_dict=True)
            
            # Get backup file info
            logger.info(f"Reading backup file information...")
            try:
                cursor.execute(f"RESTORE FILELISTONLY FROM DISK = %s", (sql_server_backup_path,))
                file_info = cursor.fetchall()
                
                if not file_info:
                    logger.error("No file information found in backup file")
                    return None
                    
                logger.info(f"Backup contains {len(file_info)} files")
                
                # Extract database name from first logical file
                db_name = file_info[0].get('LogicalName')
                if not db_name:
                    logger.warning("Could not determine database name from backup, using timestamp")
                    db_name = f"restored_db_{int(time.time())}"
                
                # Build file list and move commands
                move_commands = []
                for file in file_info:
                    logical_name = file.get('LogicalName')
                    file_list.append(logical_name)
                    
                    # Determine file extension based on type
                    file_type = file.get('Type')
                    ext = ".ldf" if file_type == "L" else ".mdf"
                    
                    # Create move command for this file
                    move_cmd = f"MOVE N'{logical_name}' TO N'/var/opt/mssql/data/{logical_name}{ext}'"
                    move_commands.append(move_cmd)
                
                # Join all move commands
                move_clause = ",\n".join(move_commands)
                
                # Build and execute the restore command
                restore_sql = f"""
                RESTORE DATABASE [{db_name}]
                FROM DISK = %s
                WITH REPLACE,
                RECOVERY,
                STATS = 10,
                {move_clause}
                """
                
                logger.info(f"Restoring database '{db_name}' with {len(file_list)} files")
                cursor.execute(restore_sql, (sql_server_backup_path,))
                
                # Wait for the restore to complete
                logger.info(f"Waiting for database {db_name} restore to complete...")
                self._wait_for_db_online(cursor, db_name)
                
                return db_name, file_list
                
            except pymssql.Error as e:
                logger.error(f"SQL error during restore: {str(e)}")
                # Try alternative approach with simpler restore syntax if the first approach fails
                logger.info("Attempting alternative restore approach...")
                
                # Generate a unique database name
                db_name = f"restored_db_{int(time.time())}"
                
                # Simplified restore command
                restore_sql = f"""
                RESTORE DATABASE [{db_name}]
                FROM DISK = %s
                WITH REPLACE, RECOVERY, STATS = 10
                """
                
                cursor.execute(restore_sql, (sql_server_backup_path,))
                self._wait_for_db_online(cursor, db_name)
                
                # Get the list of files after restore
                cursor.execute(f"SELECT name FROM sys.database_files WHERE database_id = DB_ID(%s)", (db_name,))
                files = cursor.fetchall()
                file_list = [f.get('name') for f in files]
                
                return db_name, file_list

        except Exception as e:
            logger.exception(f"Error restoring backup: {str(e)}")
            raise
        finally:
            # Clean up resources
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            # Clean up temporary backup file
            if temp_backup_path and os.path.exists(temp_backup_path):
                try:
                    os.remove(temp_backup_path)
                    logger.info(f"Cleaned up temporary backup file: {temp_backup_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary backup file: {str(e)}")
    
    def _wait_for_db_online(self, cursor, db_name: str, timeout: int = 300, check_interval: int = 5) -> bool:
        """Wait for a database to come online after restore.
        
        Args:
            cursor: Active database cursor
            db_name: Name of the database to check
            timeout: Maximum time to wait in seconds
            check_interval: Time between checks in seconds
            
        Returns:
            bool: True if database is online, False if timeout occurred
            
        Raises:
            TimeoutError: If database doesn't come online within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                cursor.execute(f"SELECT state_desc FROM sys.databases WHERE name = %s", (db_name,))
                result = cursor.fetchone()
                
                if not result:
                    logger.warning(f"Database {db_name} not found in sys.databases")
                    time.sleep(check_interval)
                    continue
                    
                state = result.get('state_desc')
                logger.info(f"Database {db_name} state: {state}")
                
                if state == "ONLINE":
                    logger.info(f"Database {db_name} is now ONLINE")
                    return True
                elif state == "RESTORING":
                    logger.info(f"Database {db_name} is still in RESTORING state")
                    time.sleep(check_interval)
                else:
                    logger.warning(f"Database {db_name} in unexpected state: {state}")
                    time.sleep(check_interval)
            except Exception as e:
                logger.warning(f"Error checking database state: {str(e)}")
                time.sleep(check_interval)
                
        error_msg = f"Timeout waiting for database {db_name} to come online"
        logger.error(error_msg)
        raise TimeoutError(error_msg)