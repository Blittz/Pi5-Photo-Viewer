"""Versioned event-file validation and Pacific-time presentation (no Qt)."""
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import stat
import sys
from utils.solar import MEDFORD_TIMEZONE

EVENTS_FILE=Path(os.getenv('SCHEDULED_EVENTS_FILE',str(Path.home()/'.local/state/discord-photo-viewer/events.json'))).expanduser()
MAX_BYTES=256*1024
STALE_AFTER=15*60
NO_END_ACTIVE_LIMIT=timedelta(hours=4)
STARTING_GRACE=timedelta(minutes=5)


def instant(value):
    if not isinstance(value,str):raise ValueError('Missing time')
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Missing timezone')
    return result.astimezone(timezone.utc)


def identifier(value):
    if not isinstance(value,str) or not value.isdigit():raise ValueError('Invalid ID')
    return value


def text(value):
    if not isinstance(value,str) or not value.strip() or len(value)>100:raise ValueError('Invalid text')
    # Keep labels plain and prevent newlines/control characters expanding the UI.
    return ' '.join(value.split())


def validate_snapshot(data):
    if not isinstance(data,dict) or data.get('schema_version')!=1 or type(data.get('refresh_ok')) is not bool:
        raise ValueError('Invalid snapshot')
    instant(data['last_attempted_refresh'])
    if data.get('last_successful_refresh') is not None:instant(data['last_successful_refresh'])
    servers=data.get('servers');events=data.get('events')
    if not isinstance(servers,list) or not isinstance(events,list) or len(servers)>1000 or len(events)>1000:
        raise ValueError('Invalid collections')
    names={}
    for server in servers:
        sid=identifier(server['id'])
        if sid in names or type(server.get('refresh_ok')) is not bool:raise ValueError('Invalid server')
        if server.get('last_successful_refresh') is not None:instant(server['last_successful_refresh'])
        if server['refresh_ok'] and server.get('last_successful_refresh') is None:raise ValueError('Missing refresh time')
        names[sid]=text(server['name'])
    if data['refresh_ok'] and (not names or not all(s['refresh_ok'] for s in servers) or not data.get('last_successful_refresh')):
        raise ValueError('Incomplete fresh snapshot')
    unique=set();clean=[]
    for event in events:
        eid=identifier(event['id']);sid=identifier(event['server_id'])
        if sid not in names or (sid,eid) in unique:raise ValueError('Invalid event identity')
        unique.add((sid,eid))
        start=instant(event['start_at']);end=instant(event['end_at']) if event.get('end_at') else None
        if end and end<=start:raise ValueError('Invalid event end')
        if event.get('status') not in ('scheduled','active','completed','canceled'):raise ValueError('Invalid status')
        kind=event.get('kind');channel=event.get('channel_id')
        if kind=='external' and channel is not None:raise ValueError('Invalid external event')
        if kind=='channel':identifier(channel)
        elif kind!='external':raise ValueError('Invalid association')
        clean.append({'id':eid,'server_id':sid,'title':text(event['title']),'start_at':start.isoformat(),
                      'end_at':end.isoformat() if end else None,'status':event['status'],'kind':kind,'channel_id':channel})
    return {'schema_version':1,'refresh_ok':data['refresh_ok'],
            'last_attempted_refresh':data['last_attempted_refresh'],
            'last_successful_refresh':data.get('last_successful_refresh'),
            'servers':[{'id':s['id'],'name':names[s['id']], 'refresh_ok':s['refresh_ok'],
                        'last_successful_refresh':s.get('last_successful_refresh')} for s in servers], 'events':clean}


def read_snapshot(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):raise ValueError('Not a regular file')
        data=file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('Oversized snapshot')
    return validate_snapshot(json.loads(data))


def countdown(seconds):
    minutes=max(1,math.ceil(seconds/60))
    if seconds<60:return 'Starts in less than a minute'
    if minutes<60:return f'Starts in {minutes}m'
    hours,minutes=divmod(minutes,60)
    if hours<24:return f'Starts in {hours}h'+(f' {minutes}m' if minutes else '')
    days,hours=divmod(hours,24)
    return f'Starts in {days}d'+(f' {hours}h' if hours else '')


def event_view(snapshot,read_failed=False,now=None):
    now=now or datetime.now(timezone.utc)
    base={'heading':'NEXT SESSION','title':'Event data unavailable','when':'',
          'detail':'Waiting for Discord event feed','note':'','countdown':'','imminent':False,'stale':True}
    if not snapshot:return base
    try:
        refreshed=instant(snapshot['last_successful_refresh'])
        age=(now-refreshed).total_seconds()
    except (ValueError,TypeError):refreshed=None;age=None
    stale=read_failed or not snapshot['refresh_ok'] or age is None or age>STALE_AFTER or age < -300
    names={s['id']:s['name'] for s in snapshot['servers']}
    future=[];current=[]
    for event in snapshot['events']:
        start=instant(event['start_at']);end=instant(event['end_at']) if event['end_at'] else None
        if event['status']=='scheduled':
            if start>now:future.append(event)
            elif now-start<=STARTING_GRACE and (end is None or now<end):current.append(event)
        elif event['status']=='active' and now<(end or start+NO_END_ACTIVE_LIMIT):
            current.append(event)
    chosen=min(future,key=lambda e:(instant(e['start_at']),e['server_id'],e['id'])) if future else (
        max(current,key=lambda e:instant(e['start_at'])) if current else None)
    source='Discord · '+(next(iter(names.values())) if len(names)==1 else f'{len(names)} servers')
    note=''
    if stale:
        note='STALE · '+('Last refreshed '+refreshed.astimezone(MEDFORD_TIMEZONE).strftime('%a %I:%M %p %Z').replace(' 0',' ') if refreshed else 'No successful refresh')
    if chosen:
        start=instant(chosen['start_at']);seconds=(start-now).total_seconds()
        future_event=chosen['status']=='scheduled' and seconds>0
        progress=countdown(seconds) if future_event else ('In progress' if chosen['status']=='active' else 'Starting now')
        if not future_event and not chosen['end_at']:progress+=' · End not listed'
        base.update(heading='LAST KNOWN SESSION' if stale else ('NEXT SESSION' if future_event else 'SESSION NOW'),
                    title=chosen['title'],when=start.astimezone(MEDFORD_TIMEZONE).strftime('%A, %b %d, %Y · %I:%M %p %Z').replace(' 0',' '),
                    detail=names[chosen['server_id']]+' · '+('Unconfirmed · ' if stale else '')+progress,
                    imminent=not stale and future_event and seconds<=24*60*60,stale=stale,note=note,
                    countdown=countdown(seconds) if future_event else '')
    else:
        base.update(title='Event data stale' if stale else 'No upcoming events',detail=source,
                    note=note,stale=stale)
    return base


if __name__=='__main__':
    # A tiny bounded worker reads the local file; no file I/O runs in the GUI.
    try:print(json.dumps(read_snapshot(sys.argv[1]),ensure_ascii=False))
    except Exception:raise SystemExit(1)
