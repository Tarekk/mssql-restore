# Contributing to MSSQL Backup Ingestion Service

Thank you for considering contributing to the MSSQL Backup Ingestion Service! Your help is essential for making this tool better for everyone.

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior.

## How Can I Contribute?

### Reporting Bugs

- **Check Existing Issues** — Before creating a new bug report, check if the problem has already been reported.
- **Use the Bug Report Template** — If available, use the issue template for bugs.
- **Be Detailed** — Include as many details as possible: steps to reproduce, expected vs. actual behavior, your environment details.
- **Include Logs** — If applicable, include relevant logs or screenshots.

### Suggesting Enhancements

- **Use the Feature Request Template** — If available, use the issue template for feature requests.
- **Be Specific** — Explain what the enhancement should do and why it would be valuable.
- **Consider Scope** — Understand if your suggestion fits the project's scope and goals.

### Pull Requests

1. **Fork the Repository** — Create your own fork of the project.
2. **Create a Branch** — Make your changes in a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Follow Coding Standards** — Match the style and conventions of the project.
4. **Include Tests** — Add tests to cover your changes.
5. **Document Changes** — Update documentation to reflect your changes.
6. **Commit Properly** — Use clear, specific commit messages.
7. **Submit a Pull Request** — Include a clear description of the problem and solution.

## Development Setup

### Prerequisites

- Python 3.9 or higher
- Docker (for testing with MSSQL and MinIO)
- Make (optional, for running Makefile commands)

### Local Development Environment

1. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mssql-backup-ingestion.git
   cd mssql-backup-ingestion
   ```

2. Set up a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Create a local `.env` file for testing:
   ```bash
   cp .env.example .env
   # Edit .env with your test configuration
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=ingestion_service tests/

# Run specific tests
pytest tests/test_monitor.py
```

### Code Style

This project uses:

- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

You can verify your code style with:

```bash
# Format code
black ingestion_service tests

# Sort imports
isort ingestion_service tests

# Lint
flake8 ingestion_service tests

# Type check
mypy ingestion_service
```

## Documentation

Please update documentation when you make changes:

- Update docstrings
- Modify README.md if needed
- Update example code if applicable

## Release Process

1. Version numbers follow [Semantic Versioning](https://semver.org/)
2. Major releases are prepared in dedicated branches
3. A maintainer will review and merge your PR
4. After merging, a maintainer will create a release

## Questions?

If you have questions or need help, please open an issue or contact the maintainers.

Thank you for contributing!