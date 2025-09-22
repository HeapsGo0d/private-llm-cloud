#!/usr/bin/env python3
"""
Private LLM Cloud - Robust Download Utilities
Incorporates proven aria2c patterns from Ignition project
"""

import os
import sys
import subprocess
import shutil
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse, parse_qs
import tempfile
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download configuration constants (from Ignition proven patterns)
ARIA2_CONNECTIONS = 8
ARIA2_SPLITS = 8
ARIA2_MAX_TRIES = 3
ARIA2_RETRY_WAIT = 2
ARIA2_TIMEOUT = 30
ARIA2_MIN_SPLIT_SIZE = "1M"
PROGRESS_INTERVAL = 5
MIN_FILE_SIZE_MB = 1

# Status icons for consistent user feedback
ICONS = {
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'info': '🔍',
    'download': '📥',
    'processing': '⚙️',
    'complete': '🎉'
}

class DownloadError(Exception):
    """Custom exception for download-related errors"""
    pass

class ValidationError(Exception):
    """Custom exception for validation-related errors"""
    pass

def ensure_aria2() -> bool:
    """
    Ensure aria2c is available on the system
    Returns: True if aria2c is available, False otherwise
    """
    try:
        result = subprocess.run(['aria2c', '--version'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.info(f"{ICONS['success']} aria2c is available")
            return True
        else:
            logger.error(f"{ICONS['error']} aria2c not working properly")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.error(f"{ICONS['error']} aria2c not found or not working: {e}")
        return False

def validate_file_size(file_path: Path, min_size_mb: int = MIN_FILE_SIZE_MB) -> bool:
    """
    Validate that downloaded file meets minimum size requirements

    Args:
        file_path: Path to the file to validate
        min_size_mb: Minimum file size in MB

    Returns:
        True if file is valid, False otherwise
    """
    try:
        if not file_path.exists():
            logger.error(f"{ICONS['error']} File does not exist: {file_path}")
            return False

        file_size = file_path.stat().st_size
        min_size_bytes = min_size_mb * 1024 * 1024

        if file_size < min_size_bytes:
            logger.error(f"{ICONS['error']} File too small: {file_size} bytes (minimum: {min_size_bytes})")
            return False

        logger.info(f"{ICONS['success']} File size validation passed: {file_size:,} bytes")
        return True
    except Exception as e:
        logger.error(f"{ICONS['error']} Error validating file size: {e}")
        return False

def validate_huggingface_url(url: str) -> bool:
    """
    Validate HuggingFace model URL format

    Args:
        url: URL to validate

    Returns:
        True if URL is valid HuggingFace format, False otherwise
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc not in ['huggingface.co', 'hf.co']:
            return False

        # Check for proper path format: /user/model/resolve/main/filename
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) < 5:
            return False

        if 'resolve' not in path_parts:
            return False

        logger.info(f"{ICONS['success']} Valid HuggingFace URL format")
        return True
    except Exception as e:
        logger.error(f"{ICONS['error']} Error validating HuggingFace URL: {e}")
        return False

def validate_civitai_url(url: str) -> bool:
    """
    Validate CivitAI model URL format

    Args:
        url: URL to validate

    Returns:
        True if URL is valid CivitAI format, False otherwise
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc != 'civitai.com':
            return False

        # Check for model ID in query parameters
        query_params = parse_qs(parsed.query)
        if 'modelVersionId' not in query_params and 'id' not in query_params:
            return False

        logger.info(f"{ICONS['success']} Valid CivitAI URL format")
        return True
    except Exception as e:
        logger.error(f"{ICONS['error']} Error validating CivitAI URL: {e}")
        return False

def cleanup_existing_file(file_path: Path) -> bool:
    """
    Remove existing file if it exists to avoid conflicts

    Args:
        file_path: Path to the file to remove

    Returns:
        True if cleanup successful, False otherwise
    """
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"{ICONS['processing']} Removed existing file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"{ICONS['error']} Error removing existing file: {e}")
        return False

def build_aria2_command(url: str, output_dir: Path, filename: str, token: str = "") -> list:
    """
    Build aria2c command with optimized parameters

    Args:
        url: URL to download
        output_dir: Directory to save file
        filename: Name of output file
        token: Optional authentication token

    Returns:
        List of command arguments
    """
    cmd = [
        'aria2c',
        '--console-log-level=warn',
        '--summary-interval=0',
        f'--dir={output_dir}',
        f'--out={filename}',
        '--allow-overwrite=true',
        '--auto-file-renaming=false',
        f'--max-connection-per-server={ARIA2_CONNECTIONS}',
        f'--split={ARIA2_SPLITS}',
        f'--max-tries={ARIA2_MAX_TRIES}',
        f'--retry-wait={ARIA2_RETRY_WAIT}',
        f'--timeout={ARIA2_TIMEOUT}',
        f'--min-split-size={ARIA2_MIN_SPLIT_SIZE}',
        '--continue=true',
        '--remote-time=true'
    ]

    # Add authentication header if token provided
    if token:
        cmd.append(f'--header=Authorization: Bearer {token}')

    # Add URL last
    cmd.append(url)

    return cmd

def download_with_aria2(url: str, output_dir: Path, filename: str, token: str = "") -> bool:
    """
    Download file using aria2c with robust error handling

    Args:
        url: URL to download
        output_dir: Directory to save file
        filename: Name of output file
        token: Optional authentication token

    Returns:
        True if download successful, False otherwise
    """
    try:
        # Pre-flight checks
        if not ensure_aria2():
            raise DownloadError("aria2c not available")

        # Validate URL format based on source
        if 'huggingface.co' in url or 'hf.co' in url:
            if not validate_huggingface_url(url):
                raise ValidationError(f"Invalid HuggingFace URL format: {url}")
        elif 'civitai.com' in url:
            if not validate_civitai_url(url):
                raise ValidationError(f"Invalid CivitAI URL format: {url}")

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / filename

        # Cleanup existing file
        if not cleanup_existing_file(file_path):
            raise DownloadError("Failed to cleanup existing file")

        # Build and execute download command
        cmd = build_aria2_command(url, output_dir, filename, token)

        logger.info(f"{ICONS['download']} Starting download: {filename}")
        logger.info(f"{ICONS['info']} URL: {url}")
        logger.info(f"{ICONS['info']} Output: {file_path}")

        # Execute download with timeout
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)  # 1 hour timeout
        end_time = time.time()

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise DownloadError(f"aria2c failed with code {result.returncode}: {error_msg}")

        # Validate downloaded file
        if not validate_file_size(file_path):
            raise ValidationError("Downloaded file failed size validation")

        duration = end_time - start_time
        file_size = file_path.stat().st_size
        speed_mbps = (file_size / (1024 * 1024)) / duration

        logger.info(f"{ICONS['success']} Download completed successfully")
        logger.info(f"{ICONS['info']} Time: {duration:.1f}s, Size: {file_size:,} bytes, Speed: {speed_mbps:.1f} MB/s")

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"{ICONS['error']} Download timeout after 1 hour")
        return False
    except (DownloadError, ValidationError) as e:
        logger.error(f"{ICONS['error']} {e}")
        return False
    except Exception as e:
        logger.error(f"{ICONS['error']} Unexpected error during download: {e}")
        return False

