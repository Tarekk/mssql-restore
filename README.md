# MSSQL Restore Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A tool for restoring MSSQL database backups. Follows Unix philosophy with standardized JSON I/O that makes it composable with other tools.

## 🚀 Features

- **Dual Operation Modes**: Run as a file monitor or CLI tool
- **Docker-ready**: Designed to run in containers with MSSQL
- **Automatic Extraction**: Handles RAR archives containing database backups
- **Flexible Input**: Supports various resource types (local files, HTTP, S3)
- **Structured JSON I/O**: Clean input/output format for easy integration

## 🐳 Docker Setup (Recommended)

The recommended way to use this tool is with Docker, which handles all dependencies and connectivity to MSSQL.

### Quick Start

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/mssql-restore.git
   cd mssql-restore
   ```

2. Start the MSSQL server and monitoring service:
   ```bash
   docker-compose up -d
   ```

3. Place backup files (RAR or DAT) in the `data_backups` directory and they will be automatically processed.

## 📝 Usage

### Monitor Mode (Default)

In monitor mode, the tool watches the `data_backups` directory for new backup files and automatically processes them:

1. Start services with monitoring enabled:
   ```bash
   docker-compose up -d
   ```

2. Copy your backup files to the `data_backups` directory.

3. The tool will automatically:
   - Detect new backup files
   - Extract RAR archives if needed
   - Restore the database to MSSQL
   - Move processed files to the archived directory

4. Check logs for processing status:
   ```bash
   docker-compose logs -f backup-tool
   ```

### CLI Mode (One-time Restore)

For one-time operations, use CLI mode to process a specific backup file:

```bash
# Process a backup file with full path specification
echo '{"command": "restore", "resource": "file:///data/input/test.rar"}' | \
  docker-compose run --rm -T -e TOOL_MODE=cli backup-tool
```

### Command Format

The tool accepts JSON commands via STDIN:

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

- Local file: `file:///data/input/backup.rar`
- HTTP(S): `https://example.com/backup.rar`
- S3: `s3://bucket/path/to/backup.dat?region=us-west-2`

## 🛠️ Configuration

Configuration is handled through environment variables in the `docker-compose.yaml` file.

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOOL_MODE` | Operation mode (`monitor` or `cli`) | `monitor` |
| `MSSQL_PASSWORD` | SQL Server password | `YourPassword123!` |
| `BACKUP_WATCH_DIR` | Directory to monitor for new backups | `/data/input` |
| `BACKUP_SHARED_DIR` | Shared directory for database backups | `/shared_backup` |
| `APP_LOG_LEVEL` | Logging level (INFO, DEBUG, etc.) | `INFO` |

## 🖥️ Local Installation (Advanced)

While Docker is recommended, you can install locally with these prerequisites:

- Python 3.8+
- MSSQL ODBC drivers
- UnRAR and p7zip utilities
- freetds (for MSSQL connectivity)

```bash
# Install system dependencies (Ubuntu example)
apt-get install -y python3 python3-pip unixodbc unixodbc-dev unrar p7zip-full p7zip-rar freetds-bin freetds-dev

# Install Microsoft ODBC Driver
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18

# Install Python dependencies
pip install -r requirements.txt

# Run the tool
cat command.json | python -m tool
```

## 📂 Directory Structure

- `data/mssql/`: MSSQL data files (mounted to container)
- `data_backups/`: Place backup files here for processing
- `data_backups/archived/`: Successfully processed backups
- `logs/`: Application logs
- `tool/`: Python source code

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.