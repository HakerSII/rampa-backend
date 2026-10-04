"""F48: the local model is downloaded at start when missing (Hugging Face), with a memory guard."""
import json

import httpx
import pytest

from app.adapters.outbound import model_fetch, phi_onnx

REPO, SUB = "microsoft/Phi-3.5-vision-instruct-onnx", "gpu/gpu-int4-rtn-block-32"
FILES = {"genai_config.json": b'{"model": {}}', "phi-3.5-v-instruct-text.onnx": b"graph",
         "phi-3.5-v-instruct-text.onnx.data": b"w" * 5000, "tokenizer.json": b"{}"}


def hub(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == f"/api/models/{REPO}/tree/main/{SUB}":
            return httpx.Response(200, json=[{"type": "file", "path": f"{SUB}/{n}", "size": len(b)} for n, b in FILES.items()]
                                  + [{"type": "directory", "path": f"{SUB}/extra"}])
        for name, body in FILES.items():
            if request.url.path == f"/{REPO}/resolve/main/{SUB}/{name}":
                return httpx.Response(200, content=body)
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://huggingface.co")


def test_downloads_every_file_config_last(tmp_path):
    requests = []
    target = tmp_path / "model"
    model_fetch.ensure_model(str(target), REPO, SUB, client=hub(requests))
    assert {p.name for p in target.iterdir()} == set(FILES)
    assert (target / "phi-3.5-v-instruct-text.onnx.data").read_bytes() == FILES["phi-3.5-v-instruct-text.onnx.data"]
    downloads = [r for r in requests if "/resolve/" in r]
    assert downloads[-1].endswith("genai_config.json")  # its presence = the download finished
    assert model_fetch.is_complete(str(target))


def test_complete_model_is_not_downloaded_again(tmp_path):
    target = tmp_path / "model"
    model_fetch.ensure_model(str(target), REPO, SUB, client=hub([]))
    again = []
    model_fetch.ensure_model(str(target), REPO, SUB, client=hub(again))
    assert again == []


def test_interrupted_download_resumes_missing_files(tmp_path):
    target = tmp_path / "model"
    target.mkdir()
    (target / "tokenizer.json").write_bytes(FILES["tokenizer.json"])  # already there, right size
    (target / "phi-3.5-v-instruct-text.onnx.data.part").write_bytes(b"half")
    requests = []
    model_fetch.ensure_model(str(target), REPO, SUB, client=hub(requests))
    assert not any(r.endswith("tokenizer.json") for r in requests)
    assert not list(target.glob("*.part")) and model_fetch.is_complete(str(target))


def test_hub_error_raises(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)), base_url="https://huggingface.co")
    with pytest.raises(httpx.HTTPError):
        model_fetch.ensure_model(str(tmp_path / "m"), REPO, SUB, client=client)
    assert not model_fetch.is_complete(str(tmp_path / "m"))


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
    t = phi_onnx.preload("models/x")
    t.join(2)
    assert loaded == ["models/x"]


def test_preload_swallows_errors(fresh, monkeypatch):
    def boom(path):
        raise MemoryError("no")

    monkeypatch.setattr(phi_onnx, "load", boom)
    phi_onnx.preload("models/x").join(2)  # no exception escapes the thread


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
