"""Use the channel's configured Buffer slots; never exceed three weekly posts."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from .content import stamp

def available_slots(channel, posts, now, config):
    if channel['isDisconnected'] or channel['isLocked'] or channel['isQueuePaused']:return []
    zone=ZoneInfo(channel['timezone']);local=now.astimezone(zone)
    queued=[p for p in posts if p['channelId']==channel['id'] and p['status'] in {'scheduled','sending'}]
    if len(queued)>=min(10,config['max_queue_per_channel']):return []
    schedules={s['day']:s for s in channel['postingSchedule']}
    occupied=set();counts={}
    for p in posts:
        if p['channelId']!=channel['id'] or p['status'] not in {'scheduled','sending','sent'}:continue
        value=p.get('dueAt') or p.get('createdAt')
        if not value:raise ValueError('Cannot establish occupied queue slots')
        dt=stamp(value).astimezone(zone);week=dt.isocalendar()[:2]
        counts[week]=counts.get(week,0)+1;occupied.add(dt)
    slots=[]
    for offset in range(8):
        day=local.date()+timedelta(days=offset)
        schedule=schedules.get(day.strftime('%a').lower(),{})
        if schedule.get('paused',True):continue
        for value in sorted(schedule.get('times',[])):
            hour,minute=map(int,value.split(':'))
            dt=datetime(day.year,day.month,day.day,hour,minute,tzinfo=zone)
            week=dt.isocalendar()[:2]
            if dt<=now+timedelta(minutes=30) or dt>now+timedelta(days=7) or dt in occupied:continue
            if counts.get(week,0)>=min(3,config['max_posts_per_channel_per_week']):continue
            slots.append(dt.astimezone(timezone.utc));counts[week]=counts.get(week,0)+1
            if len(slots)+len(queued)>=min(10,config['max_queue_per_channel']):return slots
    return slots

def publishing_allowed(config, state, env):
    return (config.get('publishing_approved') is True and not config.get('paused',True)
            and not state.get('paused',False) and env.get('SOCIAL_PUBLISHING_ENABLED')=='true')
