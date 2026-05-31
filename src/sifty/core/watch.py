"""Low-disk-space watch (engine): which volumes are below the free-space threshold."""

from __future__ import annotations

from ..infra.config import load_config
from . import disk
from .models import VolumeUsage

__all__ = ["threshold_gb", "low_space"]


def threshold_gb(override: int | None = None, config=None) -> int:
    if override is not None:
        return override
    config = config or load_config()
    return int(config.section("watch").get("threshold_gb", 5))


def low_space(override_gb: int | None = None, config=None) -> list[VolumeUsage]:
    """Volumes whose free space is below the threshold (GB)."""
    limit = threshold_gb(override_gb, config) * 1024 ** 3
    return [v for v in disk.volumes() if v.free < limit]
