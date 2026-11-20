from json import loads
from pathlib import Path

ART = Path(__file__).with_name("art")
SPEC = loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
SIZING = SPEC["sizing"]
PRESETS = SPEC["themes"]
THEMES = {
    name: tuple(preset[key] for key in ("style", "text", "accent", "background", "font"))
    for name, preset in PRESETS.items()
}
