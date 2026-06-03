"""Self-update: compare the running version against PyPI and upgrade via pipx."""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError, version as pkg_version

__all__ = ["current_version", "latest_version", "check_update", "apply_update"]

_PACKAGE = "sifty"
_PYPI_URL = "https://pypi.org/pypi/sifty/json"


def _parse(v: str) -> tuple[int, ...]:
    """Parse a semver-ish string into a comparable tuple, ignoring pre-release tags."""
    parts = []
    for segment in v.split(".")[:3]:
        digits = "".join(c for c in segment if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def current_version() -> str:
    try:
        return pkg_version(_PACKAGE)
    except PackageNotFoundError:
        return "0.0.0"


def latest_version() -> str | None:
    """Fetch the latest published version from PyPI. Returns None on any error."""
    try:
        import httpx
        resp = httpx.get(_PYPI_URL, timeout=5.0, follow_redirects=True)
        if resp.status_code == 200:
            return resp.json().get("info", {}).get("version")
    except Exception:
        pass
    return None


def check_update() -> tuple[str, str | None]:
    """Return (current, latest_if_newer). latest is None if already up-to-date or check failed."""
    current = current_version()
    latest = latest_version()
    if latest and _parse(latest) > _parse(current):
        return current, latest
    return current, None


def apply_update() -> tuple[bool, str]:
    """Run `pipx upgrade sifty`. Returns (success, message)."""
    try:
        result = subprocess.run(
            ["pipx", "upgrade", _PACKAGE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        ok = result.returncode == 0
        msg = (result.stdout or result.stderr or "").strip().splitlines()
        summary = msg[-1] if msg else ("Upgraded successfully." if ok else "Upgrade failed.")
        return ok, summary
    except FileNotFoundError:
        return False, "pipx not found — is Sifty installed via pipx?"
    except subprocess.TimeoutExpired:
        return False, "Upgrade timed out after 120 s"
    except OSError as exc:
        return False, str(exc)
