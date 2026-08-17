from pathlib import Path
from typing import Any, Dict

import yaml


def load_fixtures(path: Path = None) -> Dict[str, Any]:
    if path is None:
        path = Path(__file__).parents[3] / "data" / "synthetic" / "fixtures.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
