"""
Automatic update checker for SceneWrite.

Fetches a version manifest from scenewrite.app and compares it against
the running version.  All network I/O is designed to be called from a
background thread so the UI never blocks.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

from config import APP_VERSION, UPDATE_URL


@dataclass
class UpdateInfo:
    """Describes an available update."""
    version: str
    release_notes: str
    download_url: str
    release_date: str = ""
    is_mandatory: bool = False


def _parse_version(version_str: str) -> tuple:
    """Convert '1.2.3' to (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in version_str.strip().split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _platform_key() -> str:
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    return "linux"


def check_for_update(timeout: int = 8) -> Optional[UpdateInfo]:
    """Fetch the remote manifest and return UpdateInfo if a newer version exists.

    Returns None when the app is already up-to-date or if the check fails
    (no internet, server down, malformed JSON, etc.).  This function is
    safe to call from any thread.
    """
    try:
        req = urllib.request.Request(
            UPDATE_URL,
            headers={"User-Agent": f"SceneWrite/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        remote_version = data.get("version", "")
        if not remote_version:
            return None

        if _parse_version(remote_version) <= _parse_version(APP_VERSION):
            return None

        platform = _platform_key()
        downloads = data.get("downloads", {})
        download_url = downloads.get(platform, data.get("download_url", ""))

        min_version = data.get("min_version", "")
        is_mandatory = bool(
            min_version and _parse_version(APP_VERSION) < _parse_version(min_version)
        )

        return UpdateInfo(
            version=remote_version,
            release_notes=data.get("release_notes", ""),
            download_url=download_url,
            release_date=data.get("release_date", ""),
            is_mandatory=is_mandatory,
        )
    except Exception:
        return None


def seconds_since_last_check(config_obj) -> float:
    """Return seconds elapsed since the last successful update check."""
    last = config_obj._config_data.get("last_update_check", 0)
    return time.time() - last


def record_update_check(config_obj):
    """Persist the current timestamp as the last update check time."""
    config_obj._config_data["last_update_check"] = time.time()
    config_obj._save_config()
