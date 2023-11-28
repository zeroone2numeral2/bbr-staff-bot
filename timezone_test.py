import datetime
import sys

import pytz

print(f"python version: {sys.version}")
print(f"pytz version: {pytz.__version__}\n")

local_time = pytz.timezone("Europe/Rome")

utc_now = datetime.datetime.now(datetime.timezone.utc)
utc_now_naive = datetime.datetime.utcnow()
now_tzaware = utc_now.astimezone(local_time)
now_rome = local_time.localize(utc_now_naive)

print(f"utc now: {utc_now}")
print(f"utc now naive: {utc_now_naive}")
print(f"tzaware now: {now_tzaware}")

for month in (1, 6):
    now_dt = datetime.datetime(year=2023, month=month, day=1)
    now_dt_rome = local_time.localize(now_dt)
    now_dt_rome_dst_timedelta = now_dt_rome + now_dt_rome.dst()

    print(f"dst rome: {now_dt_rome.dst()}, bool: {bool(now_dt_rome.dst())}, result: {now_dt_rome_dst_timedelta}")
