"""F48: get the local model when it is missing (Hugging Face, as get_model.py) and measure the free memory.

The download is `snapshot_download(repo, allow_patterns=["<subfolder>/*"], local_dir=<models root>)`, so
AI_MODEL_PATH must end with AI_MODEL_SUBFOLDER (default models/gpu/gpu-int4-rtn-block-32). huggingface_hub resumes
interrupted downloads; a `.downloading` marker keeps a half-downloaded folder from counting as complete."""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

MARKER_DONE, MARKER_BUSY = ".complete", ".downloading"
MB = 2**20


def _snapshot_download(repo_id: str, allow_patterns: list[str], local_dir: str) -> None:
    from huggingface_hub import snapshot_download  # optional extra "ai"

    snapshot_download(repo_id=repo_id, allow_patterns=allow_patterns, local_dir=local_dir)


def is_complete(model_path: str) -> bool:
    """Downloaded completely (marker), or copied by hand (config present, no unfinished download)."""
    path = Path(model_path)
    return (path / MARKER_DONE).exists() or ((path / "genai_config.json").exists() and not (path / MARKER_BUSY).exists())


def ensure_model(model_path: str, repo: str, subfolder: str) -> None:
    """Download the model folder unless it is complete (blocking: call from a thread)."""
    if is_complete(model_path):
        return
    path = Path(model_path)
    sub = subfolder.strip("/")
    if path.as_posix().rstrip("/")[-len(sub):] != sub:
        raise ValueError(f"AI_MODEL_PATH {model_path} must end with AI_MODEL_SUBFOLDER {sub}")
    root = Path(path.as_posix()[: -len(sub)] or ".")
    path.mkdir(parents=True, exist_ok=True)
    (path / MARKER_BUSY).touch()
    log.info("downloading the local model %s/%s → %s (~2.6 GB)", repo, sub, path)
    _snapshot_download(repo, [f"{sub}/*"], str(root))
    (path / MARKER_DONE).touch()
    (path / MARKER_BUSY).unlink(missing_ok=True)
    log.info("local model downloaded: %s", path)


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def available_memory_mb(root: str = "/") -> int | None:
    """Free memory for this process in MB: container limit (cgroup v2/v1) and/or MemAvailable; None if unknown."""
    base = Path(root)
    values = []
    limit, used = _read(base / "sys/fs/cgroup/memory.max"), _read(base / "sys/fs/cgroup/memory.current")
    if limit and limit != "max" and used:
        values.append((int(limit) - int(used)) // MB)
    limit, used = (_read(base / "sys/fs/cgroup/memory/memory.limit_in_bytes"),
                   _read(base / "sys/fs/cgroup/memory/memory.usage_in_bytes"))
    if limit and used and int(limit) < 2**60:  # "no limit" is a huge number in cgroup v1
        values.append((int(limit) - int(used)) // MB)
    meminfo = _read(base / "proc/meminfo")
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                values.append(int(line.split()[1]) // 1024)
    return min(values) if values else None
