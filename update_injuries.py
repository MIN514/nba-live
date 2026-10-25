
#!/usr/bin/env python3
"""Fetch ESPN NBA injury reports and save a validated JSON snapshot."""

import datetime as dt
import json
import urllib.request
from pathlib import Path

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

IDS = {
    "1": "ATL", "2": "BOS", "17": "BKN", "30": "CHA",
    "4": "CHI", "5": "CLE", "6": "DAL", "7": "DEN",
    "8": "DET", "9": "GSW", "10": "HOU", "11": "IND",
    "12": "LAC", "13": "LAL", "29": "MEM", "14": "MIA",
    "15": "MIL", "16": "MIN", "3": "NOP", "18": "NYK",
    "25": "OKC", "19": "ORL", "20": "PHI", "21": "PHX",
    "22": "POR", "23": "SAC", "24": "SAS", "28": "TOR",
    "26": "UTA", "27": "WAS"
}

ABBR = {code: code for code in IDS.values()}
ABBR.update({
    "GS": "GSW",
    "NY": "NYK",
    "SA": "SAS",
    "NO": "NOP",
    "UTAH": "UTA"
})


def label(value):
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return str(
            value.get("description")
            or value.get("displayName")
            or value.get("name")
            or value.get("abbreviation")
            or value.get("detail")
            or ""
        )

    return ""


def entries(group):
    if isinstance(group, list):
        return group

    if isinstance(group, dict):
        for key in ("injuries", "items", "athletes"):
            value = group.get(key)
            if isinstance(value, list):
                return value

    return []


def team_code(group):
    """Identify the NBA team using ESPN's injury group ID."""

    team = group.get("team") or group.get("teamInfo") or {}

    if not isinstance(team, dict):
        team = {}

    # Important fix: ESPN injury groups use a top-level id.
    team_id = str(
        team.get("id")
        or group.get("teamId")
        or group.get("id")
        or ""
    )

    if team_id in IDS:
        return IDS[team_id]

    abbreviation = str(
        team.get("abbreviation")
        or group.get("abbreviation")
        or ""
    ).upper()

    return ABBR.get(abbreviation)


def parse_player(injury):
    athlete = injury.get("athlete") or injury.get("player") or {}

    if not isinstance(athlete, dict):
        athlete = {}

    name = (
        athlete.get("displayName")
        or athlete.get("fullName")
        or injury.get("displayName")
        or injury.get("name")
    )

    if not name:
        return None

    position = athlete.get("position") or injury.get("position") or {}

    status = injury.get("status") or injury.get("type") or ""

    if isinstance(status, dict):
        status = (
            status.get("description")
            or status.get("name")
            or status.get("type")
            or ""
        )

    details = injury.get("details") or {}

    if not isinstance(details, dict):
        details = {"detail": str(details)}

    detail = (
        details.get("detail")
        or details.get("type")
        or injury.get("description")
        or injury.get("shortComment")
        or injury.get("longComment")
        or ""
    )

    return_date = (
        injury.get("returnDate")
        or injury.get("returnsAt")
        or injury.get("estimatedReturnDate")
        or ""
    )

    return {
        "name": str(name),
        "pos": label(position),
        "st": label(status),
        "detail": label(detail),
        "returnDate": str(return_date)
    }


def main():
    print("Fetching ESPN NBA injuries...", flush=True)

    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise RuntimeError("ESPN did not return a JSON object")

    groups = payload.get("injuries")

    if not isinstance(groups, list):
        raise RuntimeError("ESPN injury data format is invalid")

    if not groups:
        raise RuntimeError(
            "ESPN returned an empty injury list; old data preserved"
        )

    print("Injury groups:", len(groups), flush=True)

    teams = {code: [] for code in IDS.values()}

    unmatched = []

    for group in groups:
        if not isinstance(group, dict):
            continue

        code = team_code(group)

        if not code:
            unmatched.append({
                "id": group.get("id"),
                "name": group.get("displayName")
            })
            continue

        for injury in entries(group):
            if not isinstance(injury, dict):
                continue

            player = parse_player(injury)

            if player:
                teams[code].append(player)

    total = sum(len(players) for players in teams.values())

    print("Players parsed:", total, flush=True)
    print("Unmatched teams:", unmatched, flush=True)

    if total == 0:
        raise RuntimeError(
            "No injury players parsed; existing JSON preserved"
        )

    output = {
        "updated_at": dt.datetime.now(
            dt.timezone.utc
        ).isoformat(),
        "source": URL,
        "teams": teams
    }

    Path("injuries.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print("Injuries synced successfully:", total, flush=True)


if __name__ == "__main__":
    main()
