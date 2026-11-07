import io
import logging
import os
import tarfile
import tempfile
import time
from dataclasses import dataclass
from typing import Mapping, Optional, Union
import docker
from docker.errors import DockerException, ImageNotFound

from latex_sandbox.cache import PdfCache
from latex_sandbox.config import LatexSandboxConfig
from latex_sandbox.validation import validate_files

logger = logging.getLogger(__name__)


@dataclass
class CompilationResult:
    """Result of a LaTeX compilation attempt."""

    success: bool
    pdf: Optional[bytes] = None
    log: str = ""
    error: Optional[str] = None


class LatexCompiler:
    """Compiles LaTeX sources into PDF using isolated disposable Docker containers."""

    def __init__(
        self,
        config: Optional[LatexSandboxConfig] = None,
        docker_client: Optional[docker.DockerClient] = None,
        cache: Optional[PdfCache] = None,
    ) -> None:
        self.config = config or LatexSandboxConfig()
        self._docker_client = docker_client
        self.cache = cache or PdfCache(
            directory=self.config.cache_dir,
            enabled=self.config.cache_enabled,
        )

    @property
    def docker_client(self) -> docker.DockerClient:
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env(
                    timeout=max(self.config.timeout_seconds + 30, 90)
                )
            except DockerException as e:
                raise RuntimeError(
                    f"Failed to initialize Docker client: {e}. Ensure Docker daemon is running."
                ) from e
        return self._docker_client

    def pull_image(self, image_name: Optional[str] = None) -> None:
        """Explicitly pull the sandbox Docker image from the registry."""
        target = image_name or self.config.image_name
        logger.info("Pulling sandbox image from registry: %s", target)
        self.docker_client.images.pull(target)

    def _resolve_image(self) -> tuple[Optional[str], Optional[str]]:
        """Ensure the sandbox Docker image is available locally, pulling from the registry if needed.

        Returns:
            Tuple of (resolved_image_name, error_message). If successful, error_message is None.
        """
        target_image = self.config.image_name

        # 1. Check if target image is already available in the local Docker daemon
        try:
            self.docker_client.images.get(target_image)
            return target_image, None
        except (ImageNotFound, DockerException):
            pass

        # 2. If auto_pull is enabled, attempt to pull from the registry
        pull_error: Optional[str] = None
        if self.config.auto_pull:
            try:
                logger.info(
                    "Docker image '%s' not found locally. Pulling from registry...",
                    target_image,
                )
                self.docker_client.images.pull(target_image)
                self.docker_client.images.get(target_image)
                return target_image, None
            except Exception as exc:
                pull_error = str(exc)
                logger.warning(
                    "Failed to pull image '%s' from registry: %s", target_image, exc
                )

        # 3. Check for local fallbacks (e.g. locally built image without registry prefix)
        fallback_candidates = []
        if "/" in target_image:
            fallback_candidates.append("career-agent/latex-sandbox:latest")
            fallback_candidates.append("latex-sandbox:latest")
            fallback_candidates.append(target_image.split("/")[-1])

        for fallback in fallback_candidates:
            if fallback == target_image:
                continue
            try:
                self.docker_client.images.get(fallback)
                logger.info("Using local fallback sandbox image: %s", fallback)
                return fallback, None
            except (ImageNotFound, DockerException):
                continue

        error_msg = f"Docker image '{target_image}' not found."
        if pull_error:
            error_msg += f" Failed to pull from registry: {pull_error}."
        else:
            error_msg += " Please build the image or enable registry auto-pull."

        return None, error_msg

    @staticmethod
    def _create_tar_archive(files: Mapping[str, Union[str, bytes]]) -> bytes:
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            dirs_added = set()
            for rel_path, content in files.items():
                norm_path = os.path.normpath(rel_path).lstrip("/")
                parts = norm_path.split(os.sep)
                for i in range(1, len(parts)):
                    parent = "/".join(parts[:i])
                    if parent not in dirs_added:
                        ti = tarfile.TarInfo(name=parent)
                        ti.type = tarfile.DIRTYPE
                        ti.mode = 0o755
                        ti.mtime = int(time.time())
                        tar.addfile(ti)
                        dirs_added.add(parent)

                encoded = content.encode("utf-8") if isinstance(content, str) else content
                ti = tarfile.TarInfo(name=norm_path)
                ti.size = len(encoded)
                ti.mtime = int(time.time())
                ti.mode = 0o644
                tar.addfile(ti, io.BytesIO(encoded))
        return tar_stream.getvalue()

    @staticmethod
    def _extract_file_from_tar(stream_gen, target_filename: str) -> Optional[bytes]:
        file_obj = io.BytesIO()
        for chunk in stream_gen:
            if isinstance(chunk, bytes):
                file_obj.write(chunk)
        file_obj.seek(0)
        try:
            with tarfile.open(fileobj=file_obj, mode="r") as tar:
                for member in tar.getmembers():
                    if os.path.basename(member.name) == target_filename:
                        extracted = tar.extractfile(member)
                        if extracted:
                            return extracted.read()
        except Exception as e:
            logger.debug("Error extracting file %s from tar archive: %s", target_filename, e)
        return None

    def compile(
        self,
        files: Mapping[str, Union[str, bytes]],
        main_file: str = "main.tex",
        engine: Optional[str] = None,
        runs: Optional[int] = None,
    ) -> CompilationResult:
        """Compile a dictionary of files into a PDF document.

        Args:
            files: Dict mapping relative file paths to content (str or bytes).
            main_file: Name of the primary .tex file.
            engine: TeX engine executable (e.g. 'xelatex', 'pdflatex'). Defaults to config.default_engine.
            runs: Number of compilation passes. Defaults to config.runs.

        Returns:
            CompilationResult with success flag, pdf bytes (if successful), and execution logs.
        """
        validate_files(files, main_file=main_file)

        selected_engine = engine or self.config.default_engine
        selected_runs = runs or self.config.runs

        # Check PDF cache
        cache_key = self.cache.key(
            files=files,
            main_file=main_file,
            engine=selected_engine,
            runs=selected_runs,
        )
        cached_pdf = self.cache.get(cache_key)
        if cached_pdf is not None:
            logger.info("PDF cache hit for key: %s", cache_key)
            return CompilationResult(
                success=True,
                pdf=cached_pdf,
                log="[Cache hit] Loaded compiled PDF from cache.",
                error=None,
            )

        with tempfile.TemporaryDirectory(prefix="latex_build_") as temp_dir:
            # Populate workspace files
            for rel_path, content in files.items():
                dest_path = os.path.join(temp_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if isinstance(content, str):
                    with open(dest_path, "w", encoding="utf-8") as f:
                        f.write(content)
                else:
                    with open(dest_path, "wb") as f:
                        f.write(content)

            # Ensure image is available locally or pulled from registry
            target_image, image_error = self._resolve_image()
            if target_image is None or image_error is not None:
                return CompilationResult(
                    success=False,
                    pdf=None,
                    log="",
                    error=image_error or f"Docker image '{self.config.image_name}' not found.",
                )

            # Prepare execution command
            # Security flags: -no-shell-escape forced to disable \write18 command execution
            cmd_args = [
                selected_engine,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                main_file,
            ]

            if selected_runs > 1:
                single_cmd = " ".join(cmd_args)
                cmd_str = " && ".join([single_cmd] * selected_runs)
                command = ["sh", "-c", cmd_str]
            else:
                command = cmd_args

            container = None
            logs = ""
            success = False
            pdf_bytes = None

            try:
                container = self.docker_client.containers.create(
                    image=target_image,
                    command=command,
                    working_dir="/workspace",
                    network_mode="none" if self.config.network_disabled else "bridge",
                    mem_limit=self.config.memory_limit,
                )

                # Transfer workspace files directly into container via Docker tar stream.
                # This works seamlessly whether the compiler runs on the host or inside a container (DooD)
                # without requiring host-path volume binds.
                try:
                    tar_bytes = self._create_tar_archive(files)
                    container.put_archive("/workspace", tar_bytes)
                except Exception as put_err:
                    logger.debug("container.put_archive failed or not supported: %s", put_err)

                container.start()

                # Wait for container execution with timeout
                result = container.wait(timeout=self.config.timeout_seconds)
                exit_code = result.get("StatusCode", 1)

                logs = container.logs(stdout=True, stderr=True).decode(
                    "utf-8", errors="replace"
                )

                pdf_filename = os.path.splitext(main_file)[0] + ".pdf"
                pdf_path = os.path.join(temp_dir, pdf_filename)

                if exit_code == 0:
                    try:
                        stream_gen, _ = container.get_archive(f"/workspace/{pdf_filename}")
                        pdf_bytes = self._extract_file_from_tar(stream_gen, pdf_filename)
                        if pdf_bytes is not None:
                            success = True
                    except Exception as extract_err:
                        logger.debug("Failed to extract PDF via get_archive: %s", extract_err)

                # Fallback to temp_dir if volume mount was used (for mock tests or local volume mounts)
                if not success and exit_code == 0 and os.path.exists(pdf_path):
                    success = True
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()

            except Exception as e:
                return CompilationResult(
                    success=False,
                    pdf=None,
                    log=logs,
                    error=str(e),
                )
            finally:
                if container:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass

            if success and pdf_bytes:
                self.cache.save(cache_key, pdf_bytes)

            return CompilationResult(
                success=success,
                pdf=pdf_bytes,
                log=logs,
                error=None if success else f"Compilation failed with logs:\n{logs}",
            )
