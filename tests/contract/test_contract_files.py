from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]
CONTRACT_DIR = ROOT / "contracts"


def test_openapi_contracts_are_yaml_documents_with_expected_version():
    for path in sorted(CONTRACT_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert document["openapi"] == "3.0.3"
        assert document["info"]["version"] == "0.1.0"


def test_public_contracts_expose_expected_service_boundaries():
    expected = {
        "agent-api.yaml": ["/api/v1/auth/demo-accounts", "/api/v1/auth/login", "/api/v1/conversations", "/api/v1/runs/{run_id}/appointment-selection"],
        "patient-ops-api.yaml": "/api/v1/agent-results",
        "clinic-core-api.yaml": "/api/v1/appointments",
    }

    for filename, paths in expected.items():
        document = yaml.safe_load((CONTRACT_DIR / filename).read_text(encoding="utf-8"))
        if isinstance(paths, str):
            paths = [paths]
        for path in paths:
            assert path in document["paths"]
