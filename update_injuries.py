
#!/usr/bin/env python3
"""Update NBA injuries and estimated return dates from ESPN."""

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


def first_value(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return ""


def as_dict(value):
    return value if isinstance(value, dict) else {}


def label(value):
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return str(first_value(
            value.get("description"),
            value.get("displayName"),
            value.get("name"),
            value.get("abbreviation"),
            value.get("detail")
        ))

    return ""


def entries(group):
    for key in ("injuries", "items", "athletes"):
        value = group.get(key)

        if isinstance(value, list):
            return value

    return []


def team_code(group):
    team = as_dict(first_value(
        group.get("team"),
        group.get("teamInfo")
    ))

    team_id = str(first_value(
        team.get("id"),
        group.get("teamId"),
        group.get("id")
    ))

    if team_id in IDS:
        return IDS[team_id]

    abbreviation = str(first_value(
        team.get("abbreviation"),
        group.get("abbreviation")
    )).upper()

    return ABBR.get(abbreviation)


def find_return_date(injury):
    details = as_dict(injury.get("details"))

    # Only use explicitly identified return-date fields.
    # Never use the injury report's publication date.
    keys = (
        "returnDate",
        "expectedReturnDate",
        "estimatedReturnDate",
        "returnsAt",
        "expectedReturn",
        "estimatedReturn"
    )

    for container in (injury, details):
        for key in keys:
            value = container.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

            if isinstance(value, dict):
                date = first_value(
                    value.get("date"),
                    value.get("value"),
                    value.get("displayValue")
                )

                if date:
                    return str(date)

    return ""


def parse_player(injury):
    athlete = as_dict(first_value(
        injury.get("athlete"),
        injury.get("player")
    ))

    details = as_dict(injury.get("details"))

    name = first_value(
        athlete.get("displayName"),
        athlete.get("fullName"),
        injury.get("displayName"),
        injury.get("name")
    )

    if not name:
        return None

    position = first_value(
        athlete.get("position"),
        injury.get("position")
    )

    status = first_value(
        injury.get("status"),
        injury.get("type")
    )

    reason = first_value(
        details.get("type"),
        details.get("detail"),
        injury.get("description"),
        injury.get("shortComment"),
        injury.get("longComment")
    )

    return {
        "name": str(name),
        "pos": label(position),
        "st": label(status),
        "detail": label(reason),
        "returnDate": find_return_date(injury)
    }


def main():
    print("Fetching ESPN NBA injury report...", flush=True)

    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=25
    ) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise RuntimeError("ESPN response is not a JSON object")

    groups = payload.get("injuries")

    if not isinstance(groups, list) or not groups:
        raise RuntimeError(
            "ESPN injury list is unavailable; old file preserved"
        )

    teams = {code: [] for code in IDS.values()}

    unmatched = []
    total_entries = 0
    return_dates_found = 0

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

            total_entries += 1
            player = parse_player(injury)

            if player:
                teams[code].append(player)

                if player["returnDate"]:
                    return_dates_found += 1

    total = sum(len(players) for players in teams.values())

    print("ESPN team groups:", len(groups), flush=True)
    print("Injury entries:", total_entries, flush=True)
    print("Players parsed:", total, flush=True)
    print("Return dates found:", return_dates_found, flush=True)
    print("Unmatched groups:", unmatched, flush=True)

    if total == 0:
        raise RuntimeError(
            "No players parsed; existing file preserved"
        )

    # Diagnostic: show field names, without dumping player details.
    sample = None

    for group in groups:
        if not isinstance(group, dict):
            continue

        items = entries(group)

        if items and isinstance(items[0], dict):
            sample = items[0]
            break

    if sample:
        print(
            "Sample injury fields:",
            list(sample.keys()),
            flush=True
        )

        details = as_dict(sample.get("details"))

        print(
            "Sample details fields:",
            list(details.keys()),
            flush=True
        )

        print(
            "Sample returnDate:",
            find_return_date(sample) or "Not provided",
            flush=True
        )

    output = {
        "updated_at": dt.datetime.now(
            dt.timezone.utc
        ).isoformat(),
        "source": URL,
        "teams": teams
    }

    Path("injuries.json").write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    print("NBA injury data updated successfully!", flush=True)


if __name__ == "__main__":
    main()
