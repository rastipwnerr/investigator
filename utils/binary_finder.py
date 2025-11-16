#!/usr/bin/env python3
"""
Utility to find required forensic tool binaries
"""

import os
import subprocess
from typing import Optional, List


def find_binary(paths: List[str], binary_name: str) -> Optional[str]:
    """
    Find a binary executable in a list of possible paths

    Args:
        paths: List of paths to check
        binary_name: Binary name (for 'which' command fallback)

    Returns:
        Path to the found binary, or None if not found
    """
    # Check provided paths first
    for path in paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            print(f"[DEBUG] {binary_name} found at: {path}")
            return path

    # Try using 'which' command as fallback
    try:
        result = subprocess.run(
            ['which', binary_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            found_path = result.stdout.strip()
            print(f"[DEBUG] {binary_name} found via which: {found_path}")
            return found_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None
