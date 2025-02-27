"""
Resource resolver for MSSQL Backup Tool.

Handles different resource URI formats and resolves them to local file paths.
"""

import logging
import os
import tempfile
import time
import urllib.parse

import requests

logger = logging.getLogger(__name__)


class ResourceResolver:
    """Resolves resource URIs to local file paths."""

    def __init__(self, temp_dir: str = None):
        """Initialize resolver with optional temporary directory."""
        self.temp_dir = (
            temp_dir or os.environ.get("TOOL_TEMP_DIR") or tempfile.gettempdir()
        )
        os.makedirs(self.temp_dir, exist_ok=True)

    def resolve(self, resource_uri: str) -> str:
        """Resolve a resource URI to a local file path."""
        # Parse the URI
        parsed = urllib.parse.urlparse(resource_uri)

        # Dispatch based on scheme
        if parsed.scheme == "file":
            return self._resolve_file(parsed)
        elif parsed.scheme in ("http", "https"):
            return self._resolve_http(parsed)
        elif parsed.scheme == "s3":
            return self._resolve_s3(parsed)
        else:
            raise ValueError(f"Unsupported resource scheme: {parsed.scheme}")

    def _resolve_file(self, parsed_uri: urllib.parse.ParseResult) -> str:
        """Resolve a file:// URI to a local path."""
        # Convert file URI to local path
        if parsed_uri.netloc:
            # Handle Windows UNC paths or non-standard file URIs
            path = f"//{parsed_uri.netloc}{parsed_uri.path}"
        else:
            path = parsed_uri.path

        # Normalize the path and handle URL encoding
        path = urllib.parse.unquote(path)

        # Check if file exists
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")

        return path

    def _resolve_http(self, parsed_uri: urllib.parse.ParseResult) -> str:
        """Resolve an HTTP(S) URI by downloading to a local file."""
        url = parsed_uri.geturl()
        logger.info(f"Downloading resource from {url}")

        # Extract filename from URL or generate one
        filename = os.path.basename(parsed_uri.path) or f"download_{int(time.time())}"
        local_path = os.path.join(self.temp_dir, filename)

        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            logger.info(f"Downloaded {url} to {local_path}")
            return local_path

        except requests.RequestException as e:
            raise IOError(f"Failed to download {url}: {str(e)}")

    def _resolve_s3(self, parsed_uri: urllib.parse.ParseResult) -> str:
        """Resolve an S3 URI by downloading to a local file."""
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required for S3 resource access")

        bucket = parsed_uri.netloc
        key = parsed_uri.path.lstrip("/")

        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {parsed_uri.geturl()}")

        logger.info(f"Downloading S3 object s3://{bucket}/{key}")

        # Parse query parameters for region, etc.
        params = dict(urllib.parse.parse_qsl(parsed_uri.query))
        region = params.get("region")

        # Extract filename or generate one
        filename = os.path.basename(key) or f"s3_download_{int(time.time())}"
        local_path = os.path.join(self.temp_dir, filename)

        try:
            s3_client = boto3.client("s3", region_name=region)
            s3_client.download_file(bucket, key, local_path)

            logger.info(f"Downloaded s3://{bucket}/{key} to {local_path}")
            return local_path

        except Exception as e:
            raise IOError(f"Failed to download from S3: {str(e)}")
