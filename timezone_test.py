import datetime
import pytz
import sys

print(f"python version: {sys.version}")
print(f"pytz version: {pytz.__version__}\n")

utc_now = datetime.datetime.now(datetime.timezone.utc)
utc_now_naive = datetime.datetime.utcnow()
now_tzaware = utc_now.astimezone(pytz.timezone("Europe/Rome"))

print(f"utc now: {utc_now}")
print(f"utc now naive: {utc_now_naive}")
print(f"now_tzaware: {now_tzaware}")
print(f"utc_now_naive.hour: {utc_now_naive.hour}, utc_now.hour: {utc_now.hour}, now_tzaware.hour: {now_tzaware.hour}")
