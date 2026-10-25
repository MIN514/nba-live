#!/usr/bin/env python3
"""Download ESPN NBA injury reports and publish a timestamped, validated snapshot."""
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
IDS = {'1':'ATL','2':'BOS','17':'BKN','30':'CHA','4':'CHI','5':'CLE','6':'DAL','7':'DEN','8':'DET','9':'GSW','10':'HOU','11':'IND','12':'LAC','13':'LAL','29':'MEM','14':'MIA','15':'MIL','16':'MIN','3':'NOP','18':'NYK','25':'OKC','19':'ORL','20':'PHI','21':'PHX','22':'POR','23':'SAC','24':'SAS','28':'TOR','26':'UTA','27':'WAS'}
ABBR={x:x for x in IDS.values()}; ABBR['GS']='GSW'; ABBR['NY']='NYK'; ABBR['SA']='SAS'; ABBR['NO']='NOP'; ABBR['UTAH']='UTA'

def label(v):
    if isinstance(v,str): return v
    if isinstance(v,dict): return str(v.get('description') or v.get('displayName') or v.get('name') or v.get('abbreviation') or '')
    return ''

def entries(v):
    if isinstance(v,list):return v
    if isinstance(v,dict):
        for k in ('injuries','items','athletes'):
            if isinstance(v.get(k),list):return v[k]
    return []

def team_code(v):
    t=v.get('team') or v.get('teamInfo') or {}
    if not isinstance(t,dict):t={}
    tid=str(t.get('id') or v.get('teamId') or '')
    return IDS.get(tid) or ABBR.get(str(t.get('abbreviation') or v.get('abbreviation') or '').upper())

def row(v):
    a=v.get('athlete') or v.get('player') or {}
    if not isinstance(a,dict):a={}
    details=v.get('details') or {}
    if not isinstance(details,dict):details={'detail':str(details)}
    status=v.get('status') or v.get('type') or ''
    if isinstance(status,dict): status=status.get('description') or status.get('name') or status.get('type') or ''
    name=a.get('displayName') or a.get('fullName') or v.get('displayName') or v.get('name')
    if not name:return None
    pos=a.get('position') or v.get('position') or {}
    return {'name':str(name),'pos':label(pos),'st':label(status),'detail':label(details.get('detail') or details.get('type') or v.get('description') or v.get('shortComment')),'returnDate':str(v.get('returnDate') or v.get('returnsAt') or v.get('estimatedReturnDate') or '')}

req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0 (compatible; NBAStatsUpdater/1.0)','Accept':'application/json'})
with urllib.request.urlopen(req,timeout=25) as response:
    payload=json.load(response)
if not isinstance(payload,dict) or not isinstance(payload.get('injuries'),list):
    raise RuntimeError('ESPN 傷病資料格式不符，保留舊檔')

groups=payload['injuries']

print('ESPN top-level keys:', list(payload.keys()), flush=True)
print('Number of injury groups:', len(groups), flush=True)

if groups and isinstance(groups[0], dict):
    first = groups[0]
    print('First group keys:', list(first.keys()), flush=True)
    print('First group team:', first.get('team'), flush=True)
    print('First group injuries type:', type(first.get('injuries')).__name__, flush=True)

    sample = entries(first)
    print('Number of entries in first group:', len(sample), flush=True)

    if sample and isinstance(sample[0], dict):
        print('First entry keys:', list(sample[0].keys()), flush=True)

if not groups:
    raise RuntimeError('ESPN 回傳空清單，保留舊檔避免誤判')
teams={code:[] for code in IDS.values()}
for group in groups:
    if not isinstance(group,dict):continue
    code=team_code(group)
    if code:
        for v in entries(group):
            if isinstance(v,dict):
                item=row(v)
                if item:teams[code].append(item)
if not sum(map(len,teams.values())):
    raise RuntimeError('無法解析任何球員；保留舊檔，請檢查 ESPN 資料結構')
output={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':URL,'teams':teams}
Path('injuries.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Injuries synced:',sum(map(len,teams.values())))
