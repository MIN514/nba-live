#!/usr/bin/env python3
"""Export verifiable public NBA community predictions to GitHub Pages.

The source can ignore gametime and return a default day. Never label rows
with the requested date unless that date is actually evidenced in the page.
"""
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'community_predictions.json'
URL = 'https://www.playsport.cc/predict/scale'
TEAMS = {
 '老鷹':'ATL','塞爾提':'BOS','塞爾提克':'BOS','籃網':'BKN','黃蜂':'CHA','公牛':'CHI',
 '騎士':'CLE','獨行俠':'DAL','小牛':'DAL','金塊':'DEN','活塞':'DET','勇士':'GSW',
 '火箭':'HOU','溜馬':'IND','快艇':'LAC','湖人':'LAL','灰熊':'MEM','熱火':'MIA',
 '公鹿':'MIL','灰狼':'MIN','鵜鶘':'NOP','尼克':'NYK','雷霆':'OKC','魔術':'ORL',
 '76人':'PHI','七六人':'PHI','太陽':'PHX','拓荒者':'POR','國王':'SAC',
 '馬刺':'SAS','暴龍':'TOR','爵士':'UTA','巫師':'WAS'
}
PCT = re.compile(r'(?<!\d)(100|\d{1,2})\s*%\s*(\d[\d,]*)\s*人預測')
DATE_RE = re.compile(r'(?<!\d)(20\d{2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})(?!\d)')
DATE8_RE = re.compile(r'(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)')


def parse_date(text):
    for pattern in (DATE_RE, DATE8_RE):
        for m in pattern.finditer(text):
            try:
                return dt.date(*(int(x) for x in m.groups())).isoformat()
            except ValueError:
                pass
    return None


def row_team(row):
    for tag in row.select('h3,h4,a'):
        name = re.sub(r'\s+', '', tag.get_text(' ', strip=True))
        if name in TEAMS:
            return TEAMS[name]
    return None


def cells_with_votes(row):
    cells = row.find_all('td', recursive=False)
    result = []
    for cell in cells:
        txt = cell.get_text(' ', strip=True)
        matches = PCT.findall(txt)
        if len(matches) > 1:
            return None
        if len(matches) == 1:
            result.append((int(matches[0][0]), int(matches[0][1].replace(',', '')), txt))
    return result if len(result) == 5 else None


def market_pair(a, b, *, total=False):
    if not 99 <= a[0] + b[0] <= 101:
        return None
    left, right = ('over', 'under') if total else ('away', 'home')
    value = {left: a[0], right: b[0], 'counts': {left: a[1], right: b[1]}}
    if total:
        m = re.search(r'大\s*(\d+(?:\.\d+)?)', a[2])
        if m:
            value['line'] = float(m.group(1))
    return value


def table_date(table):
    # Prefer a date within the table heading/caption. If absent, use the
    # nearest previous heading, but never use a date from another match row.
    caption = table.find('caption')
    if caption:
        found = parse_date(caption.get_text(' ', strip=True))
        if found:
            return found
    for header in table.select('thead,th'):
        found = parse_date(header.get_text(' ', strip=True))
        if found:
            return found
    for previous in table.find_all_previous(['h1','h2','h3','h4','h5','time'], limit=12):
        found = parse_date(previous.get('datetime', '') + ' ' + previous.get_text(' ', strip=True))
        if found:
            return found
    return None


def parse(html, requested_date):
    soup = BeautifulSoup(html, 'html.parser')
    games = []
    for table in soup.select('table'):
        fallback_date = table_date(table)
        rows = table.select('tr')
        parsed = [(row_team(r), cells_with_votes(r), parse_date(r.get_text(' ', strip=True))) for r in rows]
        for i in range(len(parsed)-1):
            away, av, adate = parsed[i]
            home, hv, hdate = parsed[i+1]
            if not away or not home or away == home or av is None or hv is None:
                continue
            if adate and hdate and adate != hdate:
                continue
            actual_date = adate or hdate or fallback_date
            # Some source responses ignore gametime. Do not mislabel their rows.
            if not actual_date:
                continue
            if actual_date != requested_date:
                continue
            markets = {}
            for key, idx, total in [('spread', 2, False), ('moneyline', 3, False), ('total', 4, True)]:
                pair = market_pair(av[idx], hv[idx], total=total)
                if pair:
                    markets[key] = pair
            if markets:
                games.append({'date': actual_date, 'away': away, 'home': home, 'markets': markets})
    return games


def run():
    today = dt.datetime.now(ZoneInfo('Asia/Taipei')).date()
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (compatible; NBACommunityDisplay/1.1)',
        'Accept-Language': 'zh-TW,zh;q=0.9',
    })
    all_games = {}
    for offset in range(4):
        day = today + dt.timedelta(days=offset)
        try:
            response = session.get(URL, params={'allianceid': '3', 'gametime': day.strftime('%Y%m%d')}, timeout=25)
            response.raise_for_status()
            found = parse(response.text, day.isoformat())
            print(f'{day}: verified games = {len(found)}; final URL = {response.url}', flush=True)
            for game in found:
                all_games[(game['date'], game['away'], game['home'])] = game
        except requests.RequestException as exc:
            print(f'{day}: fetch failed: {exc}', flush=True)
    if not all_games:
        raise RuntimeError('No games with verified dates found. Existing JSON left untouched. Check whether the source exposes dates and supports gametime.')
    data = {
        'source': '玩運彩 NBA 所有會員預測比例',
        'source_url': URL + '?allianceid=3',
        'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'games': sorted(all_games.values(), key=lambda g: (g['date'], g['away'], g['home']))
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Saved {len(data["games"])} verified games to {OUTPUT.name}', flush=True)


if __name__ == '__main__':
    run()
