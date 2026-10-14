"""Launch pad: fly a visitor's rocket from a GitHub issue.

Reads the issue from $GITHUB_EVENT_PATH, runs a 1D flight simulation, writes the
flight report (markdown) to --comment-out, appends to data/launches.json and
refreshes the README leaderboard.

Local test:
  python scripts/launch.py --event fake_event.json --comment-out /tmp/report.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
from datetime import datetime, timedelta, timezone

from common import DATA, README, replace_section, write_text

G0 = 9.80665
RAIL_LENGTH = 1.5        # m
MAIN_DEPLOY_ALT = 150.0  # m
COOLDOWN = timedelta(minutes=10)

# class: total impulse [N·s], burn time [s], propellant [kg], dry mass [kg], body diameter [m]
MOTORS = {
    "G": (120, 1.5, 0.065, 0.85, 0.054),
    "H": (240, 1.8, 0.130, 1.30, 0.054),
    "I": (480, 2.2, 0.260, 2.10, 0.075),
    "J": (960, 2.8, 0.520, 3.30, 0.075),
    "K": (1920, 3.2, 1.000, 5.40, 0.098),
}
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?$")


# ---------------------------------------------------------------- atmosphere


def atmosphere(h: float, dT: float) -> tuple[float, float]:
    """ISA troposphere with a temperature offset: (density kg/m³, speed of sound m/s)."""
    h = max(0.0, min(h, 11000.0))
    T = 288.15 + dT - 0.0065 * h
    p = 101325.0 * (1 - 2.25577e-5 * h) ** 5.25588
    return p / (287.05 * T), math.sqrt(1.4 * 287.05 * T)


def drag_coeff(cd0: float, mach: float) -> float:
    """Subsonic Cd with a smooth transonic drag rise peaking near Mach 1."""
    return cd0 * (1 + 0.9 * math.exp(-((mach - 1.02) / 0.16) ** 2) + 0.35 * max(0.0, min(mach - 1.0, 1.0)))


# -------------------------------------------------------------------- motor


def thrust_profile(impulse: float, burn: float):
    """Regressive-progressive grain: spike at ignition, plateau, tail-off. Normalised to impulse."""
    def shape(t: float) -> float:
        x = t / burn
        if x < 0 or x > 1:
            return 0.0
        if x < 0.08:
            return 1.45 * x / 0.08
        if x < 0.22:
            return 1.45 - (1.45 - 1.0) * (x - 0.08) / 0.14
        if x < 0.85:
            return 1.0 - 0.1 * (x - 0.22) / 0.63
        return 0.9 * (1 - (x - 0.85) / 0.15)
    n = 2000
    area = sum(shape((i + 0.5) * burn / n) for i in range(n)) * burn / n
    k = impulse / area
    return lambda t: k * shape(t)


# --------------------------------------------------------------- simulation


def fly(motor: str, seed: str) -> dict:
    rng = random.Random(seed)
    impulse, burn, prop, dry, diam = MOTORS[motor]
    impulse *= rng.uniform(0.93, 1.07)
    burn *= rng.uniform(0.95, 1.05)
    dry *= rng.uniform(0.9, 1.1)
    cd0 = rng.uniform(0.40, 0.60)
    dT = rng.uniform(-12, 15)            # launch-day temperature offset from ISA
    area = math.pi * diam ** 2 / 4
    thrust = thrust_profile(impulse, burn)

    roll = rng.random()
    anomaly = "cato" if roll < 0.03 else "chute" if roll < 0.06 else None
    cato_t = rng.uniform(0.15, 0.8) * burn if anomaly == "cato" else None

    t, h, v, dt = 0.0, 0.0, 0.0, 0.002
    m0 = dry + prop
    rail_exit = None
    max_v = max_mach = max_acc = max_q = 0.0
    burnout_h = None
    samples = [(0.0, 0.0)]
    next_sample = 0.25

    while True:
        burning = t < burn and (cato_t is None or t < cato_t)
        F = thrust(t) if burning else 0.0
        m = m0 - prop * min(t, burn) / burn
        rho, a = atmosphere(h, dT)
        mach = abs(v) / a
        D = 0.5 * rho * v * abs(v) * drag_coeff(cd0, mach) * area
        acc = (F - D) / m - G0
        if h <= 0 and acc < 0 and t < 0.5:   # sitting on the pad until thrust > weight
            acc = 0.0
        v += acc * dt
        h += v * dt
        t += dt

        if rail_exit is None and h >= RAIL_LENGTH:
            rail_exit = v
        if burnout_h is None and not burning and t > 0.05:
            burnout_h = h
        max_v, max_mach = max(max_v, v), max(max_mach, mach)
        max_acc = max(max_acc, acc + G0)
        max_q = max(max_q, 0.5 * rho * v * v)
        if t >= next_sample:
            samples.append((t, h))
            next_sample += 0.25
        if v <= 0 and t > 0.3:
            break
        if t > 120:
            break

    apogee, t_apogee = max(h, 0.0), t

    if anomaly == "cato":
        # rocket comes apart: debris falls ballistically, no recovery
        v_drogue = v_main = None
        t_land = t_apogee + math.sqrt(2 * apogee / G0) * 1.6 if apogee > 0 else t_apogee
    else:
        v_drogue = rng.uniform(18, 26)
        v_main = rng.uniform(42, 55) if anomaly == "chute" else rng.uniform(4.8, 6.4)
        upper = max(0.0, apogee - MAIN_DEPLOY_ALT)
        lower = min(apogee, MAIN_DEPLOY_ALT)
        t_land = t_apogee + upper / v_drogue + lower / v_main

    # descent samples for the plot
    step = max(0.5, (t_land - t_apogee) / 14)
    tt = t_apogee + step
    while tt < t_land:
        if anomaly == "cato":
            frac = (tt - t_apogee) / (t_land - t_apogee)
            samples.append((tt, apogee * (1 - frac ** 2)))
        else:
            dt_up = max(0.0, apogee - MAIN_DEPLOY_ALT) / v_drogue
            el = tt - t_apogee
            alt = apogee - v_drogue * el if el <= dt_up else min(apogee, MAIN_DEPLOY_ALT) - v_main * (el - dt_up)
            samples.append((tt, max(0.0, alt)))
        tt += step
    samples.append((t_land, 0.0))

    return {
        "motor": motor,
        "apogee": apogee,
        "t_apogee": t_apogee,
        "t_land": t_land,
        "burnout_h": burnout_h or 0.0,
        "max_v": max_v,
        "max_mach": max_mach,
        "max_g": max_acc / G0,
        "max_q": max_q / 1000,
        "rail_exit": rail_exit or 0.0,
        "liftoff_mass": m0,
        "cd0": cd0,
        "temp_c": 15 + dT,
        "anomaly": anomaly,
        "v_drogue": v_drogue,
        "v_main": v_main,
        "samples": samples,
    }


# ------------------------------------------------------------------- report


def mermaid(samples: list[tuple[float, float]], n: int = 25) -> str:
    """Altitude-vs-time line chart, resampled on a uniform time grid."""
    t_end = samples[-1][0]
    grid = [t_end * i / (n - 1) for i in range(n)]
    ys, j = [], 0
    for t in grid:
        while j < len(samples) - 2 and samples[j + 1][0] < t:
            j += 1
        (ta, ha), (tb, hb) = samples[j], samples[j + 1]
        f = 0.0 if tb == ta else min(1.0, max(0.0, (t - ta) / (tb - ta)))
        ys.append(ha + f * (hb - ha))
    top = max(h for _, h in samples)
    ymax = max(50, math.ceil(top * 1.1 / 50) * 50)
    xs = ", ".join(f'"{t:.0f}"' for t in grid)
    line = ", ".join(f"{h:.0f}" for h in ys)
    return (
        "```mermaid\n"
        "xychart-beta\n"
        f'    title "Altitude · apogee {top:,.0f} m"\n'
        f'    x-axis "time (s)" [{xs}]\n'
        f'    y-axis "altitude (m)" 0 --> {ymax}\n'
        f"    line [{line}]\n"
        "```"
    )


def plural(n: int, word: str, suffix: str = "s") -> str:
    return f"{n:,} {word}{'' if n == 1 else suffix}"


def report(login: str, issue: int, r: dict, rank: int | None, total: int,
           best: tuple[int, int] | None = None) -> str:
    outcome = {
        None: "✅ **Nominal flight.** Drogue at apogee, main at 150 m, safe landing.",
        "chute": "⚠️ **Main chute failed to inflate.** The rocket came in hot under the drogue. Apogee still counts.",
        "cato": "💥 **CATO.** The motor failed mid-burn and the rocket came apart. Apogee still counts, barely.",
    }[r["anomaly"]]
    rows = [
        ("Apogee", f"**{r['apogee']:,.0f} m**"),
        ("Time to apogee", f"{r['t_apogee']:.1f} s"),
        ("Max speed", f"{r['max_v']:.0f} m/s (Mach {r['max_mach']:.2f})"),
        ("Max acceleration", f"{r['max_g']:.1f} g"),
        ("Max dynamic pressure", f"{r['max_q']:.1f} kPa"),
        ("Rail exit speed", f"{r['rail_exit']:.1f} m/s" + (" ⚠️ low" if r["rail_exit"] < 15 else "")),
        ("Burnout altitude", f"{r['burnout_h']:,.0f} m"),
        ("Flight time", f"{r['t_land']:.0f} s"),
    ]
    if r["v_drogue"]:
        rows.append(("Descent rate", f"{r['v_drogue']:.0f} m/s drogue · {r['v_main']:.1f} m/s main"))
    table = "| Readout | Value |\n| --- | --- |\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    if rank:
        standing = f"🏆 That's **#{rank}** on the leaderboard ({plural(total, 'launch', 'es')} so far)."
    elif best:
        standing = (f"Your best flight, #{best[0]}, still holds **#{best[1]}** on the leaderboard. "
                    f"Try a bigger motor?")
    else:
        standing = f"Not on the top-10 board this time ({plural(total, 'launch', 'es')} so far). Try a bigger motor?"
    return f"""### 🚀 Flight report: @{login} · {r['motor']} motor

