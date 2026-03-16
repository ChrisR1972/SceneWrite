"""
License management for SceneWrite.

Handles machine fingerprinting, local license caching with encryption,
online activation/validation via the Cloudflare Workers API, and
7-day free trial tracking.
"""

import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

from config import APP_VERSION, LICENSE_API_BASE, get_config_directory
TRIAL_DAYS = 7
OFFLINE_GRACE_DAYS = 14
REVALIDATION_INTERVAL = 7 * 24 * 60 * 60  # re-check online once per week

# Derivation salt for the local cache encryption key.
# Not a secret -- just ensures the HMAC output differs from other uses
# of the same machine fingerprint.
_CACHE_SALT = b"SceneWrite-License-Cache-v1"


class LicenseStatus(Enum):
    VALID = "valid"
    TRIAL_ACTIVE = "trial_active"
    TRIAL_EXPIRED = "trial_expired"
    EXPIRED = "expired"
    INVALID = "invalid"
    NO_LICENSE = "no_license"


@dataclass
class LicenseState:
    status: LicenseStatus
    license_key: str = ""
    email: str = ""
    plan: str = ""
    days_remaining: Optional[int] = None
    message: str = ""


# ---------------------------------------------------------------------------
#  Machine fingerprint
# ---------------------------------------------------------------------------

