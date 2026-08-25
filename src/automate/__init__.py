"""automate - Reusable CI/CD workflows and release helpers for Python projects."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("automate")
except PackageNotFoundError:  # pragma: no cover - only when running from a bare checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
