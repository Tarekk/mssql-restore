# MSSQL Backup Ingestion Service

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A robust, production-ready service for automated processing of MSSQL backup files. The service monitors directories for new backup files (RAR or DAT), extracts them if necessary, restores them to a running SQL Server instance, and archives processed files locally.

## 🚀 Features

  - **Automatic Monitoring**: Monitors directories for new backup files
  - **Format Support**: Processes both RAR archives and DAT backup files
  - **Extraction & Restoration**: Automatically extracts archives and restores databases
  - **Local Archiving**: Archives processed files with timestamps
  - **Resilient Processing**: Includes retry logic for transient failures
  - **Flexible Callback System**: Customizable status callbacks for integration with any system
  - **Graceful Shutdown**: Handles termination signals for clean shutdowns
  - **Comprehensive Logging**: Detailed, configurable logging with rotation
  - **Docker Ready**: Optimized for containerized deployments

## 📋 Installation

### Clone Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/mssql-backup-ingestion.git
cd mssql-backup-ingestion

# Install dependencies
pip install -r requirements.txt
```

### Using Docker

```bash
# Build the Docker image
docker build -t mssql-backup-ingestion -f Dockerfile .

# Run the container
docker run -v /path/to/backups:/data/backups \
           -e MSSQL_SERVER=mssql \
           -e MSSQL_PASSWORD=yourpassword \
           mssql-backup-ingestion
```

## 🛠️ Configuration

Configuration is handled through environment variables or a `.env` file:

### Core Settings

| Environment Variable   | Description                               | Default          |
| ---------------------- | ----------------------------------------- | ---------------- |
| `BACKUP_WATCH_DIR`     | Directory to monitor for new backup files | `/data/backups`  |
| `BACKUP_SHARED_DIR`    | Shared directory for database backups     | `/shared_backup` |
| `APP_POLLING_INTERVAL` | Interval in seconds between file checks   | `1.0`            |
| `APP_LOG_LEVEL`        | Logging level                             | `INFO`           |

### MSSQL Settings

| Environment Variable | Description                   | Default     |
| -------------------- | ----------------------------- | ----------- |
| `MSSQL_SERVER`       | MSSQL server hostname or IP   | `localhost` |
| `MSSQL_PORT`         | MSSQL server port             | `1433`      |
| `MSSQL_USER`         | MSSQL username                | `sa`        |
| `MSSQL_PASSWORD`     | MSSQL password                | (Required)  |
| `MSSQL_TIMEOUT`      | Connection timeout in seconds | `60`        |

### Logging Settings

| Environment Variable | Description                   | Default |
| -------------------- | ----------------------------- | ------- |
| `LOG_LEVEL`          | Logging level                 | `INFO`  |
| `LOG_DIRECTORY`      | Directory for log files       | `logs`  |
| `LOG_MAX_SIZE_MB`    | Maximum log file size in MB   | `10`    |
| `LOG_BACKUP_COUNT`   | Number of log backups to keep | `5`     |
| `LOG_JSON_FORMAT`    | Use JSON formatted logs       | `true`  |

## 📝 Usage

### Running as a Service

```bash
# Run with default settings
python -m ingestion_service

# Run with custom settings
BACKUP_WATCH_DIR=/path/to/backups MSSQL_SERVER=localhost python -m ingestion_service
```

### Programmatic Usage

```python
from ingestion_service.core.monitor import BackupMonitor

# Initialize the monitor
monitor = BackupMonitor(
    mssql_settings=mssql_settings,
    watch_directory="/path/to/backups",
    shared_backup_dir="/shared_backup",
    polling_interval=1.0,
    file_patterns=[".rar", ".dat"]
)

# Start monitoring (this will block until stopped)
monitor.start()
```

### Using the Callback API

The service provides a flexible callback system for status updates:

```python
def my_status_callback(filename, status, details, metadata=None):
    """Custom status callback for processing events."""
    print(f"File {filename} status: {status} - {details}")
    if metadata:
        print(f"Additional metadata: {metadata}")

    # Send to a database, API, message queue, etc.
    if status == "completed":
        notify_admin(f"Database {metadata.get('database_name')} restored successfully")
    elif status == "failed":
        alert_system(f"Backup processing failed: {details}")

# Use the callback with the monitor
monitor = BackupMonitor(
    # ... other settings ...
    status_callback=my_status_callback
)
```

The callback system uses the following status codes:

| Status       | Description                                       |
| ------------ | ------------------------------------------------- |
| `processing` | File has been detected and processing has started |
| `completed`  | File processing completed successfully            |
| `failed`     | Processing failed with an error                   |

## 🔒 Security Considerations

  - Secure your SQL Server passwords
  - Use environment variables rather than hardcoded credentials
  - Consider using a secrets management system in production
  - Implement network-level security for service communication
  - Review file permissions on backup directories

## 🐳 Docker Compose Example

```yaml
version: "3.8"

services:
  mssql:
    image: mcr.microsoft.com/mssql/server:2019-latest
    environment:
      - ACCEPT_EULA=Y
      - SA_PASSWORD=${MSSQL_PASSWORD}
    ports:
      - "${MSSQL_PORT}:1433"
    volumes:
      - ./data/mssql:/var/opt/mssql/data
      - shared_backup_volume:/shared_backup

  ingestion:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ${BACKUP_WATCH_DIR:-./data/backups}:/data/backups
      - shared_backup_volume:/shared_backup
    environment:
      - MSSQL_SERVER=mssql
      - MSSQL_PASSWORD=${MSSQL_PASSWORD}
    depends_on:
      - mssql

volumes:
  shared_backup_volume:
```

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📊 Architecture

```
┌─────────────────┐         ┌─────────────────┐
│                 │         │                 │
│  Backup Files   │────────▶│  Watch Directory│
│                 │         │                 │
└─────────────────┘         └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │                 │
                            │  Ingestion      │
                            │  Service        │
                            │                 │
                            └────────┬────────┘
                                     │
                                     ▼
┌─────────────────┐         ┌─────────────────┐
│                 │         │                 │
│  Status Updates │◀────────│  MSSQL Server   │
│  (Callbacks)    │         │                 │
└─────────────────┘         └─────────────────┘
```

