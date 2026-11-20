from json import loads
from pathlib import Path

DESIGNS = loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
