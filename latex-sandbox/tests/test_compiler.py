import os
import pathlib
from unittest.mock import MagicMock
import pytest
import docker
from docker.errors import DockerException, ImageNotFound

from latex_sandbox.cache import PdfCache
from latex_sandbox.compiler import CompilationResult, LatexCompiler
from latex_sandbox.config import LatexSandboxConfig
from latex_sandbox.validation import ValidationError

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def is_docker_available_and_image_built(image_name: str) -> bool:
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(image_name)
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def isolated_test_cache(tmp_path, monkeypatch):
    """Ensure each test runs with an isolated temporary cache directory."""
    test_cache = tmp_path / "test_cache"
    monkeypatch.setenv("LATEX_CACHE_DIR", str(test_cache))
    yield test_cache


@pytest.fixture
def mock_docker():
    """Fixture providing a mock Docker client configured for unit testing without Docker daemon or images."""
    client = MagicMock()
    container = MagicMock()

    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = (
        b"This is XeTeX, Version 3.141592653\nOutput written on main.pdf (1 page)."
    )
    mock_pdf = b"%PDF-1.5 Mock PDF output content"
    mock_tar = LatexCompiler._create_tar_archive({"main.pdf": mock_pdf})
    container.get_archive.return_value = ([mock_tar], {})

    def create_side_effect(*args, **kwargs):
        volumes = kwargs.get("volumes", {})
        for host_path in volumes.keys():
            pdf_path = os.path.join(host_path, "main.pdf")
            with open(pdf_path, "wb") as f:
                f.write(mock_pdf)
        return container

    client.containers.create.side_effect = create_side_effect
    client.images.get.return_value = MagicMock()

    return client, container


# -----------------------------------------------------------------------------
# Unit Tests (Fast & CI friendly - No Docker daemon or pre-built image required)
# -----------------------------------------------------------------------------


def test_basic_compile(mock_docker):
    client, container = mock_docker
    compiler = LatexCompiler(docker_client=client)

    tex_path = FIXTURES_DIR / "basic" / "main.tex"
    files = {"main.tex": tex_path.read_text(encoding="utf-8")}

    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf == b"%PDF-1.5 Mock PDF output content"
    assert "XeTeX" in result.log
    client.containers.create.assert_called_once()
    container.remove.assert_called_once_with(force=True)


def test_unicode_compile(mock_docker):
    client, _ = mock_docker
    compiler = LatexCompiler(docker_client=client)

    tex_path = FIXTURES_DIR / "unicode" / "main.tex"
    files = {"main.tex": tex_path.read_text(encoding="utf-8")}

    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf is not None
    assert result.pdf.startswith(b"%PDF")


def test_image_compile(mock_docker):
    client, _ = mock_docker
    compiler = LatexCompiler(docker_client=client)

    tex_path = FIXTURES_DIR / "image" / "main.tex"
    logo_path = FIXTURES_DIR / "image" / "logo.png"

    files = {
        "main.tex": tex_path.read_text(encoding="utf-8"),
        "logo.png": logo_path.read_bytes(),
    }

    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf is not None
    assert result.pdf.startswith(b"%PDF")


def test_invalid_latex(mock_docker):
    client, container = mock_docker
    container.wait.return_value = {"StatusCode": 1}
    container.logs.return_value = b"! Undefined control sequence.\nl.3 \\invalidcommand"

    client.containers.create.side_effect = None
    client.containers.create.return_value = container

    compiler = LatexCompiler(docker_client=client)
    files = {
        "main.tex": r"\documentclass{article}\begin{document}\invalidcommand\end{document}"
    }

    result = compiler.compile(files=files)

    assert result.success is False
    assert result.pdf is None
    assert "Undefined control sequence" in result.log


def test_shell_escape_disabled(mock_docker):
    client, _ = mock_docker
    compiler = LatexCompiler(docker_client=client)

    files = {
        "main.tex": r"\documentclass{article}\begin{document}\immediate\write18{id}\end{document}"
    }

    result = compiler.compile(files=files)

    assert result.success is True
    _, create_kwargs = client.containers.create.call_args
    command = create_kwargs.get("command", [])
    assert "-no-shell-escape" in command


def test_container_cleanup(mock_docker):
    client, container = mock_docker
    compiler = LatexCompiler(docker_client=client)

    files = {"main.tex": r"\documentclass{article}\begin{document}Hello\end{document}"}
    result = compiler.compile(files=files)

    assert result.success is True
    container.remove.assert_called_once_with(force=True)


def test_cv_integration_compile(mock_docker):
    client, _ = mock_docker
    compiler = LatexCompiler(docker_client=client)

    tex_path = FIXTURES_DIR / "cv" / "main.tex"
    logo_path = FIXTURES_DIR / "cv" / "logo.png"

    files = {
        "main.tex": tex_path.read_text(encoding="utf-8"),
        "logo.png": logo_path.read_bytes(),
    }

    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf is not None
    assert result.pdf.startswith(b"%PDF")


def test_validation_errors(mock_docker):
    client, _ = mock_docker
    compiler = LatexCompiler(docker_client=client)

    with pytest.raises(ValidationError, match="cannot be empty"):
        compiler.compile(files={})

    with pytest.raises(ValidationError, match="was not found"):
        compiler.compile(files={"other.tex": "content"})

    with pytest.raises(ValidationError, match="Invalid path traversal"):
        compiler.compile(files={"main.tex": "valid", "../escape.tex": "bad"})


