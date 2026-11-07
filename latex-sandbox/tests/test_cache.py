import tempfile
from pathlib import Path

import pytest
from latex_sandbox.cache import CacheManager, PdfCache


@pytest.fixture
def temp_cache_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def test_cache_initialization(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir / "subdir")
    assert cache.directory.exists()
    assert cache.enabled is True


def test_cache_alias():
    assert CacheManager is PdfCache


def test_cache_key_deterministic(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    files = {"main.tex": r"\documentclass{article}\begin{document}Hello\end{document}"}

    key1 = cache.key(files=files, engine="xelatex", runs=1)
    key2 = cache.key(files=files, engine="xelatex", runs=1)
    assert key1 == key2
    assert len(key1) == 64  # SHA-256 hex string


def test_cache_key_different_for_different_content(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    files1 = {"main.tex": r"\documentclass{article}\begin{document}Hello\end{document}"}
    files2 = {"main.tex": r"\documentclass{article}\begin{document}World\end{document}"}

    assert cache.key(files=files1) != cache.key(files=files2)


def test_cache_key_different_for_different_engines_or_runs(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    files = {"main.tex": "content"}

    key_xe = cache.key(files=files, engine="xelatex", runs=1)
    key_pdf = cache.key(files=files, engine="pdflatex", runs=1)
    key_runs = cache.key(files=files, engine="xelatex", runs=2)

    assert key_xe != key_pdf
    assert key_xe != key_runs


def test_cache_key_with_string_input(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    tex = r"\documentclass{article}\begin{document}Test\end{document}"
    key = cache.key(files=tex)
    assert len(key) == 64


def test_cache_key_with_binary_assets(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    files1 = {"main.tex": "text", "logo.png": b"\x89PNG\r\n\x1a\n"}
    files2 = {"main.tex": "text", "logo.png": b"\x89PNG\r\n\x1a\nCHANGED"}

    assert cache.key(files=files1) != cache.key(files=files2)


def test_cache_get_miss(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    assert cache.get("nonexistent_hash") is None


def test_cache_save_and_get_hit(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    key = "test_hash_123"
    pdf_bytes = b"%PDF-1.5 test pdf content"

    saved_path = cache.save(key, pdf_bytes)
    assert saved_path is not None
    assert saved_path.exists()
    assert saved_path.name == f"{key}.pdf"

    retrieved = cache.get(key)
    assert retrieved == pdf_bytes


def test_cache_save_with_path(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    key = "test_hash_path"
    source_pdf = temp_cache_dir / "source.pdf"
    pdf_bytes = b"%PDF-1.5 path content"
    source_pdf.write_bytes(pdf_bytes)

    saved_path = cache.save(key, source_pdf)
    assert saved_path is not None
    assert cache.get(key) == pdf_bytes


def test_cache_disabled(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir, enabled=False)
    key = "disabled_hash"

    assert cache.save(key, b"content") is None
    assert cache.get(key) is None


def test_cache_clear(temp_cache_dir):
    cache = PdfCache(directory=temp_cache_dir)
    cache.save("k1", b"pdf1")
    cache.save("k2", b"pdf2")

    assert (temp_cache_dir / "k1.pdf").exists()
    assert (temp_cache_dir / "k2.pdf").exists()

    removed = cache.clear()
    assert removed == 2
    assert not (temp_cache_dir / "k1.pdf").exists()
    assert not (temp_cache_dir / "k2.pdf").exists()
