#!/usr/bin/env python3
"""
flight_watch.py — alert when a military aircraft is near your location.

Cloud version: runs on GitHub Actions on a schedule, so it works whether
or not any of your own devices are on. Sends a push notification via
ntfy.sh.

Data source: adsb.fi open data API (free, no key needed)
  https://github.com/adsbfi/opendata

This script does ONE check per run and exits. flight_watch_state.json
(used to avoid re-alerting on the same aircraft within COOLDOWN_SECONDS)
is committed back to the repo by the GitHub Actions workflow after each
run, since GitHub Actions runners don't keep disk state between runs.

This repo is PUBLIC (so GitHub Actions minutes are free/unlimited, which
5-minute polling needs). Because of that, your home coordinates and ntfy
topic are NOT hardcoded here — they're read from GitHub Actions secrets
(Settings -> Secrets and variables -> Actions) so they never appear in
this public code or in commit history. See SETUP.md for the exact names.
"""

import json
import os
import time
import urllib.request
import urllib.error

# ---- Configuration you may want to tweak -----------------------------

# Read from GitHub Actions secrets (set via the workflow's `env:` block),
# never hardcoded here since this repo is public.
LAT = float(os.environ["FLIGHTWATCH_LAT"])
LON = float(os.environ["FLIGHTWATCH_LON"])
NTFY_TOPIC = os.environ["FLIGHTWATCH_NTFY_TOPIC"]

RADIUS_NM = 13.5          # ~25 km (1 NM = 1.852 km) — not sensitive, kept in code

NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# Don't re-alert on the same aircraft (by hex code) more than once per
# this many seconds, so one plane circling nearby doesn't spam you.
COOLDOWN_SECONDS = 30 * 60

# -----------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "flight_watch_state.json")

API_URL = f"https://opendata.adsb.fi/api/v3/lat/{LAT}/lon/{LON}/dist/{RADIUS_NM}"


def log(msg):
    # GitHub Actions captures stdout in the run's log automatically, so
    # printing is all we need — no local log file (it wouldn't survive
    # between runs anyway, since each run starts from a fresh checkout).
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except OSError as e:
        log(f"WARNING: could not save state: {e}")


def fetch_aircraft():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "flight-watch-script/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("ac", [])


def is_military(ac):
    # dbFlags is a bitfield from the adsb.fi/adsb.lol/ADSBExchange aircraft
    # database; bit 0 (value 1) marks an aircraft as military.
    # Note: this depends on that database being complete/accurate — it can
    # miss some military aircraft and, rarely, misflag one.
    flags = ac.get("dbFlags", 0) or 0
    return bool(flags & 1)


