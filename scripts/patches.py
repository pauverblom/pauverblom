"""Mission patches: one embroidered-style SVG badge per project in profile.json,
plus the README table that links them.

Usage: python scripts/patches.py
"""

from __future__ import annotations

from common import ASSETS, FONT, README, esc, load_config, replace_section, write_text

SIZE = 168
C = SIZE / 2

# Emblems are drawn in a 64x64 box centred on the patch, stroke = patch colour.
EMBLEMS = {
    "rocket": """
      <path d="M32 6 C42 16 44 30 40 44 H24 C20 30 22 16 32 6 Z" fill="{fill}" stroke="{col}" stroke-width="2.4"/>
      <circle cx="32" cy="24" r="5" fill="{bg}" stroke="{col}" stroke-width="2.2"/>
      <path d="M24 34 L15 46 L24 44 Z M40 34 L49 46 L40 44 Z" fill="{col}"/>
      <path d="M27 48 Q32 62 37 48" fill="none" stroke="{col}" stroke-width="2.4" stroke-linecap="round"/>""",
    "wave": """
      <rect x="6" y="12" width="52" height="40" rx="4" fill="{fill}" stroke="{col}" stroke-width="2.4"/>
      <path d="M10 32 L18 32 L22 20 L28 44 L34 24 L38 36 L42 32 L54 32" fill="none" stroke="{col}"
            stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>""",
    "braces": """
      <path d="M22 10 C14 10 16 22 16 26 C16 30 10 32 10 32 C10 32 16 34 16 38 C16 42 14 54 22 54"
            fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round"/>
      <path d="M42 10 C50 10 48 22 48 26 C48 30 54 32 54 32 C54 32 48 34 48 38 C48 42 50 54 42 54"
            fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round"/>
      <circle cx="26" cy="32" r="2.6" fill="{col}"/><circle cx="32" cy="32" r="2.6" fill="{col}"/>
      <circle cx="38" cy="32" r="2.6" fill="{col}"/>""",
    "orbit": """
      <ellipse cx="32" cy="32" rx="28" ry="11" fill="none" stroke="{col}" stroke-width="2.2" transform="rotate(-25 32 32)"/>
      <circle cx="32" cy="32" r="11" fill="{fill}" stroke="{col}" stroke-width="2.4"/>
      <circle cx="55" cy="21" r="4" fill="{col}"/>""",
    "cube": """
      <path d="M32 8 L54 20 L54 44 L32 56 L10 44 L10 20 Z" fill="{fill}" stroke="{col}" stroke-width="2.4" stroke-linejoin="round"/>
      <path d="M10 20 L32 32 L54 20 M32 32 L32 56" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"/>""",
    "spark": """
      <path d="M32 6 C34 24 40 30 58 32 C40 34 34 40 32 58 C30 40 24 34 6 32 C24 30 30 24 32 6 Z"
            fill="{fill}" stroke="{col}" stroke-width="2.4" stroke-linejoin="round"/>
      <circle cx="50" cy="14" r="3" fill="{col}"/>""",
}

BG = "#0d141c"  # patches are self-contained so they read on light and dark pages


def arc(r: float, top: bool) -> str:
    """Circle arc for textPath: upper arc runs left→right clockwise, lower arc left→right counter-clockwise."""
    if top:
        return f"M{C - r},{C} A{r},{r} 0 0 1 {C + r},{C}"
    return f"M{C - r},{C} A{r},{r} 0 0 0 {C + r},{C}"


def patch_svg(p: dict) -> str:
    col = p.get("color", "#3ddc97")
    emblem = EMBLEMS.get(p.get("emblem"), EMBLEMS["rocket"]).format(
        col=col, fill=f"{col}22", bg=BG)
    name, tag = p["name"].upper(), p.get("tagline", "").upper()
    # shrink letter spacing for long names so they stay on the upper arc
    ls_name = max(0.6, 3.2 - 0.3 * max(0, len(name) - 6))
    fs_name = 13 if len(name) <= 11 else 11.5
    ls_tag = max(0.4, 2.2 - 0.12 * max(0, len(tag) - 8))
    pid = p["id"]
    stars = "".join(
        f'<circle cx="{C + s * 66}" cy="{C}" r="2.6" fill="{col}"/>' for s in (-1, 1))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}" role="img" aria-label="{esc(p['name'])} mission patch">
<title>{esc(p['name'])}</title>
<defs>
  <path id="top-{pid}" d="{arc(64, True)}"/>
  <path id="bot-{pid}" d="{arc(66, False)}"/>
</defs>
<circle cx="{C}" cy="{C}" r="{C - 2}" fill="{BG}" stroke="{col}" stroke-width="3"/>
<circle cx="{C}" cy="{C}" r="{C - 9}" fill="none" stroke="{col}" stroke-width="1" stroke-dasharray="2 3" opacity=".7"/>
<circle cx="{C}" cy="{C}" r="46" fill="none" stroke="{col}" stroke-width="1.6" opacity=".9"/>
{stars}
<text font-family="{FONT}" font-size="{fs_name}" font-weight="700" fill="#e9eef3" letter-spacing="{ls_name:.2f}">
  <textPath href="#top-{pid}" startOffset="50%" text-anchor="middle">{esc(name)}</textPath></text>
<text font-family="{FONT}" font-size="10" fill="{col}" letter-spacing="{ls_tag:.2f}">
  <textPath href="#bot-{pid}" startOffset="50%" text-anchor="middle">{esc(tag)}</textPath></text>
<g transform="translate({C - 32},{C - 32})">{emblem}</g>
</svg>
"""


def readme_table(patches: list[dict], per_row: int = 3) -> str:
    rows = []
    for i in range(0, len(patches), per_row):
        cells = []
        for p in patches[i:i + per_row]:
            cells.append(
                f'<td align="center" width="33%"><a href="{esc(p["url"])}">'
                f'<img src="assets/patches/{esc(p["id"])}.svg" width="132" alt="{esc(p["name"])} mission patch"/></a><br/>'
                f'<sub>{esc(p.get("description", ""))}</sub></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return '<table align="center">\n' + "\n".join(rows) + "\n</table>"


def main() -> None:
    cfg = load_config()
    for p in cfg["patches"]:
        write_text(ASSETS / "patches" / f"{p['id']}.svg", patch_svg(p))
    readme = README.read_text(encoding="utf-8")
    write_text(README, replace_section(readme, "PATCHES", readme_table(cfg["patches"])))
    print(f"{len(cfg['patches'])} patches rendered")


if __name__ == "__main__":
    main()
