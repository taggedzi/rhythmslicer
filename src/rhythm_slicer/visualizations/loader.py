"""Safe visualization loader."""

from __future__ import annotations

from importlib import import_module
from typing import Any
import re

from rhythm_slicer.visualizations import minimal as minimal_viz

_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _is_valid_name(name: str) -> bool:
    return bool(_VALID_NAME.match(name))


def _is_plugin(candidate: Any) -> bool:
    return hasattr(candidate, "VIZ_NAME") and callable(
        getattr(candidate, "generate_frames", None)
    )


def _load_builtin(name: str) -> Any | None:
    module_name = f"rhythm_slicer.visualizations.{name}"
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        return None
    except Exception:
        return None


def _load_entry_point(name: str) -> Any | None:
    try:
        from importlib import metadata
    except Exception:
        return None
    try:
        entry_points = metadata.entry_points()
    except Exception:
        return None
    if hasattr(entry_points, "select"):
        candidates = entry_points.select(group="rhythmslicer.visualizations")
    else:
        candidates = entry_points.get("rhythmslicer.visualizations", [])
    for entry_point in candidates:
        if entry_point.name != name:
            continue
        try:
            return entry_point.load()
        except Exception:
            return None
    return None


def load_viz(name: str):
    """Return a visualization plugin module-like object."""
    if not _is_valid_name(name):
        return minimal_viz
    plugin = _load_builtin(name)
    if plugin is not None and _is_plugin(plugin):
        return plugin
    plugin = _load_entry_point(name)
    if plugin is not None and _is_plugin(plugin):
        return plugin
    return minimal_viz
