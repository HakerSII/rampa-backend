"""F48: the local model is downloaded at start when missing (Hugging Face), with a memory guard."""
import json
from pathlib import Path

import pytest

from app.adapters.outbound import model_fetch, phi_onnx

REAL_PRELOAD = phi_onnx.preload  # conftest replaces it in every test (no background loads)
REPO, SUB = "microsoft/Phi-3.5-vision-instruct-onnx", "gpu/gpu-int4-rtn-block-32"


@pytest.fixture
def hub(monkeypatch):
    """Fake snapshot_download (as get_model.py): writes the subfolder's files under local_dir."""
    calls = []

    def snapshot(repo_id, allow_patterns, local_dir):
        calls.append((repo_id, allow_patterns, local_dir))
        target = Path(local_dir) / SUB
        target.mkdir(parents=True, exist_ok=True)
        (target / "genai_config.json").write_text("{}")
        (target / "phi-3.5-v-instruct-text.onnx.data").write_bytes(b"w" * 10)

    monkeypatch.setattr(model_fetch, "_snapshot_download", snapshot)
    return calls


def test_downloads_the_subfolder_like_get_model(tmp_path, hub):
    path = tmp_path / "models" / "gpu" / "gpu-int4-rtn-block-32"
    model_fetch.ensure_model(str(path), REPO, SUB)
    assert hub == [(REPO, [f"{SUB}/*"], str(tmp_path / "models"))]
    assert model_fetch.is_complete(str(path)) and (path / "genai_config.json").exists()


def test_complete_model_is_not_downloaded_again(tmp_path, hub):
    path = tmp_path / "models" / SUB
    model_fetch.ensure_model(str(path), REPO, SUB)
    model_fetch.ensure_model(str(path), REPO, SUB)
    assert len(hub) == 1


def test_a_model_copied_by_hand_counts_as_complete(tmp_path, hub):
    path = tmp_path / "models" / SUB
    path.mkdir(parents=True)
    (path / "genai_config.json").write_text("{}")
    model_fetch.ensure_model(str(path), REPO, SUB)
    assert hub == []


def test_interrupted_download_is_resumed(tmp_path, monkeypatch, hub):
    path = tmp_path / "models" / SUB

    def dies(repo_id, allow_patterns, local_dir):
        (Path(local_dir) / SUB).mkdir(parents=True, exist_ok=True)
        (Path(local_dir) / SUB / "genai_config.json").write_text("{}")  # some files are there, not all
        raise OSError("connection reset")

    real = model_fetch._snapshot_download
    monkeypatch.setattr(model_fetch, "_snapshot_download", dies)
    with pytest.raises(OSError):
        model_fetch.ensure_model(str(path), REPO, SUB)
    assert not model_fetch.is_complete(str(path))  # genai_config.json alone is not enough after a failed run
    monkeypatch.setattr(model_fetch, "_snapshot_download", real)
    model_fetch.ensure_model(str(path), REPO, SUB)
    assert model_fetch.is_complete(str(path)) and len(hub) == 1


def test_path_must_end_with_the_subfolder(tmp_path, hub):
    with pytest.raises(ValueError):
        model_fetch.ensure_model(str(tmp_path / "elsewhere"), REPO, SUB)


def test_memory_from_cgroup_v2(tmp_path):
    cg = tmp_path / "sys" / "fs" / "cgroup"
    cg.mkdir(parents=True)
    (cg / "memory.max").write_text(str(512 * 2**20))
    (cg / "memory.current").write_text(str(112 * 2**20))
    assert model_fetch.available_memory_mb(str(tmp_path)) == 400


def test_memory_from_meminfo_when_no_limit(tmp_path):
    cg = tmp_path / "sys" / "fs" / "cgroup"
    cg.mkdir(parents=True)
    (cg / "memory.max").write_text("max")
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "meminfo").write_text("MemTotal: 16000000 kB\nMemAvailable:    8192000 kB\n")
    assert model_fetch.available_memory_mb(str(tmp_path)) == 8000


