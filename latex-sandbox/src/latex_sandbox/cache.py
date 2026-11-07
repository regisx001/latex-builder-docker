import logging
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Optional, Union

logger = logging.getLogger(__name__)


class PdfCache:
    """Content-addressable on-disk PDF cache for LaTeX compilation."""

    def __init__(
        self,
        directory: Union[str, Path] = "/cache",
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.directory = Path(directory)
        if self.enabled:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Fallback for local non-root dev environments where /cache cannot be created
                self.directory = Path.home() / ".cache" / "career-agent" / "latex"
                try:
                    self.directory.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    logger.warning(
                        "Failed to create PDF cache directory at %s: %s. Disabling cache.",
                        self.directory,
                        e,
                    )
                    self.enabled = False

    def key(
        self,
        files: Union[str, Mapping[str, Union[str, bytes]]],
        main_file: str = "main.tex",
        engine: str = "xelatex",
        runs: int = 1,
    ) -> str:
        """Compute a deterministic SHA-256 hash key based on input files, main file, engine, and runs."""
        hasher = sha256()
        hasher.update(main_file.encode("utf-8"))
        hasher.update(engine.encode("utf-8"))
        hasher.update(str(runs).encode("utf-8"))

        if isinstance(files, str):
            hasher.update(files.encode("utf-8"))
        elif isinstance(files, Mapping):
            for path in sorted(files.keys()):
                hasher.update(path.encode("utf-8"))
                content = files[path]
                if isinstance(content, str):
                    hasher.update(content.encode("utf-8"))
                elif isinstance(content, (bytes, bytearray)):
                    hasher.update(content)
                else:
                    hasher.update(str(content).encode("utf-8"))
        else:
            hasher.update(str(files).encode("utf-8"))

        return hasher.hexdigest()

    def get(self, cache_key: str) -> Optional[bytes]:
        """Retrieve cached PDF bytes by cache key. Returns None on cache miss."""
        if not self.enabled:
            return None
        pdf_path = self.directory / f"{cache_key}.pdf"
        if pdf_path.exists() and pdf_path.is_file():
            try:
                return pdf_path.read_bytes()
            except OSError as e:
                logger.warning("Failed reading cached PDF at %s: %s", pdf_path, e)
        return None

    def save(self, cache_key: str, pdf: Union[bytes, Path]) -> Optional[Path]:
        """Save PDF content or file to cache under <cache_key>.pdf."""
        if not self.enabled:
            return None
        destination = self.directory / f"{cache_key}.pdf"
        try:
            if isinstance(pdf, Path):
                destination.write_bytes(pdf.read_bytes())
            elif isinstance(pdf, (bytes, bytearray)):
                destination.write_bytes(pdf)
            else:
                destination.write_bytes(bytes(pdf))
            return destination
        except OSError as e:
            logger.warning("Failed saving PDF to cache at %s: %s", destination, e)
            return None

    def clear(self) -> int:
        """Clear all cached PDFs. Returns the count of removed files."""
        if not self.directory.exists():
            return 0
        count = 0
        for item in self.directory.glob("*.pdf"):
            try:
                item.unlink()
                count += 1
            except OSError:
                pass
        return count


CacheManager = PdfCache
