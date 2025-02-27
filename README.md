# MSSQL Backup Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A tool for processing MSSQL backup files following Unix philosophy principles. The tool accepts input via STDIN and produces output via STDOUT in a structured JSON format.

## 🚀 Features

  - **Uniform Interface**: Uses structured JSON I/O following Unix pipe principles
  - **Flexible Resource Handling**: Supports various input sources (local files, HTTP, S3)
  - **Standardized Error Handling**: Consistent error reporting and exit codes
  - **Format Support**: Processes both RAR archives and DAT backup files
  - **Extraction & Restoration**: Automatically extracts archives and restores databases
  - **Comprehensive Logging**: Detailed, configurable logging

## 📋 Installation

### Clone Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/mssql-backup-tool.git
cd mssql-backup-tool

# Install dependencies
pip install -r requirements.txt
```

### Using Docker

```bash
# Build the Docker image
docker build -t mssql-backup-tool -f Dockerfile .

# Run the container with a command
cat restore_command.json | docker run -i \
    -v /path/to/backups:/data/backups \
    -e MSSQL_SERVER=mssql \
    -e MSSQL_PASSWORD=yourpassword \
    mssql-backup-tool
```

## 🛠️ Configuration

Configuration is handled through environment variables or a `.env` file:

### Core Settings

| Environment Variable | Description                           | Default          |
| -------------------- | ------------------------------------- | ---------------- |
| `BACKUP_SHARED_DIR`  | Shared directory for database backups | `/shared_backup` |
| `LOG_LEVEL`          | Logging level                         | `INFO`           |

### MSSQL Settings

| Environment Variable | Description                   | Default     |
| -------------------- | ----------------------------- | ----------- |
| `MSSQL_SERVER`       | MSSQL server hostname or IP   | `localhost` |
| `MSSQL_PORT`         | MSSQL server port             | `1433`      |
| `MSSQL_USER`         | MSSQL username                | `sa`        |
| `MSSQL_PASSWORD`     | MSSQL password                | (Required)  |
| `MSSQL_TIMEOUT`      | Connection timeout in seconds | `60`        |

## 📝 Usage

### Using the CLI Tool

The tool accepts JSON commands via STDIN and outputs JSON results via STDOUT:

```bash
# Restore a local backup file
echo '{"command": "restore", "resource": "file:///path/to/backup.dat", "options": {"database_name": "my_database"}}' | python -m tool

# Restore a backup from an HTTP URL
echo '{"command": "restore", "resource": "https://example.com/backup.rar"}' | python -m tool
```

### Command Format

```json
{
  "command": "restore",
  "resource": "resource_uri",
  "options": {
    "database_name": "optional_target_name",
    "archive_processed": true
  }
}
```

### Resource URI Formats

  - Local file: `file:///path/to/backup.dat`
  - HTTP(S): `https://example.com/backup.rar`
  - S3: `s3://bucket/path/to/backup.dat?region=us-west-2`

### Output Format

The tool outputs structured JSON messages:

```json
{
  "type": "progress|result|error",
  "timestamp": "ISO8601 timestamp",
  "status": "processing|success|failed",
  "message": "Human-readable message",
  "data": {
    /* type-specific payload */
  }
}
```

### Exit Codes

  - `0`: Success
  - `1`: General error
  - `130`: Interrupted (SIGINT)

## 🐳 Docker Compose Example

```yaml
version: "3.8"

services:
  mssql:
    image: mcr.microsoft.com/mssql/server:2019-latest
    environment:
      - ACCEPT_EULA=Y
      - SA_PASSWORD=${MSSQL_PASSWORD:-YourPassword123!}
    ports:
      - "${MSSQL_PORT:-1433}:1433"
    volumes:
      - ./data/mssql:/var/opt/mssql/data
      - shared_backup_volume:/shared_backup

  backup-tool:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./data_backups:/data/input
      - shared_backup_volume:/shared_backup
    environment:
      - MSSQL_SERVER=mssql
      - MSSQL_USER=sa
      - MSSQL_PASSWORD=${MSSQL_PASSWORD:-YourPassword123!}
      - BACKUP_SHARED_DIR=/shared_backup
    # This service is designed to be invoked via Docker exec with STDIN

volumes:
  shared_backup_volume:
```

## 🤝 Contributing

Contributions are welcome!

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