def test_memory_unknown(tmp_path):
    assert model_fetch.available_memory_mb(str(tmp_path)) is None


# --- phi_onnx: download + guard + state ------------------------------------------

@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(phi_onnx, "_LOADED", {})
    monkeypatch.setattr(phi_onnx, "STATE", {})
    monkeypatch.setattr(phi_onnx, "_CONFIG", dict(phi_onnx._CONFIG))

    class FakeOg:
        class Model:
            def __init__(self, path):
                self.path = path

            def create_multimodal_processor(self):
                return "processor"

    monkeypatch.setattr(phi_onnx, "_og", lambda: FakeOg)


def test_load_downloads_a_missing_model_first(fresh, monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(model_fetch, "ensure_model", lambda path, repo, sub: fetched.append((path, repo, sub)))
    monkeypatch.setattr(model_fetch, "available_memory_mb", lambda: 8000)
    phi_onnx.configure(download=True, repo=REPO, subfolder=SUB, min_ram_mb=3500)
    phi_onnx.load(str(tmp_path / "m"))
    assert fetched == [(str(tmp_path / "m"), REPO, SUB)]
    assert phi_onnx.state(str(tmp_path / "m"))["state"] == "ready"


def test_no_download_when_disabled(fresh, monkeypatch, tmp_path):
    monkeypatch.setattr(model_fetch, "ensure_model", lambda *a: pytest.fail("downloaded"))
    monkeypatch.setattr(model_fetch, "available_memory_mb", lambda: None)
    phi_onnx.configure(download=False, repo=REPO, subfolder=SUB, min_ram_mb=3500)
    phi_onnx.load(str(tmp_path / "m"))
    assert phi_onnx.state(str(tmp_path / "m"))["state"] == "ready"


def test_memory_guard_refuses_to_load(fresh, monkeypatch, tmp_path):
    monkeypatch.setattr(model_fetch, "is_complete", lambda path: True)
    monkeypatch.setattr(model_fetch, "available_memory_mb", lambda: 512)
    phi_onnx.configure(download=True, repo=REPO, subfolder=SUB, min_ram_mb=3500)
    with pytest.raises(MemoryError):
        phi_onnx.load(str(tmp_path / "m"))
    st = phi_onnx.state(str(tmp_path / "m"))
    assert st["state"] == "error" and "512 MB" in st["detail"] and "3500 MB" in st["detail"]


def test_state_of_an_unused_model(fresh):
    assert phi_onnx.state("nowhere") == {"state": "off", "detail": ""}


def test_preload_runs_in_the_background(fresh, monkeypatch):
    loaded = []
    monkeypatch.setattr(phi_onnx, "load", lambda path: loaded.append(path))
    t = REAL_PRELOAD("models/x")
    t.join(2)
    assert loaded == ["models/x"]


def test_preload_swallows_errors(fresh, monkeypatch):
    def boom(path):
        raise MemoryError("no")

    monkeypatch.setattr(phi_onnx, "load", boom)
    REAL_PRELOAD("models/x").join(2)  # no exception escapes the thread


def test_settings_defaults():
    from app.config import Settings
    s = Settings(_env_file=None)
    assert (s.ai_model_download, s.ai_model_repo, s.ai_model_subfolder, s.ai_model_min_ram_mb) == \
        (True, REPO, SUB, 3500)


def test_onnx_available_when_it_can_be_downloaded(monkeypatch, tmp_path):
    from app.adapters.outbound import vision_onnx
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    phi_onnx.configure(download=False, repo=REPO, subfolder=SUB, min_ram_mb=0)
    assert vision_onnx.onnx_available(str(tmp_path / "missing")) is False
    phi_onnx.configure(download=True, repo=REPO, subfolder=SUB, min_ram_mb=0)
    assert vision_onnx.onnx_available(str(tmp_path / "missing")) is True
    phi_onnx.configure(download=False, repo=REPO, subfolder=SUB, min_ram_mb=0)
    json.dumps(phi_onnx.state("x"))  # state is JSON for /health