def verify_download_integrity(file_path: Path, expected_hash: str = None, hash_algorithm: str = 'sha256') -> bool:
    """
    Verify download integrity using hash comparison

    Args:
        file_path: Path to downloaded file
        expected_hash: Expected hash value
        hash_algorithm: Hash algorithm to use

    Returns:
        True if integrity check passes, False otherwise
    """
    try:
        if not expected_hash:
            logger.info(f"{ICONS['warning']} No hash provided, skipping integrity check")
            return True

        if not file_path.exists():
            logger.error(f"{ICONS['error']} File not found for integrity check: {file_path}")
            return False

        # Calculate file hash
        hash_obj = hashlib.new(hash_algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)

        actual_hash = hash_obj.hexdigest()

        if actual_hash.lower() == expected_hash.lower():
            logger.info(f"{ICONS['success']} Integrity check passed")
            return True
        else:
            logger.error(f"{ICONS['error']} Integrity check failed")
            logger.error(f"Expected: {expected_hash}")
            logger.error(f"Actual:   {actual_hash}")
            return False

    except Exception as e:
        logger.error(f"{ICONS['error']} Error during integrity check: {e}")
        return False

def atomic_download(url: str, output_dir: Path, filename: str, token: str = "",
                   expected_hash: str = None) -> bool:
    """
    Perform atomic download with validation and cleanup
    Download → Verify → Move → Cleanup pattern

    Args:
        url: URL to download
        output_dir: Final output directory
        filename: Final filename
        token: Optional authentication token
        expected_hash: Optional hash for integrity checking

    Returns:
        True if atomic download successful, False otherwise
    """
    temp_dir = None
    try:
        # Create temporary directory for download
        temp_dir = Path(tempfile.mkdtemp(prefix='pllm_download_'))
        temp_file = temp_dir / filename
        final_file = output_dir / filename

        logger.info(f"{ICONS['processing']} Starting atomic download: {filename}")

        # Download to temporary location
        if not download_with_aria2(url, temp_dir, filename, token):
            raise DownloadError("Download failed")

        # Verify integrity if hash provided
        if expected_hash and not verify_download_integrity(temp_file, expected_hash):
            raise ValidationError("Integrity verification failed")

        # Ensure final output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Atomic move to final location
        shutil.move(str(temp_file), str(final_file))

        logger.info(f"{ICONS['complete']} Atomic download completed: {final_file}")
        return True

    except Exception as e:
        logger.error(f"{ICONS['error']} Atomic download failed: {e}")
        return False
    finally:
        # Cleanup temporary directory
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"{ICONS['processing']} Cleaned up temporary directory")
            except Exception as e:
                logger.warning(f"{ICONS['warning']} Failed to cleanup temp directory: {e}")

def get_download_info(url: str) -> Dict[str, Any]:
    """
    Get information about a download URL without downloading

    Args:
        url: URL to analyze

    Returns:
        Dictionary with download information
    """
    try:
        parsed = urlparse(url)
        info = {
            'url': url,
            'domain': parsed.netloc,
            'valid': False,
            'estimated_size': None,
            'filename': None
        }

        # Extract filename from URL
        path_parts = parsed.path.split('/')
        if path_parts:
            info['filename'] = path_parts[-1]

        # Validate based on domain
        if parsed.netloc in ['huggingface.co', 'hf.co']:
            info['valid'] = validate_huggingface_url(url)
            info['source'] = 'huggingface'
        elif parsed.netloc == 'civitai.com':
            info['valid'] = validate_civitai_url(url)
            info['source'] = 'civitai'
        else:
            info['source'] = 'unknown'

        return info

    except Exception as e:
        logger.error(f"{ICONS['error']} Error getting download info: {e}")
        return {'url': url, 'valid': False, 'error': str(e)}

if __name__ == "__main__":
    """Command line interface for testing download utilities"""
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <url> <output_dir> <filename> [token]")
        sys.exit(1)

    url = sys.argv[1]
    output_dir = Path(sys.argv[2])
    filename = sys.argv[3]
    token = sys.argv[4] if len(sys.argv) > 4 else ""

    success = atomic_download(url, output_dir, filename, token)
    sys.exit(0 if success else 1)