def _run_cmd(args: list[str]) -> str:
    try:
        out = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=5)
        return out.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def get_machine_id() -> str:
    """Return a stable, pseudonymous identifier for this machine.

    Combines OS-level machine IDs that persist across reboots.
    The result is a SHA-256 hex digest so no raw hardware serials leave
    the machine.
    """
    parts: list[str] = []

    if sys.platform == "win32":
        # Windows: MachineGuid from the registry
        raw = _run_cmd([
            "reg", "query",
            r"HKLM\SOFTWARE\Microsoft\Cryptography",
            "/v", "MachineGuid",
        ])
        match = re.search(r"MachineGuid\s+REG_SZ\s+(.+)", raw)
        if match:
            parts.append(match.group(1).strip())

        # Fallback: BIOS serial
        raw = _run_cmd(["wmic", "bios", "get", "serialnumber"])
        for line in raw.splitlines():
            line = line.strip()
            if line and line.lower() != "serialnumber":
                parts.append(line)
                break

    elif sys.platform == "darwin":
        raw = _run_cmd(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', raw)
        if match:
            parts.append(match.group(1))

    else:  # Linux
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        val = f.read().strip()
                        if val:
                            parts.append(val)
                            break
                except OSError:
                    pass

    # Universally available fallback: hostname + platform node
    if not parts:
        parts.append(platform.node())
        parts.append(str(uuid.getnode()))

    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


# ---------------------------------------------------------------------------
#  Encrypted local license cache
# ---------------------------------------------------------------------------

def _derive_key(machine_id: str) -> bytes:
    """Derive a 32-byte key from the machine fingerprint for HMAC signing."""
    return hashlib.sha256(_CACHE_SALT + machine_id.encode()).digest()


def _cache_path() -> str:
    return os.path.join(get_config_directory(), "license.dat")


def _write_cache(data: dict, machine_id: str):
    """Write license data to disk with an HMAC signature."""
    key = _derive_key(machine_id)
    payload = json.dumps(data, separators=(",", ":")).encode()
    sig = hmac.new(key, payload, hashlib.sha256).hexdigest()
    blob = json.dumps({"payload": data, "sig": sig}, indent=2)
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            f.write(blob)
    except OSError:
        pass


def _read_cache(machine_id: str) -> Optional[dict]:
    """Read and verify the local license cache.  Returns None on any error."""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    payload = blob.get("payload")
    sig = blob.get("sig")
    if not payload or not sig:
        return None

    key = _derive_key(machine_id)
    expected = hmac.new(
        key, json.dumps(payload, separators=(",", ":")).encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, sig):
        return None

    return payload


# ---------------------------------------------------------------------------
#  Trial management
# ---------------------------------------------------------------------------

def _trial_data_path() -> str:
    return os.path.join(get_config_directory(), ".sw_trial")


def start_trial(machine_id: str) -> float:
    """Record the trial start time and return it."""
    now = time.time()
    data = {"started": now, "mid": machine_id[:16]}
    key = _derive_key(machine_id)
    payload = json.dumps(data, separators=(",", ":")).encode()
    sig = hmac.new(key, payload, hashlib.sha256).hexdigest()
    blob = json.dumps({"p": data, "s": sig})
    try:
        with open(_trial_data_path(), "w", encoding="utf-8") as f:
            f.write(blob)
    except OSError:
        pass
    return now


def get_trial_start(machine_id: str) -> Optional[float]:
    """Return the trial start timestamp, or None if no trial has been started."""
    try:
        with open(_trial_data_path(), "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    data = blob.get("p")
    sig = blob.get("s")
    if not data or not sig:
        return None

    key = _derive_key(machine_id)
    expected = hmac.new(
        key, json.dumps(data, separators=(",", ":")).encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None

    return data.get("started")


def trial_days_remaining(machine_id: str) -> Optional[int]:
    """Return how many trial days remain, or None if no trial started."""
    started = get_trial_start(machine_id)
    if started is None:
        return None
    elapsed_days = (time.time() - started) / 86400
    remaining = TRIAL_DAYS - elapsed_days
    return max(0, int(remaining))


# ---------------------------------------------------------------------------
#  Online API calls
# ---------------------------------------------------------------------------

def _api_post(endpoint: str, body: dict, timeout: int = 10) -> Optional[dict]:
    """POST JSON to the license API.  Returns parsed response or None."""
    url = f"{LICENSE_API_BASE}{endpoint}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"SceneWrite/{APP_VERSION}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def activate_license(license_key: str, machine_id: str) -> LicenseState:
    """Activate a license key online and cache the result locally."""
    resp = _api_post("/api/activate", {
        "license_key": license_key.strip(),
        "machine_id": machine_id,
        "app_version": APP_VERSION,
        "platform": sys.platform,
    })
    if resp is None:
        return LicenseState(
            status=LicenseStatus.INVALID,
            message="Could not reach the license server. Check your internet connection and try again.",
        )

    if resp.get("valid"):
        cache = {
            "license_key": license_key.strip(),
            "email": resp.get("email", ""),
            "plan": resp.get("plan", "lifetime"),
            "activated_at": time.time(),
            "last_validated": time.time(),
            "machine_id": machine_id,
        }
        _write_cache(cache, machine_id)
        return LicenseState(
            status=LicenseStatus.VALID,
            license_key=license_key.strip(),
            email=resp.get("email", ""),
            plan=resp.get("plan", "lifetime"),
            message="License activated successfully.",
        )

    return LicenseState(
        status=LicenseStatus.INVALID,
        message=resp.get("error", "Invalid license key."),
    )


def validate_cached_license(machine_id: str) -> LicenseState:
    """Check the local cache and optionally re-validate online."""
    cache = _read_cache(machine_id)
    if cache is None:
        return LicenseState(status=LicenseStatus.NO_LICENSE)

    if cache.get("machine_id") and cache["machine_id"] != machine_id:
        return LicenseState(
            status=LicenseStatus.INVALID,
            message="License was activated on a different machine.",
        )

    last_validated = cache.get("last_validated", 0)
    elapsed = time.time() - last_validated

    # If we're within the revalidation window, trust the cache
    if elapsed < REVALIDATION_INTERVAL:
        return LicenseState(
            status=LicenseStatus.VALID,
            license_key=cache.get("license_key", ""),
            email=cache.get("email", ""),
            plan=cache.get("plan", ""),
        )

    # Try to re-validate online
    resp = _api_post("/api/validate", {
        "license_key": cache.get("license_key", ""),
        "machine_id": machine_id,
    })

    if resp is not None:
        if resp.get("valid"):
            cache["last_validated"] = time.time()
            _write_cache(cache, machine_id)
            return LicenseState(
                status=LicenseStatus.VALID,
                license_key=cache.get("license_key", ""),
                email=cache.get("email", ""),
                plan=cache.get("plan", ""),
            )
        else:
            # Server says invalid -- clear cache
            try:
                os.remove(_cache_path())
            except OSError:
                pass
            return LicenseState(
                status=LicenseStatus.INVALID,
                message=resp.get("error", "License is no longer valid."),
            )

    # Offline: allow a grace period
    if elapsed < OFFLINE_GRACE_DAYS * 86400:
        return LicenseState(
            status=LicenseStatus.VALID,
            license_key=cache.get("license_key", ""),
            email=cache.get("email", ""),
            plan=cache.get("plan", ""),
            message="Offline mode — license will be re-verified when online.",
        )

    return LicenseState(
        status=LicenseStatus.EXPIRED,
        message=(
            f"License could not be verified for over {OFFLINE_GRACE_DAYS} days. "
            "Please connect to the internet to re-validate."
        ),
    )


def deactivate_license(machine_id: str):
    """Remove local license data (for switching machines)."""
    for p in (_cache_path(), _trial_data_path()):
        try:
            os.remove(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
#  High-level check (called at startup)
# ---------------------------------------------------------------------------

def check_license() -> LicenseState:
    """Determine the current license state.

    Priority:
      1. Valid activated license (cached or re-validated online)
      2. Active free trial
      3. Expired trial / no license
    """
    mid = get_machine_id()

    # 1. Check for an activated license
    state = validate_cached_license(mid)
    if state.status == LicenseStatus.VALID:
        return state

    # 2. Check free trial
    remaining = trial_days_remaining(mid)
    if remaining is not None:
        if remaining > 0:
            return LicenseState(
                status=LicenseStatus.TRIAL_ACTIVE,
                days_remaining=remaining,
                message=f"{remaining} day{'s' if remaining != 1 else ''} remaining in your free trial.",
            )
        else:
            return LicenseState(
                status=LicenseStatus.TRIAL_EXPIRED,
                days_remaining=0,
                message="Your free trial has ended.",
            )

    # 3. No license and no trial
    return LicenseState(status=LicenseStatus.NO_LICENSE)
