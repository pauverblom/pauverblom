"""Ground-station telemetry for the GitHub profile.

Pulls contribution and event data from the GitHub API and renders:
  assets/telemetry-{dark,light}.svg       live telemetry panel
  assets/flight-profile-{dark,light}.svg  last 52 weeks as a flight profile

Usage:
  python scripts/telemetry.py            # live data (needs GITHUB_TOKEN or GH_STATS_TOKEN)
  python scripts/telemetry.py --mock     # synthetic data, for local previews
"""

from __future__ import annotations

import argparse
import json
import math
import random
import urllib.request
from datetime import date, datetime, timedelta, timezone

from common import (
    ASSETS, FONT, THEMES, esc, load_config, smooth_path, svg_open, token,
    truncate, write_text,
)

API = "https://api.github.com"

# --------------------------------------------------------------------------- data


def _request(url: str, body: dict | None = None) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-telemetry",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    tok = token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_days(user: str, now: datetime) -> dict[date, int]:
    """Daily contribution counts for the last ~53 weeks (GraphQL, token required)."""
    start = (now - timedelta(days=370)).replace(hour=0, minute=0, second=0, microsecond=0)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { weeks { contributionDays { date contributionCount } } }
        }
      }
    }"""
    res = _request(
        f"{API}/graphql",
        {"query": query, "variables": {
            "login": user, "from": start.isoformat(), "to": now.isoformat()}},
    )
    if "errors" in res:
        raise SystemExit(f"GraphQL error: {res['errors']}")
    weeks = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {
        date.fromisoformat(d["date"]): d["contributionCount"]
        for w in weeks for d in w["contributionDays"]
    }


def fetch_events(user: str, skip_repos: list[str]) -> list[dict]:
    """Recent public events, condensed into ground-station log lines."""
    raw = _request(f"{API}/users/{user}/events/public?per_page=100")
    skip = {r.lower() for r in skip_repos}
    out: list[dict] = []
    for ev in raw:  # newest first
        repo = ev["repo"]["name"]
        if repo.lower() in skip:
            continue
        p, kind, t = ev.get("payload", {}), ev["type"], ev["created_at"]
        tag = text = None
        if kind == "PushEvent":
            # A run of consecutive pushes to one repo becomes a single log line.
            prev = out[-1] if out else None
            if prev and prev["tag"] == "PUSH" and prev["repo"] == repo:
                prev["pushes"] += 1
                prev["text"] = f"{prev['pushes']} pushes → {repo}"
                continue
            branch = (p.get("ref") or "").removeprefix("refs/heads/")
            out.append({"time": t, "tag": "PUSH", "repo": repo, "pushes": 1,
                        "text": f"pushed → {repo}" + (f":{branch}" if branch else "")})
            continue
        elif kind == "PullRequestEvent":
            pr, action = p.get("pull_request", {}), p.get("action")
            num = p.get("number") or pr.get("number")
            if action == "closed" and pr.get("merged"):
                tag, text = "MERGE", f"PR #{num} merged · {repo}"
            elif action in ("opened", "reopened"):
                tag, text = "PR", f"PR #{num} {action} · {repo}"
        elif kind == "PullRequestReviewEvent":
            num = p.get("pull_request", {}).get("number")
            tag, text = "REVIEW", f"reviewed PR #{num} · {repo}"
        elif kind == "ReleaseEvent" and p.get("action") == "published":
            tag, text = "REL", f"{p.get('release', {}).get('tag_name', 'release')} released · {repo}"
        elif kind == "CreateEvent" and p.get("ref_type") in ("repository", "tag"):
            if p["ref_type"] == "repository":
                tag, text = "NEW", f"repository created · {repo}"
            else:
                tag, text = "TAG", f"{p.get('ref')} tagged · {repo}"
        elif kind == "IssuesEvent" and p.get("action") == "opened":
            tag, text = "ISSUE", f"issue #{p.get('issue', {}).get('number')} opened · {repo}"
        elif kind == "ForkEvent":
            tag, text = "FORK", f"forked {repo}"
        if tag and (not out or out[-1]["text"] != text):
            out.append({"time": t, "tag": tag, "repo": repo, "text": text})
    return out


def mock_data(now: datetime) -> tuple[dict[date, int], list[dict]]:
    rng = random.Random(42)
    days: dict[date, int] = {}
    today = now.date()
    for i in range(371):
        d = today - timedelta(days=370 - i)
        season = 1.0 + 0.8 * math.sin(i / 58.0) + (1.6 if 290 < i < 330 else 0)
        weekend = 0.45 if d.weekday() >= 5 else 1.0
        burst = rng.random() < 0.06
        lam = max(0.0, season * weekend * (5 if burst else 1.6))
        days[d] = 0 if rng.random() < 0.18 else int(rng.expovariate(1 / (lam + 0.01)))
    stamp = lambda h: (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = [
        {"time": stamp(3), "tag": "PUSH", "text": "4 commits → faraday-rocketry/frfmd:svelte-migration"},
        {"time": stamp(20), "tag": "PR", "text": "PR #5488 opened · FabricMC/fabric-api"},
        {"time": stamp(29), "tag": "PUSH", "text": "2 commits → Pauverblom/flight-affinity:main"},
        {"time": stamp(51), "tag": "MERGE", "text": "PR #112 merged · faraday-rocketry/frlib"},
        {"time": stamp(75), "tag": "REVIEW", "text": "reviewed PR #41 · faraday-rocketry/frfmd"},
        {"time": stamp(98), "tag": "REL", "text": "v2.3.0 released · Pauverblom/claude-skills"},
    ]
    return days, events


# ----------------------------------------------------------------------- analysis

PHASES = ["BOOST", "COAST", "APOGEE", "DESCENT", "RECOVERY"]


def analyse(days: dict[date, int], now: datetime) -> dict:
    today = now.date()
    get = lambda d: days.get(d, 0)
    week = lambda end: sum(get(end - timedelta(days=k)) for k in range(7))
    v7, vprev = week(today), week(today - timedelta(days=7))
    recent_weeks = [week(today - timedelta(days=7 * k)) for k in range(8)]
    ytd = sum(c for d, c in days.items() if d.year == today.year and d <= today)

    if v7 == 0:
        phase = "RECOVERY"
    elif v7 >= max(recent_weeks) and v7 > vprev:
        phase = "APOGEE"
    elif v7 > vprev * 1.15:
        phase = "BOOST"
    elif v7 >= vprev * 0.6:
        phase = "COAST"
    else:
        phase = "DESCENT"

    t0 = datetime(today.year, 1, 1, tzinfo=timezone.utc)
    met = now - t0
    return {
        "ytd": ytd,
        "v7": v7,
        "vprev": vprev,
        "accel": v7 - vprev,
        "phase": phase,
        "met": f"T+{met.days:03d}d {met.seconds // 3600:02d}:{met.seconds % 3600 // 60:02d}",
        "daily60": [get(today - timedelta(days=59 - k)) for k in range(60)],
        "recent_weeks": list(reversed(recent_weeks)),
    }


def met_stamp(iso: str, now: datetime) -> str:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    t0 = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    if t < t0:  # event from last year: fall back to a plain date
        return t.strftime("%Y-%m-%d")
    m = t - t0
    return f"T+{m.days:03d}d {m.seconds // 3600:02d}:{m.seconds % 3600 // 60:02d}"


# ------------------------------------------------------------------ panel render

STYLE = """
<style>
  .t {{ font-family: {font}; }}
  .dim {{ fill: {dim}; }}
  .lbl {{ font-size: 11px; letter-spacing: 1.6px; }}
  .big {{ font-size: 34px; font-weight: 700; }}
  .live {{ animation: blink 1.6s steps(2, start) infinite; }}
  .pulse {{ animation: pulse 2s ease-out infinite; transform-box: fill-box; transform-origin: center; }}
  .draw {{ stroke-dasharray: 2400; stroke-dashoffset: 2400; animation: draw 2.4s ease-out forwards; }}
  .fade {{ opacity: 0; animation: fade .6s ease-out forwards; }}
  .scan {{ animation: scan 6s linear infinite; }}
  @keyframes blink {{ to {{ visibility: hidden; }} }}
  @keyframes pulse {{ 0% {{ transform: scale(1); opacity: .9; }} 100% {{ transform: scale(3.2); opacity: 0; }} }}
  @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  @keyframes scan {{ from {{ transform: translateX(0); }} to {{ transform: translateX(840px); }} }}
  @media (prefers-reduced-motion: reduce) {{
    .live, .pulse, .scan {{ animation: none; }}
    .draw {{ animation: none; stroke-dashoffset: 0; }}
    .fade {{ animation: none; opacity: 1; }}
  }}
