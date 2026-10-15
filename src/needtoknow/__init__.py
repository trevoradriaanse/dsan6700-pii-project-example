"""Need to Know: find the personal information in a PDF, review it, and download a copy with it removed."""

from importlib.metadata import version

# The version is written in one place, pyproject.toml; everything else (/ready, the API docs, a release tag) reads it.
__version__ = version("needtoknow")
