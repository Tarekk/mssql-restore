"""
MSSQL Backup Tool - A Unix philosophy-based tool for MSSQL backup restoration.

This tool follows a strict protocol of accepting commands via STDIN and
producing structured output via STDOUT, making it composable with other tools.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .backup_processor import BackupProcessor
from .config import settings
from .resource_resolver import ResourceResolver

# Configure logging to file, not stdout (to avoid interfering with JSON output)
logging.basicConfig(**settings.get_logging_config())
logger = logging.getLogger(__name__)


def output_message(
    msg_type: str, status: str, message: str, data: Optional[Dict[str, Any]] = None
) -> None:
    """Output a structured message to STDOUT."""
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
    """Process a restore command."""
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

        # Set up connection dictionary with retry parameters
        mssql_connection = settings.mssql.get_connection_dict()
        mssql_connection.update(
            {
                "retry_attempts": settings.backup.retry_attempts,
                "retry_delay": settings.backup.retry_delay,
            }
        )

        # Process the backup
        processor = BackupProcessor(
            mssql_settings=mssql_connection,
            shared_backup_dir=settings.backup.shared_dir,
            progress_callback=lambda status, msg, data: output_message(
                "progress", status, msg, data
            ),
        )

        result = processor.process_backup(
            resource_path,
            target_db_name=options.get("database_name"),
            archive_processed=options.get(
                "archive_processed", settings.backup.archive_processed
            ),
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
        logger.exception("Error processing restore command")
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
    """Main entry point for the MSSQL tool."""
    try:
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
