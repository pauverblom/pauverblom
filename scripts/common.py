"""Shared helpers: config, themes, SVG utilities, README marker editing."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
README = ROOT / "README.md"

FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

THEMES = {
    "dark": {
        "bg": "#0b0f14",
        "panel": "#101820",
        "border": "#1f2b38",
        "grid": "#1a2530",
        "text": "#d6e2ee",
        "dim": "#6f8295",
        "accent": "#3ddc97",
        "accent_soft": "rgba(61,220,151,0.16)",
        "cyan": "#4cc9f0",
        "warn": "#ffb547",
        "alert": "#ff5c5c",
        "off": "#243241",
    },
    "light": {
        "bg": "#f6f8fa",
        "panel": "#ffffff",
        "border": "#d0d7de",
        "grid": "#e4e9ee",
        "text": "#1f2328",
        "dim": "#5f6b77",
        "accent": "#1a7f37",
        "accent_soft": "rgba(26,127,55,0.12)",
        "cyan": "#0969da",
        "warn": "#9a6700",
        "alert": "#cf222e",
        "off": "#dfe5ea",
    },
}


def load_config() -> dict:
    with open(ROOT / "profile.json", encoding="utf-8") as f:
        return json.load(f)


def esc(text) -> str:
    return escape(str(text), {'"': "&quot;"})


def truncate(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def svg_open(w: int, h: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
        f"<title>{esc(title)}</title>"
    )


def smooth_path(points: list[tuple[float, float]], tension: float = 0.5,
                y_floor: float | None = None) -> str:
    """Catmull-Rom spline through points, as an SVG cubic Bézier path.

    y_floor clamps control points so the curve never dips below a baseline.
    """
    clamp = (lambda y: min(y, y_floor)) if y_floor is not None else (lambda y: y)
    if not points:
        return ""
    if len(points) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    d = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, clamp(p1[1] + (p2[1] - p0[1]) * tension / 3))
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, clamp(p2[1] - (p3[1] - p1[1]) * tension / 3))
        d.append(
            f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
        )
    return " ".join(d)


def write_text(path: Path, content: str) -> bool:
    """Write only if changed; returns True when the file changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def replace_section(text: str, name: str, body: str) -> str:
    """Replace content between <!-- NAME:START --> and <!-- NAME:END -->."""
    pattern = re.compile(
        rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.DOTALL
    )
    if not pattern.search(text):
        raise SystemExit(f"README is missing the {name}:START/END markers")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body.strip()}\n{m.group(3)}", text)


def token() -> str | None:
    return os.environ.get("GH_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
