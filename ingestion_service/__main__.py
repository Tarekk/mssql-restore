"""
Main entry point for the MSSQL backup ingestion service.

This module initializes logging, validates configuration,
and starts the backup monitor process.
"""

import logging.config
import os
import signal
import sys
from pathlib import Path
from typing import Optional

from ingestion_service.config import LOGGING_CONFIG, settings
from ingestion_service.core.monitor import BackupMonitor


# Global variable to hold the monitor instance for graceful shutdown
monitor: Optional[BackupMonitor] = None


def signal_handler(sig, frame):
    """Handle termination signals for graceful shutdown.
    
    Args:
        sig: Signal number
        frame: Current stack frame
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {sig}, shutting down gracefully...")
    
    if monitor:
        logger.info("Stopping backup monitor...")
        monitor.stop()
    
    logger.info("Ingestion service shutdown complete")
    sys.exit(0)


def setup_directories():
    """Create required directories for the application."""
    # Create logs directory
    log_dir = Path(settings.logging.directory)
    log_dir.mkdir(exist_ok=True)
    
    # Create watch directory
    os.makedirs(settings.watch_dir, exist_ok=True)
    
    # Create shared backup directory if configured
    os.makedirs(settings.backup.shared_dir, exist_ok=True)


def log_startup_info():
    """Log startup information and configuration details."""
    logger = logging.getLogger(__name__)
    
    logger.info("-" * 50)
    logger.info("Ingestion Service Starting")
    logger.info("-" * 50)
    
    # Log configuration details
    logger.info(f"Version: {getattr(sys.modules['ingestion_service'], '__version__', 'unknown')}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Watch directory: {settings.watch_dir}")
    logger.info(f"Polling interval: {settings.polling_interval} seconds")
    logger.info(f"MSSQL server: {settings.mssql.server}:{settings.mssql.port}")
    logger.info(f"Log level: {settings.log_level}")
    
    # Log file patterns being watched
    logger.info(f"Watching for file patterns: {settings.backup.file_patterns}")


def main():
    """Main entry point for the ingestion service."""
    global monitor
    
    # Create required directories
    setup_directories()
    
    # Configure logging
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(__name__)
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Log startup information
    log_startup_info()
    
    # Log existing files in watch directory
    try:
        files = os.listdir(settings.watch_dir)
        if files:
            logger.info(f"Found {len(files)} files in watch directory")
            if len(files) <= 10:  # Only log details if there aren't too many files
                logger.info(f"Files in watch directory: {files}")
            else:
                logger.info(f"First 10 files in watch directory: {files[:10]}...")
    except OSError as e:
        logger.error(f"Error accessing watch directory: {str(e)}")
        sys.exit(1)

    try:
        # Initialize and start the backup monitor
        logger.info("Initializing backup monitor...")
        
        monitor = BackupMonitor(
            mssql_settings=settings.mssql,
            watch_directory=settings.watch_dir,
            shared_backup_dir=settings.backup.shared_dir,
            polling_interval=settings.polling_interval,
            file_patterns=settings.backup.file_patterns
        )
        
        # Start monitoring (this will block until interrupted)
        monitor.start()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Error starting ingestion service: {str(e)}")
        logger.exception("Full stack trace:")
        sys.exit(1)


if __name__ == "__main__":
    main()