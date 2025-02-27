"""
Configuration settings for the MSSQL backup tool.

This module defines all configuration settings using Pydantic classes.
"""

from typing import List

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables
load_dotenv()


class MSSQLSettings(BaseSettings):
    """SQL Server connection settings."""

    server: str = Field(default="localhost", description="MSSQL server address")
    port: str = Field(default="1433", description="MSSQL server port")
    user: str = Field(default="sa", description="MSSQL username")
    password: SecretStr = Field(..., description="MSSQL password")
    timeout: int = Field(default=60, description="Connection timeout in seconds")

    model_config = SettingsConfigDict(
        env_prefix="MSSQL_", extra="ignore", env_file=".env"
    )

    def get_connection_dict(self) -> dict:
        """Get connection parameters as a dictionary."""
        return {
            "server": self.server,
            "port": self.port,
            "user": self.user,
            "password": self.password.get_secret_value(),
            "timeout": self.timeout,
        }


class BackupSettings(BaseSettings):
    """Backup processing settings."""

    shared_dir: str = Field(
        default="/shared_backup",
        description="Shared directory for database backup files",
    )
    file_patterns: List[str] = Field(
        default=[".rar", ".dat"], description="File extensions to monitor"
    )
    archive_processed: bool = Field(
        default=True, description="Archive processed files after successful processing"
    )
    retry_attempts: int = Field(
        default=3, description="Number of retry attempts for failed operations"
    )
    retry_delay: int = Field(
        default=5, description="Delay between retry attempts in seconds"
    )

    model_config = SettingsConfigDict(
        env_prefix="BACKUP_", extra="ignore", env_file=".env"
    )


class LoggingSettings(BaseSettings):
    """Logging configuration settings."""

    level: str = Field(default="INFO", description="Logging level")
    directory: str = Field(default="logs", description="Log directory")
    max_size_mb: int = Field(default=10, description="Max log file size in MB")
    backup_count: int = Field(default=5, description="Number of log backups to keep")
    json_format: bool = Field(default=True, description="Use JSON formatted logs")

    model_config = SettingsConfigDict(
        env_prefix="LOG_", extra="ignore", env_file=".env"
    )

    def validate_log_level(self) -> str:
        """Validate that the log level is one of the supported values."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.level.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of: {', '.join(allowed_levels)}")
        return self.level.upper()


class AppSettings(BaseSettings):
    """Application settings."""

    watch_dir: str = Field(
        default="/data/backups",
        description="Directory to watch for backup files",
    )
    polling_interval: float = Field(
        default=1.0, description="Polling interval in seconds"
    )

    # Component settings
    mssql: MSSQLSettings = Field(default_factory=MSSQLSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    def get_logging_config(self) -> dict:
        """Get logging configuration dictionary."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                },
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": self.logging.validate_log_level(),
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": f"{self.logging.directory}/tool.log",
                    "maxBytes": self.logging.max_size_mb * 1024 * 1024,
                    "backupCount": self.logging.backup_count,
                    "formatter": "json" if self.logging.json_format else "standard",
                    "level": self.logging.validate_log_level(),
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console", "file"],
                    "level": self.logging.validate_log_level(),
                }
            },
        }


# Create global settings instance
settings = AppSettings()
