#!/usr/bin/env python3
"""Stage the native avatar pilot against a copy of AzClock 16.1."""

import argparse
import json
import math
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import sys

from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024

sys.path.insert(0, str(ROOT))
from desktop_widgets.bridge.gnome import HostError
from desktop_widgets.bridge.integration import BUNDLE, bundle_assets, prepare_extension, prepare_release


def frame_bounds(paths):
    bounds = []
    for path in paths:
        with Image.open(path) as frame:
            if frame.mode != "RGBA" or frame.size != (160, 220):
                raise ValueError(f"Invalid RGBA avatar frame {path.name}")
            bounds.append(frame.getchannel("A").getbbox())
    if any(box is None or box[0] == 0 or box[1] == 0 or box[2] == 160 or box[3] == 220
           for box in bounds):
        raise ValueError("An avatar frame is empty or touches the render edge")
    return bounds


def pack_walk(source, destination, listening=None):
    manifest = json.loads((source / "walk.json").read_text())
    fps, pivot, travel = (manifest[key] for key in ("fps", "pivot", "travel"))
    if not (isinstance(fps, int) and 1 <= fps <= 60 and len(pivot) == 2 and
            3 <= len(travel) <= 240 and all(math.isfinite(v) for v in (*pivot, *travel)) and
            travel[0] == travel[-1] == 0 and min(travel) == 0 and max(travel) > 0):
        raise ValueError("Invalid walk timing, pivot or travel path")

    paths = sorted(source.glob("*.png"))
    if [path.name for path in paths] != [f"{i:04}.png" for i in range(1, len(travel) + 1)]:
        raise ValueError("Walk frame numbers do not match the manifest")
    bounds = frame_bounds(paths)
    if any(abs(box[3] - pivot[1]) > 1 for box in bounds):
        raise ValueError("A walk frame loses vertical ground contact")

    listening_paths, listening_bounds, leisure = [], [], None
    if listening:
        leisure = json.loads((listening / "listening.json").read_text())
        listening_paths = sorted(listening.glob("*.png"))
        anchors = leisure["anchors"]
        headset_scale = leisure.get("headsetScale", 1)
        if not (1 <= leisure["fps"] <= 60 and 0 < leisure["seated"] < len(anchors) <= 120 and
                isinstance(headset_scale, (int, float)) and 0 < headset_scale <= 2 and
                [p.name for p in listening_paths] == [f"{i:04}.png" for i in range(1, len(anchors) + 1)] and
                all(len(anchor[name]) == 2 and all(math.isfinite(v) for v in anchor[name])
                    for anchor in anchors for name in ("head", "hand"))):
            raise ValueError("Invalid listening frame manifest")
        listening_bounds = frame_bounds(listening_paths)
        if listening_bounds[0] != bounds[0]:
            raise ValueError("The listening transition must start at the walk's rest pose")
    all_bounds = bounds + listening_bounds
    box = tuple(reduce(bound[i] for bound in all_bounds)
                for i, reduce in enumerate((min, min, max, max)))
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    if width * height * 4 * (len(paths) + len(listening_paths)) > 12 * MIB:
        raise ValueError("Avatar clips are too large for the 24 MiB working budget")
    pivot = [pivot[0] - x0, pivot[1] - y0]
    if not (0 < pivot[0] < width and 0 < pivot[1] <= height + 1):
        raise ValueError("Walk pivot is outside the packed frame")

    with Image.open(paths[0]) as first, Image.open(paths[-1]) as last:
        # Separate EEVEE runs can vary slightly in colour even at the same pose.
        difference = ImageChops.difference(first, last)
        if bounds[0] != bounds[-1] or max(ImageStat.Stat(difference).mean) > 0.1:
            raise ValueError("The walk must end in its original standing pose")

    if leisure:
        seated = leisure["seated"]
        leisure["back"] = max(frame_box[2] for frame_box in listening_bounds[seated:]) - x0
        floor = listening_bounds[seated][3]
        with Image.open(listening_paths[seated]) as frame:
            leisure["contact"] = frame.getchannel("A").crop((x0, floor - 3, x1, floor)).getbbox()[0]
        for anchor, frame_box in zip(leisure["anchors"], listening_bounds):
            anchor["ground"] = frame_box[3] - bounds[0][3]
            anchor["crown"] = frame_box[1] - y0
            for name in ("head", "hand"):
                anchor[name][0] -= x0
                anchor[name][1] -= y0
    for name, frames in (("rest", paths[:1]), ("walk", paths[1:-1]), ("listening", listening_paths[1:])):
        with (destination / f"{name}.rgba").open("wb") as pixels:
            for path in frames:
                with Image.open(path) as frame:
                    pixels.write(frame.crop(box).tobytes())
    manifest.update(width=width, height=height, pivot=pivot)
    (destination / "walk-data.js").write_text(
        f"export const walk = {json.dumps(manifest)};\nexport const listening = {json.dumps(leisure)};\n")
    packed = len(paths) - 1 + max(0, len(listening_paths) - 1)
    print(f"Packed {packed} frame slots at {width} × {height}, "
          f"{width * height * 4 * packed / MIB:.2f} MiB of RGBA")


def stage(source, walk, output, listening=None):
    output = output.parent.resolve() / output.name
    if output.exists() or output.is_symlink() or output.is_relative_to(source):
        raise ValueError("Choose a new output directory outside the AzClock installation")
    _, extension = prepare_extension(source)
    audio = ROOT / "dist/native/avatar-audio"
    if not audio.is_file():
        raise ValueError("Build the native Avatar files before staging the preview.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".avatar-stage-") as temp:
        root = Path(temp)
        frames = root / "frames"
        frames.mkdir()
        pack_walk(walk, frames, listening)
        assets = bundle_assets(frames, audio)
        candidate = root / "extension"
        shutil.copytree(source, candidate, ignore=lambda path, _: {BUNDLE.split("/")[0]} if Path(path) == source else ())
        (candidate / "extension.js").write_bytes(prepare_release(candidate, extension, assets))
        candidate.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("azclock", type=Path, nargs="?")
    parser.add_argument("walk", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--listening", type=Path)
    parser.add_argument("--pack-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.pack_only:
            args.output.mkdir(parents=True, exist_ok=True)
            pack_walk(args.walk, args.output, args.listening)
        else:
            if args.azclock is None:
                parser.error("AzClock source is required when staging a preview")
            stage(args.azclock.resolve(), args.walk.resolve(), args.output.absolute(), args.listening)
    except (OSError, ValueError, KeyError, TypeError, HostError) as error:
        parser.exit(1, f"Cannot stage avatar pilot: {error}\n")
