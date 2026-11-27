#!/usr/bin/env python3
"""Build the AI Sub icon: a white usage ring with an AI spark on HA blue.

The icon is drawn in code so the repository needs no binary source asset and
the README, HACS and the Home Assistant brand folder all get the same artwork.

Usage:
    python tools/make_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
BRAND = ROOT / "custom_components" / "ai_sub" / "brand"

BG = (0x18, 0xBC, 0xF2)  # Home Assistant logo blue
FG = (0xFF, 0xFF, 0xFF)
RADIUS = 0.22  # corner radius, as a fraction of the side
SS = 4  # supersampling for the master drawing
MASTER = 1024


def _sparkle(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, outer: float, inner: float
) -> None:
    """Draw a four-point spark (the "AI" mark) in the middle."""
    points = []
    for index in range(8):
        angle = math.radians(index * 45 - 90)
        radius = outer if index % 2 == 0 else inner
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=FG)


def _master() -> Image.Image:
    """Draw the square artwork at MASTER * SS pixels."""
    size = MASTER * SS
    image = Image.new("RGBA", (size, size), (*BG, 255))
    draw = ImageDraw.Draw(image)
    center = size / 2

    stroke = size * 0.095
    radius = size * 0.365 - stroke / 2
    draw.ellipse(
        (
            center - radius - stroke / 2,
            center - radius - stroke / 2,
            center + radius + stroke / 2,
            center + radius + stroke / 2,
        ),
        outline=FG,
        width=int(stroke),
    )
    _sparkle(draw, center, center, size * 0.165, size * 0.038)
    return image


def _rounded(image: Image.Image, size: int) -> Image.Image:
    """Downscale and apply the rounded-square mask."""
    corner = round(size * RADIUS)
    mask = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size * SS - 1, size * SS - 1), radius=corner * SS, fill=255
    )
    out = image.resize((size, size), Image.LANCZOS)
    out.putalpha(mask.resize((size, size), Image.LANCZOS))
    return out


def main() -> int:
    master = _master()
    ASSETS.mkdir(parents=True, exist_ok=True)
    BRAND.mkdir(parents=True, exist_ok=True)

    targets = {
        ASSETS / "icon.png": 256,
        BRAND / "icon.png": 256,
        BRAND / "icon@2x.png": 512,
    }
    for path, size in targets.items():
        _rounded(master, size).save(path, optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({size}x{size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