def test_image_missing_error():
    client = MagicMock()
    client.images.get.side_effect = ImageNotFound("Image not found")
    client.images.pull.side_effect = DockerException("Pull failed")
    compiler = LatexCompiler(docker_client=client)

    files = {"main.tex": r"\documentclass{article}\begin{document}Test\end{document}"}
    result = compiler.compile(files=files)

    assert result.success is False
    assert result.pdf is None
    assert "not found" in result.error.lower()


def test_auto_pull_image_from_registry():
    client = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b"Output written on main.pdf (1 page)."
    mock_pdf = b"%PDF-1.5 Mock PDF"
    mock_tar = LatexCompiler._create_tar_archive({"main.pdf": mock_pdf})
    container.get_archive.return_value = ([mock_tar], {})

    def create_side_effect(*args, **kwargs):
        volumes = kwargs.get("volumes", {})
        for host_path in volumes.keys():
            pdf_path = os.path.join(host_path, "main.pdf")
            with open(pdf_path, "wb") as f:
                f.write(mock_pdf)
        return container

    client.containers.create.side_effect = create_side_effect
    # First .get() raises ImageNotFound, .pull() is called, second .get() returns image
    client.images.get.side_effect = [ImageNotFound("Not local"), MagicMock()]

    compiler = LatexCompiler(docker_client=client)
    files = {"main.tex": r"\documentclass{article}\begin{document}Test\end{document}"}
    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf is not None
    client.images.pull.assert_called_once_with(compiler.config.image_name)


def test_fallback_to_local_image_when_pull_fails():
    client = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b"Output written on main.pdf (1 page)."
    mock_pdf = b"%PDF-1.5 Mock PDF"
    mock_tar = LatexCompiler._create_tar_archive({"main.pdf": mock_pdf})
    container.get_archive.return_value = ([mock_tar], {})

    def create_side_effect(*args, **kwargs):
        volumes = kwargs.get("volumes", {})
        for host_path in volumes.keys():
            pdf_path = os.path.join(host_path, "main.pdf")
            with open(pdf_path, "wb") as f:
                f.write(mock_pdf)
        return container

    client.containers.create.side_effect = create_side_effect
    client.images.pull.side_effect = DockerException("Network unavailable")

    def mock_get(name):
        if name == "career-agent/latex-sandbox:latest":
            return MagicMock()
        raise ImageNotFound(f"Not found: {name}")

    client.images.get.side_effect = mock_get

    compiler = LatexCompiler(docker_client=client)
    files = {"main.tex": r"\documentclass{article}\begin{document}Test\end{document}"}
    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf is not None


def test_compiler_cache_hit_skips_docker(mock_docker, tmp_path):
    client, _ = mock_docker
    cache = PdfCache(directory=tmp_path)
    compiler = LatexCompiler(docker_client=client, cache=cache)

    files = {"main.tex": r"\documentclass{article}\begin{document}Cache Me\end{document}"}

    # 1. First compilation - cache miss, invokes Docker
    res1 = compiler.compile(files=files)
    assert res1.success is True
    assert res1.pdf is not None
    assert client.containers.create.call_count == 1

    # 2. Second compilation with identical input - cache hit!
    res2 = compiler.compile(files=files)
    assert res2.success is True
    assert res2.pdf == res1.pdf
    assert "[Cache hit]" in res2.log
    # Docker containers.create must NOT be called again
    assert client.containers.create.call_count == 1


def test_compiler_cache_miss_with_modified_content(mock_docker, tmp_path):
    client, _ = mock_docker
    cache = PdfCache(directory=tmp_path)
    compiler = LatexCompiler(docker_client=client, cache=cache)

    files1 = {"main.tex": r"\documentclass{article}\begin{document}V1\end{document}"}
    files2 = {"main.tex": r"\documentclass{article}\begin{document}V2\end{document}"}

    res1 = compiler.compile(files=files1)
    assert res1.success is True
    assert client.containers.create.call_count == 1

    res2 = compiler.compile(files=files2)
    assert res2.success is True
    assert client.containers.create.call_count == 2


def test_compiler_cache_disabled_flag(mock_docker, tmp_path):
    client, _ = mock_docker
    cache = PdfCache(directory=tmp_path, enabled=False)
    compiler = LatexCompiler(docker_client=client, cache=cache)

    files = {"main.tex": r"\documentclass{article}\begin{document}No Cache\end{document}"}

    res1 = compiler.compile(files=files)
    assert res1.success is True
    assert client.containers.create.call_count == 1

    res2 = compiler.compile(files=files)
    assert res2.success is True
    assert client.containers.create.call_count == 2


# -----------------------------------------------------------------------------
# Integration Tests (Requires running Docker daemon and pre-built image)
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_real_docker_compile_integration():
    config = LatexSandboxConfig()
    if not is_docker_available_and_image_built(config.image_name):
        pytest.skip(
            f"Docker image '{config.image_name}' is not built or Docker daemon is unavailable."
        )

    compiler = LatexCompiler(config=config)
    tex_path = FIXTURES_DIR / "cv" / "main.tex"
    logo_path = FIXTURES_DIR / "cv" / "logo.png"

    files = {
        "main.tex": tex_path.read_text(encoding="utf-8"),
        "logo.png": logo_path.read_bytes(),
    }

    result = compiler.compile(files=files)

    assert result.success is True
    assert result.pdf is not None
    assert len(result.pdf) > 0
    assert result.pdf.startswith(b"%PDF")