</style>
"""

TAG_COLOR = {"PUSH": "cyan", "PR": "warn", "MERGE": "accent", "REVIEW": "dim",
             "REL": "accent", "TAG": "accent", "NEW": "cyan", "ISSUE": "warn", "FORK": "dim"}

PHASE_COLOR = {"BOOST": "warn", "COAST": "cyan", "APOGEE": "accent",
               "DESCENT": "warn", "RECOVERY": "dim"}


def card(x: int, y: int, w: int, h: int, c: dict, label: str, body: str) -> str:
    return (
        f'<g transform="translate({x},{y})">'
        f'<rect width="{w}" height="{h}" rx="6" fill="{c["panel"]}" stroke="{c["border"]}"/>'
        f'<text x="14" y="22" class="t dim lbl">{esc(label)}</text>{body}</g>'
    )


def render_panel(a: dict, events: list[dict], cfg: dict, theme: str, now: datetime) -> str:
    c = THEMES[theme]
    W, H = 880, 468
    out = [svg_open(W, H, f"{cfg['user']} ground station telemetry"),
           STYLE.format(font=FONT, text=c["text"], dim=c["dim"]),
           f'<rect width="{W}" height="{H}" rx="10" fill="{c["bg"]}" stroke="{c["border"]}"/>',
           f'<g fill="{c["text"]}">']

    # header
    out.append(
        f'<text x="20" y="30" class="t" font-size="13" font-weight="700" letter-spacing="2">'
        f'{esc(cfg["station_name"])}</text>'
        f'<circle cx="{W - 250}" cy="25.5" r="4" fill="{c["alert"]}" class="live"/>'
        f'<text x="{W - 240}" y="30" class="t" font-size="11" letter-spacing="1.5" fill="{c["alert"]}">LIVE</text>'
        f'<text x="{W - 20}" y="30" class="t dim" font-size="11" text-anchor="end" letter-spacing="1">'
        f'MET {esc(a["met"])}</text>'
        f'<line x1="20" y1="44" x2="{W - 20}" y2="44" stroke="{c["border"]}"/>'
    )

    cw, ch, cy = 198, 112, 58
    xs = [20 + i * (cw + 16) for i in range(4)]

    # ALTITUDE
    body = (f'<text x="14" y="64" class="t big">{a["ytd"]:,}</text>'
            f'<text x="14" y="88" class="t dim" font-size="11">contributions this year</text>')
    out.append(card(xs[0], cy, cw, ch, c, "ALTITUDE", body))

    # VELOCITY + 8-week bars
    wk = a["recent_weeks"]
    peak = max(wk) or 1
    bars = "".join(
        f'<rect x="{110 + i * 10}" y="{88 - 30 * v / peak:.1f}" width="7" height="{max(1.5, 30 * v / peak):.1f}" '
        f'rx="1" fill="{c["accent"] if i == len(wk) - 1 else c["off"]}"/>'
        for i, v in enumerate(wk))
    body = (f'<text x="14" y="64" class="t big">{a["v7"]}</text>'
            f'<text x="14" y="88" class="t dim" font-size="11">last 7 days</text>{bars}')
    out.append(card(xs[1], cy, cw, ch, c, "VELOCITY", body))

    # ACCELERATION
    d = a["accel"]
    col = c["accent"] if d > 0 else c["alert"] if d < 0 else c["dim"]
    arrow = "▲" if d > 0 else "▼" if d < 0 else "■"
    body = (f'<text x="14" y="64" class="t big" fill="{col}">{arrow} {abs(d)}</text>'
            f'<text x="14" y="88" class="t dim" font-size="11">vs previous week ({a["vprev"]})</text>')
    out.append(card(xs[2], cy, cw, ch, c, "ACCELERATION", body))

    # FLIGHT PHASE + indicator lights
    pcol = c[PHASE_COLOR[a["phase"]]]
    lights = ""
    for i, name in enumerate(PHASES):
        on = name == a["phase"]
        lx = 22 + i * 36
        lights += (f'<circle cx="{lx}" cy="80" r="5" fill="{pcol if on else c["off"]}"/>'
                   f'<text x="{lx}" y="100" class="t dim" font-size="9" text-anchor="middle">{name[0]}</text>')
    body = (f'<text x="14" y="58" class="t" font-size="24" font-weight="700" fill="{pcol}">{a["phase"]}</text>'
            f'{lights}')
    out.append(card(xs[3], cy, cw, ch, c, "FLIGHT PHASE", body))

    # strip chart: 60 days
    sx, sy, sw, sh = 20, 186, W - 40, 112
    vals = a["daily60"]
    vmax = max(max(vals), 4)
    px = lambda i: sx + 14 + i * (sw - 28) / (len(vals) - 1)
    py = lambda v: sy + sh - 14 - (sh - 44) * v / vmax
    pts = [(px(i), py(v)) for i, v in enumerate(vals)]
    line = smooth_path(pts, 0.4, y_floor=sy + sh - 14)
    area = f"{line} L{pts[-1][0]:.1f},{sy + sh - 14} L{pts[0][0]:.1f},{sy + sh - 14} Z"
    grid = "".join(
        f'<line x1="{sx + 14}" x2="{sx + sw - 14}" y1="{py(vmax * f):.1f}" y2="{py(vmax * f):.1f}" '
        f'stroke="{c["grid"]}" stroke-dasharray="2 4"/>' for f in (0.25, 0.5, 0.75, 1.0))
    lx, ly = pts[-1]
    out.append(
        f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="6" fill="{c["panel"]}" stroke="{c["border"]}"/>'
        f'<text x="{sx + 14}" y="{sy + 22}" class="t dim lbl">DAILY CONTRIBUTIONS · LAST 60 DAYS</text>'
        f'<text x="{sx + sw - 14}" y="{sy + 22}" class="t dim" font-size="11" text-anchor="end">peak {max(vals)}/day</text>'
        f'<clipPath id="strip"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="6"/></clipPath>'
        f'{grid}<path d="{area}" fill="{c["accent_soft"]}" class="fade"/>'
        f'<path d="{line}" fill="none" stroke="{c["accent"]}" stroke-width="2" class="draw"/>'
        f'<g clip-path="url(#strip)"><rect x="{sx - 40}" y="{sy}" width="40" height="{sh}" '
        f'fill="{c["accent"]}" opacity="0.05" class="scan"/></g>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{c["accent"]}" class="pulse"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{c["accent"]}"/>'
    )

    # event log
    ey = 312
    out.append(
        f'<rect x="20" y="{ey}" width="{W - 40}" height="{H - ey - 20}" rx="6" fill="{c["panel"]}" stroke="{c["border"]}"/>'
        f'<text x="34" y="{ey + 22}" class="t dim lbl">EVENT LOG</text>'
    )
    if not events:
        out.append(f'<text x="34" y="{ey + 48}" class="t dim" font-size="12">no recent downlinks</text>')
    for i, ev in enumerate(events[:5]):
        y = ey + 46 + i * 18
        col = c[TAG_COLOR.get(ev["tag"], "dim")]
        out.append(
            f'<g class="fade" style="animation-delay:{0.3 + i * 0.15:.2f}s">'
            f'<text x="34" y="{y}" class="t dim" font-size="12">{esc(met_stamp(ev["time"], now))}</text>'
            f'<text x="176" y="{y}" class="t" font-size="12" font-weight="700" fill="{col}">{esc(ev["tag"])}</text>'
            f'<text x="246" y="{y}" class="t" font-size="12">{esc(truncate(ev["text"], 78))}</text></g>'
        )

    out.append("</g></svg>")
    return "".join(out)


# --------------------------------------------------------- flight profile render


def weekly_series(days: dict[date, int], now: datetime) -> list[tuple[date, int]]:
    today = now.date()
    weeks = []
    for k in range(51, -1, -1):
        end = today - timedelta(days=7 * k)
        weeks.append((end, sum(days.get(end - timedelta(days=j), 0) for j in range(7))))
    return weeks


def pick_peaks(vals: list[int], n: int = 3, gap: int = 5) -> list[int]:
    order = sorted(range(len(vals)), key=lambda i: -vals[i])
    chosen: list[int] = []
    for i in order:
        if vals[i] == 0:
            break
        if all(abs(i - j) >= gap for j in chosen):
            chosen.append(i)
        if len(chosen) == n:
            break
    return chosen


def render_profile(days: dict[date, int], cfg: dict, theme: str, now: datetime) -> str:
    c = THEMES[theme]
    W, H = 880, 280
    weeks = weekly_series(days, now)
    vals = [v for _, v in weeks]
    vmax = max(max(vals), 5)
    x0, x1, ytop, ygnd = 56, W - 36, 64, H - 52
    px = lambda i: x0 + i * (x1 - x0) / (len(vals) - 1)
    py = lambda v: ygnd - (ygnd - ytop) * v / vmax
    pts = [(px(i), py(v)) for i, v in enumerate(vals)]
    line = smooth_path(pts, 0.5, y_floor=ygnd)
    area = f"{line} L{pts[-1][0]:.1f},{ygnd} L{pts[0][0]:.1f},{ygnd} Z"

    out = [svg_open(W, H, f"{cfg['user']} flight profile, last 52 weeks"),
           STYLE.format(font=FONT, text=c["text"], dim=c["dim"]),
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{c["accent"]}" stop-opacity="0.35"/>'
           f'<stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/></linearGradient></defs>',
           f'<rect width="{W}" height="{H}" rx="10" fill="{c["bg"]}" stroke="{c["border"]}"/>',
           f'<g fill="{c["text"]}">',
           f'<text x="20" y="30" class="t" font-size="13" font-weight="700" letter-spacing="2">FLIGHT PROFILE</text>',
           f'<text x="{W - 20}" y="30" class="t dim" font-size="11" text-anchor="end" letter-spacing="1">'
           f'CONTRIBUTIONS / WEEK · LAST 52 WEEKS</text>']

    # y grid + labels
    for f in (0.25, 0.5, 0.75, 1.0):
        y = py(vmax * f)
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{c["grid"]}" stroke-dasharray="2 4"/>'
                   f'<text x="{x0 - 10}" y="{y + 4:.1f}" class="t dim" font-size="10" text-anchor="end">{round(vmax * f)}</text>')

    # month ticks
    seen = set()
    for i, (end, _) in enumerate(weeks):
        key = (end.year, end.month)
        if key in seen or i == 0:
            seen.add(key)
            continue
        seen.add(key)
        x = px(i)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{ygnd}" y2="{ygnd + 5}" stroke="{c["dim"]}"/>'
                   f'<text x="{x:.1f}" y="{ygnd + 18}" class="t dim" font-size="10" text-anchor="middle">'
                   f'{end.strftime("%b").upper()}</text>')

    out.append(f'<path d="{area}" fill="url(#g)" class="fade"/>'
               f'<path d="{line}" fill="none" stroke="{c["accent"]}" stroke-width="2.2" class="draw"/>'
               f'<line x1="{x0 - 8}" x2="{x1 + 8}" y1="{ygnd}" y2="{ygnd}" stroke="{c["dim"]}" stroke-width="1.2"/>')

    # pad marker
    out.append(f'<path d="M{x0 - 6},{ygnd} l6,-10 l6,10 z" fill="{c["dim"]}"/>'
               f'<text x="{x0}" y="{ygnd + 32}" class="t dim" font-size="10" text-anchor="middle">PAD</text>')

    # event markers on peaks
    peaks = pick_peaks(vals)
    for rank, i in enumerate(sorted(peaks)):
        x, y = pts[i]
        is_apogee = i == peaks[0]
        label = "APOGEE" if is_apogee else "STAGE SEP"
        col = c["warn"] if is_apogee else c["cyan"]
        ly = max(ytop - 12, y - 16 - (rank % 2) * 14)
        anchor = "end" if x > W - 160 else "start" if x < 160 else "middle"
        out.append(
            f'<g class="fade" style="animation-delay:{1.6 + rank * 0.2:.1f}s">'
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y:.1f}" y2="{ygnd}" stroke="{col}" stroke-dasharray="3 3" opacity=".7"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{c["bg"]}" stroke="{col}" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{ly:.1f}" class="t" font-size="10" font-weight="700" fill="{col}" '
            f'text-anchor="{anchor}" letter-spacing="1">{label} · {vals[i]}</text></g>')

    # current position
    cx, cy = pts[-1]
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c["accent"]}" class="pulse"/>'
               f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c["accent"]}"/>'
               f'<text x="{cx:.1f}" y="{ygnd + 32}" class="t" font-size="10" text-anchor="end" fill="{c["accent"]}">NOW</text>')
    out.append("</g></svg>")
    return "".join(out)


# ------------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="render with synthetic data")
    args = ap.parse_args()

    cfg = load_config()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if args.mock:
        days, events = mock_data(now)
    else:
        if not token():
            raise SystemExit("Set GITHUB_TOKEN (or GH_STATS_TOKEN) to query the GitHub API")
        days = fetch_days(cfg["user"], now)
        events = fetch_events(cfg["user"], cfg.get("event_log_skip_repos", []))

    a = analyse(days, now)
    changed = []
    for theme in THEMES:
        if write_text(ASSETS / f"telemetry-{theme}.svg", render_panel(a, events, cfg, theme, now)):
            changed.append(f"telemetry-{theme}.svg")
        if write_text(ASSETS / f"flight-profile-{theme}.svg", render_profile(days, cfg, theme, now)):
            changed.append(f"flight-profile-{theme}.svg")
    print(f"phase={a['phase']} ytd={a['ytd']} v7={a['v7']} accel={a['accel']:+d}")
    print("updated:", ", ".join(changed) or "nothing")


if __name__ == "__main__":
    main()
