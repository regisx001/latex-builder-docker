import os
from typing import Mapping, Union


class ValidationError(ValueError):
    """Exception raised for validation errors in input files or parameters."""

    pass


def validate_filename(filename: str) -> None:
    """Ensure filename is relative, safe, and doesn't attempt directory traversal."""
    if not filename or not isinstance(filename, str):
        raise ValidationError("Filename must be a non-empty string.")

    if os.path.isabs(filename):
        raise ValidationError(f"Filename must be relative, got absolute path: '{filename}'")

    normalized = os.path.normpath(filename)
    if normalized.startswith("..") or "/.." in normalized or "\\.." in normalized:
        raise ValidationError(f"Invalid path traversal attempt in filename: '{filename}'")


def validate_files(
    files: Mapping[str, Union[str, bytes]], main_file: str = "main.tex"
) -> None:
    """Validate the provided dictionary of files before compilation."""
    if not isinstance(files, Mapping) or not files:
        raise ValidationError("The 'files' dictionary cannot be empty.")

    if main_file not in files:
        raise ValidationError(
            f"Main entry point '{main_file}' was not found in files dictionary."
        )

    for filename, content in files.items():
        validate_filename(filename)
        if not isinstance(content, (str, bytes)):
            raise ValidationError(
                f"File content for '{filename}' must be str or bytes, got {type(content).__name__}"
            )
