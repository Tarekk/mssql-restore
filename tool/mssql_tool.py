#!/usr/bin/env python3
"""
MSSQL Backup Tool - A Unix philosophy-based tool for MSSQL backup restoration.

This tool follows a strict protocol of accepting commands via STDIN and
producing structured output via STDOUT, making it composable with other tools.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .backup_processor import BackupProcessor
from .config import settings
from .resource_resolver import ResourceResolver

# Configure logging to file, not stdout (to avoid interfering with JSON output)
logging.basicConfig(
    level=getattr(logging, os.environ.get("TOOL_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler("mssql_tool.log")],
)
logger = logging.getLogger(__name__)


def output_message(
    msg_type: str, status: str, message: str, data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Output a structured message to STDOUT.

    Args:
        msg_type: Message type (progress, result, error)
        status: Status (processing, success, failed)
        message: Human-readable message
        data: Optional data payload
    """
    output = {
        "type": msg_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
    }

    if data:
        output["data"] = data

    # Write to STDOUT as a single line
    sys.stdout.write(json.dumps(output) + "\n")
    sys.stdout.flush()


def process_restore_command(command: Dict[str, Any]) -> int:
    """
    Process a restore command.

    Args:
        command: Command dictionary from STDIN

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    resource_uri = command.get("resource")
    if not resource_uri:
        output_message(
            "error", "failed", "Missing resource URI", {"code": "MISSING_RESOURCE"}
        )
        return 1

    options = command.get("options", {})

    try:
        # Resolve the resource
        output_message("progress", "processing", f"Resolving resource: {resource_uri}")

        resolver = ResourceResolver()
        resource_path = resolver.resolve(resource_uri)

        # Process the backup
        if hasattr(settings.mssql, "get_connection_params"):
            # Use the provided method to get a dictionary
            mssql_settings_dict = settings.mssql.get_connection_params()
            # Add retry parameters from backup settings
            mssql_settings_dict.update(
                {
                    "retry_attempts": settings.backup.retry_attempts,
                    "retry_delay": settings.backup.retry_delay,
                }
            )
        else:
            # Convert model to dictionary if needed
            if hasattr(settings.mssql, "model_dump"):
                mssql_settings_dict = settings.mssql.model_dump()
            elif hasattr(settings.mssql, "dict"):
                mssql_settings_dict = settings.mssql.dict()
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

        processor = BackupProcessor(
            mssql_settings=mssql_settings_dict,
            shared_backup_dir=settings.backup.shared_dir,
            progress_callback=lambda status, msg, data: output_message(
                "progress", status, msg, data
            ),
        )

        result = processor.process_backup(
            resource_path,
            target_db_name=options.get("database_name"),
            archive_processed=options.get("archive_processed", True),
        )

        # Report success
        output_message(
            "result",
            "success",
            f"Successfully restored database {result['database_name']}",
            result,
        )
        return 0

    except Exception as e:
        logger.exception(f"Error processing restore command")
        output_message(
            "error",
            "failed",
            str(e),
            {
                "code": type(e).__name__,
                "details": {"resource": resource_uri, "error": str(e)},
            },
        )
        return 1


def main() -> int:
    """
    Main entry point for the MSSQL tool.

    Reads a command from STDIN, processes it, and outputs result to STDOUT.

    Returns:
        int: Exit code
    """
    try:
        # Check if STDIN has data (non-blocking)
        import select

        if not select.select([sys.stdin], [], [], 0.0)[0]:
            # No input waiting, but we're in CLI mode
            output_message(
                "error",
                "failed",
                "No input on STDIN. Use pipe to send commands or set TOOL_MODE=monitor.",
                {"code": "NO_INPUT"},
            )
            return 1

        # Read command from STDIN
        command_str = sys.stdin.read().strip()
        if not command_str:
            output_message(
                "error",
                "failed",
                "Empty command received on STDIN",
                {"code": "EMPTY_COMMAND"},
            )
            return 1

        # Parse command as JSON
        try:
            command = json.loads(command_str)
        except json.JSONDecodeError:
            output_message(
                "error", "failed", "Invalid JSON command", {"code": "INVALID_JSON"}
            )
            return 1

        # Process command based on type
        command_type = command.get("command", "").lower()
        if command_type == "restore":
            return process_restore_command(command)
        else:
            output_message(
                "error",
                "failed",
                f"Unknown command: {command_type}",
                {"code": "UNKNOWN_COMMAND"},
            )
            return 1

    except KeyboardInterrupt:
        output_message(
            "error", "failed", "Operation interrupted", {"code": "INTERRUPTED"}
        )
        return 130
    except Exception as e:
        logger.exception("Unhandled exception")
        output_message(
            "error", "failed", f"Unhandled error: {str(e)}", {"code": "UNHANDLED_ERROR"}
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