# Every aircraft's Mode S "hex" address (a 24-bit ICAO identifier) is
# assigned to a country out of fixed address blocks, per ICAO Annex 10.
# This is the same trick flight-tracking sites use to show a country flag
# next to an aircraft. Coverage here focuses on Western/Central Europe
# (where almost everything you'll see near Bilthoven falls) plus the
# other NATO members and major air forces — it is NOT the complete list
# of ~200 ICAO-assigned countries. An aircraft outside these ranges shows
# up as "unknown registration country" rather than the wrong country.
# (start_hex, end_hex, country name, ISO country code)
ICAO_COUNTRY_RANGES = [
    (0x300000, 0x33FFFF, "Italy", "it"),
    (0x340000, 0x37FFFF, "Spain", "es"),
    (0x380000, 0x3BFFFF, "France", "fr"),
    (0x3C0000, 0x3FFFFF, "Germany", "de"),
    (0x400000, 0x43FFFF, "United Kingdom", "gb"),
    (0x440000, 0x447FFF, "Austria", "at"),
    (0x448000, 0x44FFFF, "Belgium", "be"),
    (0x450000, 0x457FFF, "Bulgaria", "bg"),
    (0x458000, 0x45FFFF, "Denmark", "dk"),
    (0x460000, 0x467FFF, "Finland", "fi"),
    (0x468000, 0x46FFFF, "Greece", "gr"),
    (0x470000, 0x477FFF, "Hungary", "hu"),
    (0x478000, 0x47FFFF, "Norway", "no"),
    (0x480000, 0x487FFF, "Netherlands", "nl"),
    (0x488000, 0x48FFFF, "Poland", "pl"),
    (0x490000, 0x497FFF, "Portugal", "pt"),
    (0x498000, 0x49FFFF, "Czechia", "cz"),
    (0x4A0000, 0x4A7FFF, "Romania", "ro"),
    (0x4A8000, 0x4AFFFF, "Sweden", "se"),
    (0x4B0000, 0x4B7FFF, "Switzerland", "ch"),
    (0x4B8000, 0x4BFFFF, "Turkey", "tr"),
    (0x4C0000, 0x4C7FFF, "Serbia", "rs"),
    (0x4C8000, 0x4C87FF, "Cyprus", "cy"),
    (0x4CA000, 0x4CAFFF, "Ireland", "ie"),
    (0x4CC000, 0x4CCFFF, "Iceland", "is"),
    (0x4D0000, 0x4D07FF, "Luxembourg", "lu"),
    (0x4D2000, 0x4D27FF, "Malta", "mt"),
    (0x501000, 0x5017FF, "Croatia", "hr"),
    (0x502800, 0x502FFF, "Latvia", "lv"),
    (0x503800, 0x503FFF, "Lithuania", "lt"),
    (0x505800, 0x505FFF, "Slovakia", "sk"),
    (0x506800, 0x506FFF, "Slovenia", "si"),
    (0x508000, 0x50FFFF, "Ukraine", "ua"),
    (0x510000, 0x5107FF, "Belarus", "by"),
    (0x511000, 0x5117FF, "Estonia", "ee"),
    (0x512000, 0x5127FF, "North Macedonia", "mk"),
    (0x514000, 0x5147FF, "Georgia", "ge"),
    (0x516000, 0x5167FF, "Montenegro", "me"),
    (0x700000, 0x700FFF, "Afghanistan", "af"),
    (0x710000, 0x717FFF, "Saudi Arabia", "sa"),
    (0x718000, 0x71FFFF, "South Korea", "kr"),
    (0x738000, 0x73FFFF, "Israel", "il"),
    (0x740000, 0x747FFF, "Jordan", "jo"),
    (0x780000, 0x7BFFFF, "China", "cn"),
    (0x7C0000, 0x7FFFFF, "Australia", "au"),
    (0x800000, 0x83FFFF, "India", "in"),
    (0x840000, 0x87FFFF, "Japan", "jp"),
    (0x896000, 0x896FFF, "United Arab Emirates", "ae"),
    (0xA00000, 0xAFFFFF, "United States", "us"),
    (0xC00000, 0xC3FFFF, "Canada", "ca"),
    (0xC80000, 0xC87FFF, "New Zealand", "nz"),
    (0x100000, 0x1FFFFF, "Russia", "ru"),
    (0xE40000, 0xE7FFFF, "Brazil", "br"),
]


def flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return ""
    try:
        return "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in country_code)
    except (TypeError, ValueError):
        return ""


def country_for_hex(hexcode):
    try:
        value = int(hexcode, 16)
    except (TypeError, ValueError):
        return None
    for start, end, name, code in ICAO_COUNTRY_RANGES:
        if start <= value <= end:
            return name, code
    return None


def describe(ac):
    hexcode = ac.get("hex", "?")
    flight = (ac.get("flight") or "").strip() or "no callsign"
    reg = ac.get("r") or "unknown reg"
    actype = ac.get("t") or "unknown type"
    alt = ac.get("alt_baro")
    alt_str = f"{alt} ft" if isinstance(alt, (int, float)) else str(alt or "unknown alt")

    country = country_for_hex(hexcode)
    if country:
        name, code = country
        country_str = f"{flag_emoji(code)} {name}".strip()
    else:
        country_str = "registration country unknown"

    return f"{flight} ({reg}, {actype}) — {country_str} — {alt_str} — hex {hexcode}"


def notify_ntfy(title, message):
    if not NTFY_TOPIC or "REPLACE" in NTFY_TOPIC:
        log("WARNING: ntfy topic not configured, skipping push notification")
        return
    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tags": "airplane"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.URLError as e:
        log(f"WARNING: ntfy push failed: {e}")


def main():
    try:
        aircraft = fetch_aircraft()
    except Exception as e:
        log(f"ERROR fetching aircraft data: {e}")
        return

    state = load_state()
    now = time.time()
    changed = False
    military_count = 0

    for ac in aircraft:
        if not is_military(ac):
            continue
        military_count += 1
        hexcode = ac.get("hex")
        if not hexcode:
            continue
        last_alert = state.get(hexcode, 0)
        if now - last_alert < COOLDOWN_SECONDS:
            continue

        desc = describe(ac)
        title = "Military aircraft nearby"
        log(f"ALERT: {desc}")
        notify_ntfy(title, desc)
        state[hexcode] = now
        changed = True

    # Heartbeat: always log a line so the Actions run log shows the check
    # actually happened, even when nothing is currently in range.
    log(f"checked: {len(aircraft)} aircraft in range, {military_count} military")

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
