"""
MSSQL Backup Ingestion Service.

A robust service for monitoring, processing, and restoring MSSQL backup files.
The service monitors directories for new backup files (RAR or DAT), extracts them
if necessary, and restores them to a running SQL Server instance.
"""

__version__ = "0.1.0"