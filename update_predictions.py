#!/usr/bin/env python3
"""Read publicly visible NBA community prediction rows into GitHub Pages JSON.
No credentials, hidden endpoints, or synthetic prediction values.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'community_predictions.json'
URL = 'https://www.playsport.cc/predict/scale'
TEAMS = {
 '老鷹':'ATL','塞爾提':'BOS','塞爾提克':'BOS','籃網':'BKN','黃蜂':'CHA','公牛':'CHI','騎士':'CLE','獨行俠':'DAL','小牛':'DAL','金塊':'DEN','活塞':'DET','勇士':'GSW','火箭':'HOU','溜馬':'IND','快艇':'LAC','湖人':'LAL','灰熊':'MEM','熱火':'MIA','公鹿':'MIL','灰狼':'MIN','鵜鶘':'NOP','尼克':'NYK','雷霆':'OKC','魔術':'ORL','76人':'PHI','七六人':'PHI','太陽':'PHX','拓荒者':'POR','國王':'SAC','馬刺':'SAS','暴龍':'TOR','爵士':'UTA','巫師':'WAS'
}
PCT = re.compile(r'(?<!\d)(100|\d{1,2})\s*%\s*(\d[\d,]*)\s*人預測')


def row_team(row):
    # Team links on the source are usually in a heading within each team row.
    for tag in row.select('h3,h4,a'):
        name = tag.get_text(' ', strip=True).replace(' ', '')
        if name in TEAMS:
            return TEAMS[name]
    return None


def cells_with_votes(row):
    """Extract each market column by vote percentage + prediction count.
    If columns are merged in the source, return None rather than shift markets.
    """
    cells = row.find_all(['td'], recursive=False)
    result = []
    for cell in cells:
        txt = cell.get_text(' ', strip=True)
        matches = PCT.findall(txt)
        if len(matches) == 1:
            result.append((int(matches[0][0]), int(matches[0][1].replace(',', '')), txt))
        elif len(matches) > 1:
            # Ambiguous cell grouping: do not infer columns.
            return None
    if len(result) != 5:
        return None
    return result


def market_pair(a, b, key, *, total=False):
    if a[0] + b[0] not in range(99, 102):
        return None
    left, right = ('over', 'under') if total else ('away', 'home')
    value = {left:a[0], right:b[0], 'counts':{left:a[1], right:b[1]}}
    if total:
        m = re.search(r'大\s*(\d+(?:\.\d+)?)', a[2])
        if m:
            value['line'] = float(m.group(1))
    return value


def parse(html, date):
    soup = BeautifulSoup(html, 'html.parser')
    games = []
    for table in soup.select('table'):
        rows = table.select('tr')
        parsed = [(row_team(r), cells_with_votes(r)) for r in rows]
        for i in range(len(parsed)-1):
            away, av = parsed[i]
            home, hv = parsed[i+1]
            if not away or not home or away == home or av is None or hv is None:
                continue
            # Source order: international spread, international total,
            # sports-lottery spread, sports-lottery moneyline, sports-lottery total.
            # We only use the explicitly identified five-vote-column rows.
            fields = [('spread',2,False),('moneyline',3,False),('total',4,True)]
            markets = {}
            for key,j,is_total in fields:
                pair = market_pair(av[j],hv[j],key,total=is_total)
                if pair:
                    markets[key] = pair
            if markets:
                games.append({'date':date,'away':away,'home':home,'markets':markets})
    return games


def run():
    tz = ZoneInfo('Asia/Taipei')
    today = dt.datetime.now(tz).date()
    session = requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0 (compatible; NBACommunityDisplay/1.0)','Accept-Language':'zh-TW,zh;q=0.9'})
    all_games = {}
    errors = []
    for offset in (0,1,2):
        day = today + dt.timedelta(days=offset)
        try:
            r = session.get(URL,params={'allianceid':'3','gametime':day.strftime('%Y%m%d')},timeout=25)
            r.raise_for_status()
            found = parse(r.text,day.isoformat())
            for g in found:
                all_games[(g['date'],g['away'],g['home'])] = g
            print(day, 'parsed games:',len(found))
        except requests.RequestException as e:
            errors.append(str(e))
            print(day,'fetch error:',str(e)[:200])
    if not all_games:
        # Keep last verified data on source failure; don't overwrite with fake or empty values.
        raise RuntimeError('No reliably parsed prediction rows; preserving existing JSON. '+('; '.join(errors))[:300])
    data={'source':'玩運彩 NBA 所有會員預測比例','source_url':URL+'?allianceid=3',
          'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
          'games':sorted(all_games.values(),key=lambda x:(x['date'],x['away'],x['home']))}
    OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('saved',len(data['games']),'games')

if __name__=='__main__':
    run()
