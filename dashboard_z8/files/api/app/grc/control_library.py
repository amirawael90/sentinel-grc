"""Control library loader (task Z1).

Loads every *.yaml file in data/controls/, validates each control and
exposes simple helpers. Run `python control_library.py` to print a summary.
"""
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

CONTROLS_DIR = Path(__file__).parent / "data" / "controls"


class Control(BaseModel):
    id: str
    framework: str
    function: Optional[str] = None
    category: str
    category_id: str
    title: Optional[str] = None
    description: str
    asset_class: Optional[str] = None
    implementation_groups: list[str] = []
    weight: float = Field(default=1.0, gt=0)
    owner: str = "TBD"
    status: Literal["Implemented", "Partial", "Not implemented", "Not applicable"]
    maturity: int = Field(ge=0, le=5)
    review_date: Optional[date] = None
    platform_features: list[str] = []


def load_controls(directory: Path = CONTROLS_DIR) -> list[Control]:
    controls: list[Control] = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, list):
                raise ValueError(
                    f"{path.name} is not a list of controls. "
                    "Keep only control files in data/controls/ "
                    "(move other files, e.g. the mapping file, elsewhere)."
                )
            for item in data:
                controls.append(Control(**item))
    ids = [c.id for c in controls]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Duplicate control ids: {sorted(duplicates)}")
    return controls


def by_framework(controls: list[Control]) -> dict[str, list[Control]]:
    result: dict[str, list[Control]] = {}
    for c in controls:
        result.setdefault(c.framework, []).append(c)
    return result


def gaps(controls: list[Control]) -> list[Control]:
    """Controls no platform feature covers (shown as gaps in Compliance Center)."""
    return [c for c in controls if not c.platform_features]


if __name__ == "__main__":
    controls = load_controls()
    print(f"Loaded {len(controls)} controls")
    for fw, items in by_framework(controls).items():
        print(f"  {fw}: {len(items)}")
    print(f"Controls with no platform feature: {len(gaps(controls))}")
