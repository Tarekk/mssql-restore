"""
Backup file monitoring service.

This module contains the main monitoring logic for detecting and processing
MSSQL backup files, either from a directory or using filesystem events.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Union

from pydantic import SecretStr
from watchdog.observers import Observer
from watchdog.events import FileCreatedEvent

from ingestion_service.core.backup_handler import BackupFileHandler

# Configure logging
logger = logging.getLogger(__name__)


class BackupMonitor:
    """Monitor a directory for backup files and process them.

    This class provides both event-based and polling-based monitoring of
    a directory for new backup files, processing them using a BackupFileHandler
    instance.

    Attributes:
        watch_directory: Directory to monitor for new backup files
        shared_backup_dir: Directory to store extracted backup files
        polling_interval: Time between checks for new files (in seconds)
        file_patterns: List of file extensions to process
        observer: Watchdog observer for file system events
        handler: Handler for processing backup files
        running: Flag indicating whether the monitor is currently running
        _stop_event: Threading event for signaling the monitor to stop
    """

    def __init__(
        self,
        mssql_settings: Any,
        watch_directory: str,
        shared_backup_dir: str = "/shared_backup",
        polling_interval: float = 1.0,
        file_patterns: Optional[List[str]] = None,
        status_callback: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
    ):
        """Initialize the backup monitor.

        Args:
            mssql_settings: SQL Server connection settings
            watch_directory: Directory to monitor for backup files
            shared_backup_dir: Directory to store extracted backup files
            polling_interval: Interval between checks for new files (in seconds)
            file_patterns: List of file extensions to process (default: [".rar", ".dat"])
            status_callback: Optional callback for status updates
        
        Raises:
            FileNotFoundError: If watch_directory does not exist and cannot be created
            ValueError: If mssql_settings is invalid
        """
        self.watch_directory = watch_directory
        self.shared_backup_dir = shared_backup_dir
        self.polling_interval = polling_interval
        self.file_patterns = file_patterns or [".rar", ".dat"]
        self.status_callback = status_callback
        self.observer = None
        self.handler = None
        self.running = False
        self._stop_event = threading.Event()

        # Validate and create watch directory
        watch_path = Path(watch_directory)
        try:
            watch_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create watch directory {watch_directory}: {e}")
            raise FileNotFoundError(f"Failed to create watch directory: {e}")

        # Validate and create shared backup directory
        shared_path = Path(shared_backup_dir)
        try:
            shared_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create shared backup directory {shared_backup_dir}: {e}")
            raise FileNotFoundError(f"Failed to create shared backup directory: {e}")

        try:
            # Get password secret value if it's a SecretStr
            mssql_password = (
                mssql_settings.password.get_secret_value()
                if isinstance(mssql_settings.password, SecretStr)
                else mssql_settings.password
            )
            
            # Initialize backup handler
            self.handler = BackupFileHandler(
                mssql_settings.server,
                mssql_settings.user,
                mssql_password,
                status_callback,
                shared_backup_dir=shared_backup_dir,
                file_patterns=self.file_patterns,
                connection_timeout=getattr(mssql_settings, "timeout", 60),
            )
            
        except Exception as e:
            logger.exception(f"Error initializing backup monitor: {e}")
            raise

    def start(self) -> None:
        """Start monitoring for new backup files.
        
        This method starts a watchdog observer to detect new files
        and then processes any existing files in the directory.
        
        The method will block until stop() is called or an exception occurs.
        """
        if self.running:
            logger.warning("Backup monitor is already running")
            return
            
        self.running = True
        self._stop_event.clear()
        
        # Start watchdog observer
        logger.info(f"Starting file system observer for {self.watch_directory}")
        self.observer = Observer()
        self.observer.schedule(self.handler, self.watch_directory, recursive=False)
        self.observer.start()
        
        # Process existing files
        self._process_existing_files()
        
        # Main monitoring loop
        logger.info("Backup monitor running, press Ctrl+C to stop")
        try:
            while not self._stop_event.is_set():
                time.sleep(self.polling_interval)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()
        except Exception as e:
            logger.error(f"Error in backup monitor: {str(e)}")
            self.stop()
            raise
        finally:
            if self.observer and self.observer.is_alive():
                self.observer.stop()
                self.observer.join()
            self.running = False

    def stop(self) -> None:
        """Stop the backup monitor gracefully."""
        if not self.running:
            return
            
        logger.info("Stopping backup monitor...")
        self._stop_event.set()
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
            
        self.running = False
        logger.info("Backup monitor stopped")

    def _process_existing_files(self) -> None:
        """Process any existing files in the watch directory."""
        logger.info(f"Checking for existing files in {self.watch_directory}")
        try:
            for filename in os.listdir(self.watch_directory):
                file_path = os.path.join(self.watch_directory, filename)
                if not os.path.isfile(file_path):
                    continue
                    
                # Check if file matches supported patterns
                if not any(filename.lower().endswith(pattern) for pattern in self.file_patterns):
                    logger.debug(f"Skipping file with unsupported extension: {filename}")
                    continue
                    
                logger.info(f"Processing existing file: {file_path}")
                # Create a synthetic event for the handler
                event = FileCreatedEvent(file_path)
                self.handler.dispatch(event)
        except OSError as e:
            logger.error(f"Error listing files in watch directory: {e}")


# For backward compatibility
def start_backup_monitor(
    mssql_server: str,
    mssql_user: str,
    mssql_password: Union[str, SecretStr],
    watch_directory: str,
    status_callback: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
) -> None:
    """
    Legacy function to start the backup file monitoring service.
    
    This function exists for backward compatibility and delegates to the
    BackupMonitor class.
    
    Args:
        mssql_server: MSSQL server address
        mssql_user: MSSQL username
        mssql_password: MSSQL password
        watch_directory: Directory to monitor for backup files
        status_callback: Optional callback function for status updates
        
    Returns:
        None
    """
    # Create settings objects for compatibility
    class MSSQLSettings:
        def __init__(self):
            self.server = mssql_server
            self.user = mssql_user
            self.password = mssql_password
            self.timeout = 60
            
    logger.warning("Using deprecated start_backup_monitor function. Consider using BackupMonitor class instead.")
    
    # Create and start the monitor
    monitor = BackupMonitor(
        mssql_settings=MSSQLSettings(),
        watch_directory=watch_directory,
        status_callback=status_callback,
    )
    
    monitor.start()