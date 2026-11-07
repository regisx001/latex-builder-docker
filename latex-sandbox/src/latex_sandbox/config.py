import os
from dataclasses import dataclass, field


@dataclass
class LatexSandboxConfig:
    """Configuration settings for the XeLaTeX sandbox environment."""

    image_name: str = field(
        default_factory=lambda: os.getenv(
            "LATEX_SANDBOX_IMAGE", "ghcr.io/regisx001/career-agent/latex-sandbox:latest"
        )
    )
    timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("LATEX_SANDBOX_TIMEOUT", "60"))
    )
    memory_limit: str = "512m"
    network_disabled: bool = True
    default_engine: str = "xelatex"
    runs: int = 1
    auto_pull: bool = field(
        default_factory=lambda: os.getenv("LATEX_SANDBOX_AUTO_PULL", "true").lower()
        in ("true", "1", "yes")
    )
    cache_enabled: bool = field(
        default_factory=lambda: os.getenv("LATEX_CACHE_ENABLED", "true").lower()
        in ("true", "1", "yes")
    )
    cache_dir: str = field(
        default_factory=lambda: os.getenv("LATEX_CACHE_DIR", "/cache")
    )
