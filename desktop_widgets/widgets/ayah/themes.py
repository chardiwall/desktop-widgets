from json import loads
from pathlib import Path

ART = Path(__file__).with_name("art")
SPEC = loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
SIZING = SPEC["sizing"]
PRESETS = SPEC["themes"]
