#!/usr/bin/env python3
"""Match publicly visible NBA community votes to ESPN scheduled games.

Only export a prediction when its away/home teams uniquely match an NBA game
within the short schedule window. Never treat an ignored source query date as
an actual game date. No fabricated vote percentages.
"""
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'community_predictions.json'
SOURCE = 'https://www.playsport.cc/predict/scale'
SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
TZ = ZoneInfo('Asia/Taipei')
TEAMS = {
 '老鷹':'ATL','塞爾提':'BOS','塞爾提克':'BOS','籃網':'BKN','黃蜂':'CHA','公牛':'CHI',
 '騎士':'CLE','獨行俠':'DAL','小牛':'DAL','金塊':'DEN','活塞':'DET','勇士':'GSW',
 '火箭':'HOU','溜馬':'IND','快艇':'LAC','湖人':'LAL','灰熊':'MEM','熱火':'MIA',
 '公鹿':'MIL','灰狼':'MIN','鵜鶘':'NOP','尼克':'NYK','雷霆':'OKC','魔術':'ORL',
 '76人':'PHI','七六人':'PHI','太陽':'PHX','拓荒者':'POR','國王':'SAC',
 '馬刺':'SAS','暴龍':'TOR','爵士':'UTA','巫師':'WAS'
}
PCT = re.compile(r'(?<!\d)(100|\d{1,2})\s*%\s*(\d[\d,]*)\s*人預測')


def row_team(row):
    for tag in row.select('h3,h4,a'):
        name = re.sub(r'\s+', '', tag.get_text(' ', strip=True))
        if name in TEAMS:
            return TEAMS[name]
    return None


def cells_with_votes(row):
    result = []
    for cell in row.find_all('td', recursive=False):
        txt = cell.get_text(' ', strip=True)
        matches = PCT.findall(txt)
        if len(matches) > 1:
            return None
        if matches:
            result.append((int(matches[0][0]), int(matches[0][1].replace(',', '')), txt))
    return result if len(result) == 5 else None


def market_pair(a, b, *, total=False):
    if not 99 <= a[0] + b[0] <= 101:
        return None
    left, right = ('over', 'under') if total else ('away', 'home')
    value = {left: a[0], right: b[0], 'counts': {left: a[1], right: b[1]}}
    if total:
        match = re.search(r'大\s*(\d+(?:\.\d+)?)', a[2])
        if match:
            value['line'] = float(match.group(1))
    return value


def parse_source(html):
    soup = BeautifulSoup(html, 'html.parser')
    games = {}
    for table in soup.select('table'):
        parsed = [(row_team(r), cells_with_votes(r)) for r in table.select('tr')]
        for i in range(len(parsed) - 1):
            away, av = parsed[i]
            home, hv = parsed[i + 1]
            if not away or not home or away == home or av is None or hv is None:
                continue
            markets = {}
            for key, idx, is_total in [('spread', 2, False), ('moneyline', 3, False), ('total', 4, True)]:
                pair = market_pair(av[idx], hv[idx], total=is_total)
                if pair:
                    markets[key] = pair
            if markets:
                # Multiple rows for the same matchup may represent different games.
                # Do not guess which one corresponds to the NBA schedule.
                games.setdefault((away, home), []).append(markets)
    return games


def parse_espn_schedule(payload, today):
    matches = defaultdict(set)
    for event in payload.get('events', []):
        competitions = event.get('competitions') or []
        if not competitions:
            continue
        sides = {}
        for team in competitions[0].get('competitors', []):
            code = (team.get('team') or {}).get('abbreviation', '').upper()
            if code == 'NO':
                code = 'NOP'
            if code == 'UTAH':
                code = 'UTA'
            if team.get('homeAway') in ('home', 'away'):
                sides[team['homeAway']] = code
        if not sides.get('away') or not sides.get('home'):
            continue
        stamp = event.get('date') or competitions[0].get('date')
        if not stamp:
            continue
        try:
            when = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(TZ)
        except ValueError:
            continue
        if today - dt.timedelta(days=1) <= when.date() <= today + dt.timedelta(days=5):
            matches[(sides['away'], sides['home'])].add(when.date().isoformat())
    return matches


def run():
    today = dt.datetime.now(TZ).date()
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'zh-TW,zh;q=0.9'})
    source_response = session.get(SOURCE, params={'allianceid': '3'}, timeout=30)
    source_response.raise_for_status()
    votes = parse_source(source_response.text)
    print('Source matchups parsed:', len(votes), flush=True)
    if not votes:
        raise RuntimeError('No valid vote rows parsed from the public source; old JSON preserved.')

    # ESPN dates are US-centered. Query each date around the target window to
    # avoid missing Taiwan-morning games at US-day boundaries.
    schedule = defaultdict(set)
    for offset in range(-2, 6):
        day = today + dt.timedelta(days=offset)
        response = session.get(SCOREBOARD, params={'dates': day.strftime('%Y%m%d'), 'limit': 200}, timeout=30)
        response.raise_for_status()
        for matchup, dates in parse_espn_schedule(response.json(), today).items():
            schedule[matchup].update(dates)
    print('ESPN matchups found:', len(schedule), flush=True)

    results = []
    for matchup, options in votes.items():
        dates = schedule.get(matchup, set())
        if len(options) != 1 or len(dates) != 1:
            print('Skipping ambiguous/unmatched:', matchup, 'source rows:', len(options), 'dates:', sorted(dates))
            continue
        away, home = matchup
        results.append({'date': next(iter(dates)), 'away': away, 'home': home, 'markets': options[0]})
    if not results:
        raise RuntimeError('No uniquely matched NBA games. Existing JSON preserved; source may show a different date.')

    data = {'source': '玩運彩 NBA 所有會員預測比例',
            'source_url': SOURCE + '?allianceid=3',
            'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'games': sorted(results, key=lambda x: (x['date'], x['away'], x['home']))}
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved uniquely matched games:', len(results), flush=True)


if __name__ == '__main__':
    run()