{outcome}

{table}

{mermaid(r['samples'])}

{standing}

<sub>Lift-off mass {r['liftoff_mass']:.2f} kg · Cd {r['cd0']:.2f} · {r['temp_c']:.0f} °C at the pad · launch #{issue}. Simulated with a 1D point-mass model: ISA atmosphere, transonic drag rise, variable mass, two-stage recovery.</sub>
"""


# -------------------------------------------------------------- leaderboard


def leaderboard(launches: list[dict], repo: str) -> tuple[str, dict[int, int]]:
    best: dict[str, dict] = {}
    for l in launches:
        if l["login"] not in best or l["apogee"] > best[l["login"]]["apogee"]:
            best[l["login"]] = l
    top = sorted(best.values(), key=lambda l: -l["apogee"])[:10]
    ranks = {l["issue"]: i + 1 for i, l in enumerate(top)}
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows = [
        f"| {medals.get(i + 1, i + 1)} | [@{l['login']}](https://github.com/{l['login']}) | {l['motor']} "
        f"| **{l['apogee']:,.0f} m** | Mach {l['max_mach']:.2f} "
        f"| [#{l['issue']}](https://github.com/{repo}/issues/{l['issue']}) |"
        for i, l in enumerate(top)
    ]
    pilots = len(best)
    last = launches[-1]
    body = (
        "| | Pilot | Motor | Apogee | Max speed | Flight |\n| :-: | --- | :-: | --: | --: | :-: |\n"
        + "\n".join(rows)
        + f"\n\n<sub>{plural(len(launches), 'launch', 'es')} by {plural(pilots, 'pilot')}"
        f" · latest: @{last['login']} reached {last['apogee']:,.0f} m on a {last['motor']} motor</sub>"
    )
    return body, ranks


# --------------------------------------------------------------------- main


def parse_motor(title: str, body: str) -> str:
    m = re.search(r"motor\s*[:=]\s*([G-Kg-k])\b", body or "") or re.search(r"\blaunch\s+([G-Kg-k])\b", title or "")
    return m.group(1).upper() if m else "I"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    ap.add_argument("--comment-out", required=True)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Pauverblom/Pauverblom"))
    args = ap.parse_args()

    with open(args.event, encoding="utf-8") as f:
        issue = json.load(f)["issue"]
    login, number = issue["user"]["login"], int(issue["number"])
    if not LOGIN_RE.match(login):
        raise SystemExit(f"unexpected login format: {login!r}")

    db_path = DATA / "launches.json"
    launches = json.loads(db_path.read_text()) if db_path.exists() else []
    now = datetime.now(timezone.utc).replace(microsecond=0)

    last_mine = [l for l in launches if l["login"] == login]
    if last_mine:
        since = now - datetime.fromisoformat(last_mine[-1]["time"])
        if since < COOLDOWN:
            wait = math.ceil((COOLDOWN - since).total_seconds() / 60)
            write_text_out(args.comment_out,
                           f"### ⏳ Launch scrubbed\n\n@{login}, the pad is still cooling down from your last flight. "
                           f"Try again in about {wait} min.")
            print("scrubbed: cooldown")
            return

    motor = parse_motor(issue.get("title", ""), issue.get("body") or "")
    seed = hashlib.sha256(f"{login}:{number}".encode()).hexdigest()
    r = fly(motor, seed)

    launches.append({
        "issue": number, "login": login, "motor": motor, "time": now.isoformat(),
        "apogee": round(r["apogee"], 1), "max_mach": round(r["max_mach"], 3),
        "anomaly": r["anomaly"],
    })
    write_text(db_path, json.dumps(launches, indent=1) + "\n")

    body, ranks = leaderboard(launches, args.repo)
    write_text(README, replace_section(README.read_text(encoding="utf-8"), "LEADERBOARD", body))
    best = next(((num, rk) for num, rk in ranks.items()
                 if any(l["issue"] == num and l["login"] == login for l in launches)), None)
    write_text_out(args.comment_out, report(login, number, r, ranks.get(number), len(launches), best))
    print(f"@{login} {motor}: apogee {r['apogee']:.0f} m, Mach {r['max_mach']:.2f}, anomaly={r['anomaly']}")


def write_text_out(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
