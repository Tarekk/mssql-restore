"""
Main entry point for the MSSQL Backup Tool when run as a module.
"""

import os
import sys

from .monitor import main as monitor_main
from .mssql_tool import main as tool_main


def main():
    """
    Main entry point for the package when run as a module.
    This function is called when running `python -m tool`.

    By default, it runs the monitoring service. To use the CLI tool,
    set the environment variable TOOL_MODE=cli.
    """
    mode = os.environ.get("TOOL_MODE", "monitor").lower()

    if mode == "cli":
        # Run the CLI tool (stdin/stdout protocol)
        return tool_main()
    else:
        # Run the monitoring service by default
        return monitor_main()


if __name__ == "__main__":
    sys.exit(main())

