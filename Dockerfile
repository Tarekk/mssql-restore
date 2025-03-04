# Use Ubuntu as base image
FROM ubuntu:22.04

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ACCEPT_EULA=Y \
    TZ=UTC

# Install Python and system dependencies with retry mechanism
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && \
    for i in $(seq 1 3); do \
        (apt-get update -o Acquire::CompressionTypes::Order::=gz && \
        apt-get install -y --no-install-recommends \
            python3 \
            python3-pip \
            python3-dev \
            build-essential \
            curl \
            gnupg2 \
            unixodbc \
            unixodbc-dev \
            wget \
            unrar \
            p7zip-full \
            p7zip-rar \
            freetds-bin \
            freetds-dev && \
        # Ensure unrar is executable
        chmod +x /usr/bin/unrar && \
        # Install Microsoft ODBC Driver (critical for SQL Server connectivity)
        curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
        curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
        apt-get update -o Acquire::CompressionTypes::Order::=gz && \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 && \
        # Clean up
        apt-get clean && \
        rm -rf /var/lib/apt/lists/*) && break || \
        if [ $i -lt 3 ]; then sleep 1; else exit 1; fi; \
    done

# Set work directory
WORKDIR /app

# Upgrade pip and install wheel
RUN python3 -m pip install --no-cache-dir --upgrade pip wheel setuptools

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Create necessary directories with proper permissions
RUN mkdir -p /data/input /data/output /shared_backup /logs \
    && chmod -R 777 /data /shared_backup /logs

# Copy the package
COPY . /app/

# Add logging directory to environment
ENV LOG_DIRECTORY=/logs \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Set mode to monitor by default (use TOOL_MODE=cli for CLI mode)
ENV TOOL_MODE=monitor

# Default command using Python module syntax explicitly
# This ensures __main__.py is executed correctly
ENTRYPOINT ["python3", "-m", "tool"]
