import datetime
import sys

import pytz

print(f"python version: {sys.version}")
print(f"pytz version: {pytz.__version__}\n")


def print_dst_aware_time(tz_aware_dt):
    tz_aware_dt_with_dst = tz_aware_dt + tz_aware_dt.dst()
    if not tz_aware_dt.dst():
        print(f"[{tz_aware_dt}] tzaware now, dst-aware (dst: false, add dst): {tz_aware_dt_with_dst}")
    else:
        print(f"[{tz_aware_dt}] tzaware now, dst-aware (dst: true, do not add dst): {tz_aware_dt}")


local_timezone = pytz.timezone("Europe/Rome")

utc_now = datetime.datetime.now(datetime.timezone.utc)
utc_now_naive = datetime.datetime.utcnow()

print(f"utc now: {utc_now}")
print(f"utc now naive: {utc_now_naive}")
print(f"")

now_tzaware = utc_now.astimezone(local_timezone)

print_dst_aware_time(now_tzaware)
print(f"")


for month in (1, 6):
    now_dt = datetime.datetime(year=2023, month=month, day=1, hour=10)
    now_dt_rome = local_timezone.localize(now_dt)

    print_dst_aware_time(now_dt_rome)
