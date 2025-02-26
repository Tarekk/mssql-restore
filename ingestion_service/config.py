"""
Configuration settings for the ingestion service.

This module defines all configuration settings using Pydantic classes.
It handles environment variable loading and validation.
"""

import os
from pathlib import Path
from typing import Dict, Optional, List, Any

from dotenv import load_dotenv
from pydantic import Field, SecretStr, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables
load_dotenv()


class MSSQLSettings(BaseSettings):
    """SQL Server connection settings.
    
    Attributes:
        server: SQL Server hostname or IP address
        port: SQL Server port number
        user: SQL Server authentication username
        password: SQL Server authentication password
        driver: ODBC Driver name, varies by system
        timeout: Connection timeout in seconds
    """
    server: str = Field(default="localhost", description="MSSQL server address")
    port: str = Field(default="1433", description="MSSQL server port")
    user: str = Field(default="sa", description="MSSQL username")
    password: SecretStr = Field(..., description="MSSQL password")
    driver: str = Field(
        default="{ODBC Driver 18 for SQL Server}", description="MSSQL ODBC driver"
    )
    timeout: int = Field(default=60, description="Connection timeout in seconds")

    model_config = SettingsConfigDict(
        env_prefix="MSSQL_", extra="ignore", env_file=".env"
    )
    
    def get_connection_string(self) -> str:
        """Generate a connection string for pyodbc.
        
        Returns:
            str: A formatted connection string
        """
        return (
            f"DRIVER={self.driver};"
            f"SERVER={self.server},{self.port};"
            f"UID={self.user};"
            f"PWD={self.password.get_secret_value()};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={self.timeout}"
        )


class BackupSettings(BaseSettings):
    """Backup processing settings.
    
    Attributes:
        shared_dir: Shared directory path for database backups
        file_patterns: List of file extensions to monitor
        archive_processed: Whether to archive processed files 
        retry_attempts: Number of retry attempts for failed operations
        retry_delay: Delay between retry attempts in seconds
    """
    shared_dir: str = Field(
        default="/shared_backup", 
        description="Shared directory for database backup files"
    )
    file_patterns: List[str] = Field(
        default=[".rar", ".dat"], 
        description="File extensions to monitor"
    )
    archive_processed: bool = Field(
        default=True,
        description="Archive processed files after successful processing"
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed operations"
    )
    retry_delay: int = Field(
        default=5,
        description="Delay between retry attempts in seconds"
    )
    
    model_config = SettingsConfigDict(
        env_prefix="BACKUP_", extra="ignore", env_file=".env"
    )


class LoggingSettings(BaseSettings):
    """Logging configuration settings.
    
    Attributes:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        directory: Directory to store log files
        max_size_mb: Maximum size of log file before rotation
        backup_count: Number of rotated log files to keep
        json_format: Whether to use JSON formatted logs
    """
    level: str = Field(default="INFO", description="Logging level")
    directory: str = Field(default="logs", description="Log directory")
    max_size_mb: int = Field(default=10, description="Max log file size in MB")
    backup_count: int = Field(default=5, description="Number of log backups to keep")
    json_format: bool = Field(default=True, description="Use JSON formatted logs")
    
    model_config = SettingsConfigDict(
        env_prefix="LOG_", extra="ignore", env_file=".env"
    )
    
    @validator("level")
    def validate_log_level(cls, v):
        """Validate that the log level is one of the supported values."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of: {', '.join(allowed_levels)}")
        return v.upper()


class AppSettings(BaseSettings):
    """Application settings.
    
    Attributes:
        watch_dir: Directory to monitor for backup files
        polling_interval: Interval in seconds between file system checks
        log_level: Application logging level
        mssql: SQL Server connection settings
        backup: Backup processing settings
        logging: Logging configuration settings
    """
    watch_dir: str = Field(
        default=os.environ.get('BACKUP_WATCH_DIR', '/data/backups'),
        description="Directory to watch for backup files"
    )
    polling_interval: float = Field(
        default=1.0,
        description="Polling interval in seconds"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # Component settings
    mssql: MSSQLSettings = Field(default_factory=MSSQLSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Instantiate settings
settings = AppSettings()

# Base paths
BASE_DIR = Path(__file__).parent.parent
WATCH_DIR = settings.watch_dir

# For backward compatibility
MSSQL_CONFIG = {
    "server": settings.mssql.server,
    "port": settings.mssql.port,
    "user": settings.mssql.user,
    "password": settings.mssql.password.get_secret_value(),
    "driver": settings.mssql.driver,
    "timeout": settings.mssql.timeout,
}

# Logging configuration
LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": settings.log_level,
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": f"{settings.logging.directory}/ingestion.log",
            "maxBytes": settings.logging.max_size_mb * 1024 * 1024,
            "backupCount": settings.logging.backup_count,
            "formatter": "json" if settings.logging.json_format else "standard",
            "level": settings.log_level,
        },
    },
    "loggers": {"": {"handlers": ["console", "file"], "level": settings.log_level}},
}