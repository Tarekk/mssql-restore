"""
Backup directory monitoring service.

This script continuously monitors a directory for new backup files
and processes them using the backup processor.
"""

import json
import logging
import os
import sys
import time
from typing import Dict, List, Set

from .backup_processor import BackupProcessor
from .config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.environ.get("APP_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class BackupMonitor:
    """Monitors a directory for backup files and processes them."""

    def __init__(
        self,
        watch_dir: str = None,
        file_patterns: List[str] = None,
        polling_interval: float = 1.0,
    ):
        """
        Initialize the monitor.

        Args:
            watch_dir: Directory to watch for files
            file_patterns: File extensions to watch for
            polling_interval: Time between checks in seconds
        """
        self.watch_dir = watch_dir or settings.watch_dir
        self.file_patterns = file_patterns or settings.backup.file_patterns
        self.polling_interval = polling_interval or settings.polling_interval
        if hasattr(settings.mssql, "get_connection_params"):
            mssql_settings_dict = settings.mssql.get_connection_params()
            mssql_settings_dict.update(
                {
                    "retry_attempts": settings.backup.retry_attempts,
                    "retry_delay": settings.backup.retry_delay,
                }
            )
        elif hasattr(settings.mssql, "model_dump"):
            mssql_settings_dict = settings.mssql.model_dump()
            mssql_settings_dict.update(
                {
                    "retry_attempts": settings.backup.retry_attempts,
                    "retry_delay": settings.backup.retry_delay,
                }
            )
        else:
            # Manual conversion
            mssql_settings_dict = {
                "server": settings.mssql.server,
                "port": settings.mssql.port,
                "user": settings.mssql.user,
                "password": settings.mssql.password.get_secret_value(),
                "timeout": settings.mssql.timeout,
                "retry_attempts": settings.backup.retry_attempts,
                "retry_delay": settings.backup.retry_delay,
            }

        self.processor = BackupProcessor(
            mssql_settings=mssql_settings_dict,
            shared_backup_dir=settings.backup.shared_dir,
            progress_callback=self._progress_callback,
        )
        self.processed_files: Set[str] = set()

        # Ensure watch directory exists
        if not os.path.exists(self.watch_dir):
            os.makedirs(self.watch_dir, exist_ok=True)

        logger.info(
            f"Starting backup monitor watching {self.watch_dir} "
            f"for patterns {self.file_patterns}"
        )

    def _progress_callback(self, status: str, message: str, data: Dict) -> None:
        """Callback for processing progress updates."""
        output = {
            "status": status,
            "message": message,
            "data": data,
        }
        logger.info(f"Processing update: {message}")

        # Print to stdout as JSON for potential consumers
        print(json.dumps(output), flush=True)

    def _find_backup_files(self) -> List[str]:
        """
        Find backup files in the watch directory.

        Returns:
            List[str]: List of file paths
        """
        if not os.path.exists(self.watch_dir):
            logger.warning(f"Watch directory does not exist: {self.watch_dir}")
            return []

        files = []
        for filename in os.listdir(self.watch_dir):
            # Skip files we've already processed
            if filename in self.processed_files:
                continue

            # Skip files that don't match our patterns
            if not any(filename.lower().endswith(ext) for ext in self.file_patterns):
                continue

            file_path = os.path.join(self.watch_dir, filename)

            # Only include files (not directories)
            if os.path.isfile(file_path):
                files.append(file_path)

        return files

    def process_file(self, file_path: str) -> bool:
        """
        Process a single backup file.

        Args:
            file_path: Path to the backup file

        Returns:
            bool: True if processing succeeded, False otherwise
        """
        filename = os.path.basename(file_path)
        logger.info(f"Processing new backup file: {filename}")

        try:
            result = self.processor.process_backup(
                file_path,
                archive_processed=settings.backup.archive_processed,
            )

            logger.info(f"Successfully restored database: {result['database_name']}")
            self.processed_files.add(filename)
            return True

        except Exception as e:
            logger.error(f"Failed to process backup file {filename}: {str(e)}")
            # Don't add to processed_files so we can retry
            return False

    def run(self) -> None:
        """Run the monitor continuously."""
        logger.info(f"Monitoring {self.watch_dir} for backup files")

        try:
            while True:
                files = self._find_backup_files()

                for file_path in files:
                    self.process_file(file_path)

                time.sleep(self.polling_interval)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring stopped due to error: {str(e)}")
            raise


def main() -> int:
    """Main entry point for the monitor service."""
    try:
        monitor = BackupMonitor()
        monitor.run()
        return 0
    except Exception as e:
        logger.exception(f"Unhandled exception: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

