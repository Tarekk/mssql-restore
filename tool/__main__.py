"""
Main entry point for the MSSQL Backup Tool.
"""

import sys

from .mssql_tool import main as tool_main

if __name__ == "__main__":
    sys.exit(tool_main())

