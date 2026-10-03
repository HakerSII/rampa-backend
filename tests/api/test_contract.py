"""Every path+method in features/*/openapi.yaml exists in the running app (MVP contract)."""
from pathlib import Path

import pytest
import yaml

from app.adapters.inbound.http.main import API_PREFIX, create_app

SPECS = sorted(Path(__file__).parents[2].glob("features/*/openapi.yaml"))
METHODS = {"get", "post", "put", "patch", "delete"}


def contract_operations():
    for spec in SPECS:
        for path, ops in yaml.safe_load(spec.read_text(encoding="utf-8"))["paths"].items():
            for method in METHODS & set(ops):
                yield spec.parent.name, method, path


@pytest.fixture(scope="module")
def app_operations(tmp_path_factory):
    from app.config import Settings
    schema = create_app(Settings(media_dir=str(tmp_path_factory.mktemp("m")))).openapi()
    return {(m, p.removeprefix(API_PREFIX)) for p, ops in schema["paths"].items() for m in ops}


def test_specs_found():
    assert len(SPECS) == 7


@pytest.mark.parametrize("feature, method, path", list(contract_operations()))
def test_operation_implemented(app_operations, feature, method, path):
    # FastAPI uses {place_id}, specs use {placeId} → compare with params normalised
    norm = lambda p: "/".join("{}" if s.startswith("{") else s for s in p.split("/"))
    assert (method, norm(path)) in {(m, norm(p)) for m, p in app_operations}, f"{feature}: {method.upper()} {path}"


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.parent.name)
def test_spec_is_valid_openapi(spec):
    from openapi_spec_validator import validate
    validate(yaml.safe_load(spec.read_text(encoding="utf-8")))
