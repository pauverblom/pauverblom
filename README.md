<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/telemetry-dark.svg">
  <img src="assets/telemetry-light.svg" width="100%" alt="Ground-station telemetry: contributions this year, last 7 days, week-over-week change and current flight phase, with a 60-day strip chart and recent GitHub events">
</picture>

### Hi, I'm Pau 👋

Space Engineering student at UPV in Valencia, writing ground-station and flight software for **Faraday Rocketry**: telemetry simulation, the flight monitoring dashboard, and the shared libraries behind them. Mostly Python, Svelte and C, with the occasional Minecraft mod on the side.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/flight-profile-dark.svg">
  <img src="assets/flight-profile-light.svg" width="100%" alt="Flight profile: weekly contributions over the last 52 weeks, with apogee and stage separations marking the busiest weeks">
</picture>

<details>
<summary><b>How to read the telemetry</b></summary>
<br>

| Readout | Meaning |
| --- | --- |
| **Altitude** | Contributions since 1 January (T‑0) |
| **Velocity** | Contributions in the last 7 days |
| **Acceleration** | Change versus the previous 7 days |
| **Flight phase** | `BOOST` speeding up · `COAST` steady · `APOGEE` best week in two months · `DESCENT` slowing down · `RECOVERY` under parachutes |
| **MET** | Mission elapsed time since T‑0 |

Everything is regenerated daily by a GitHub Action from the GitHub API. No external services involved.
</details>

## Mission patches

<!-- PATCHES:START -->
<table align="center">
<tr><td align="center" width="33%"><a href="https://github.com/faraday-rocketry"><img src="assets/patches/frfmd.svg" width="132" alt="FRFMD mission patch"/></a><br/><sub>Faraday Rocketry flight monitoring dashboard: 50 Hz WebSocket telemetry, Svelte + ECharts frontend.</sub></td><td align="center" width="33%"><a href="https://github.com/faraday-rocketry"><img src="assets/patches/telemetry-generator.svg" width="132" alt="TELEMETRY GEN mission patch"/></a><br/><sub>Python/Tkinter generator that simulates and streams serial telemetry for ground-station testing.</sub></td><td align="center" width="33%"><a href="https://github.com/faraday-rocketry/frlib"><img src="assets/patches/frlib.svg" width="132" alt="FRLIB mission patch"/></a><br/><sub>Faraday Rocketry's shared code library.</sub></td></tr>
<tr><td align="center" width="33%"><a href="https://github.com/Pauverblom/flight-affinity"><img src="assets/patches/flight-affinity.svg" width="132" alt="FLIGHT AFFINITY mission patch"/></a><br/><sub>Personal project.</sub></td><td align="center" width="33%"><a href="https://github.com/FabricMC/fabric-api/pull/5488"><img src="assets/patches/fabric-api.svg" width="132" alt="FABRIC API mission patch"/></a><br/><sub>Contribution to FabricMC: saving a world's active mod list.</sub></td><td align="center" width="33%"><a href="https://github.com/Pauverblom/claude-skills"><img src="assets/patches/claude-skills.svg" width="132" alt="CLAUDE SKILLS mission patch"/></a><br/><sub>Skills I've adapted for Claude.</sub></td></tr>
</table>
<!-- PATCHES:END -->

## Launch pad

Every visitor gets a launch. Pick a motor, open the pre-filled issue, and a GitHub Action flies your rocket through a 1D simulation (thrust curve, variable mass, drag with altitude-dependent air density) and replies with the flight data.

<p align="center">
  <a href="https://github.com/Pauverblom/Pauverblom/issues/new?title=launch&body=Pick%20a%20motor%20class%20by%20editing%20the%20last%20line%20%28G%2C%20H%2C%20I%2C%20J%20or%20K%29%2C%20then%20press%20%2A%2ACreate%2A%2A.%0AFlight%20results%20show%20up%20as%20a%20comment%20in%20about%20a%20minute.%0A%0Amotor%3A%20I"><b>🚀 Launch a rocket</b></a>
</p>

<!-- LEADERBOARD:START -->
<p align="center"><sub>The pad is clear. No launches yet, so the first one takes the top spot.</sub></p>
<!-- LEADERBOARD:END -->
