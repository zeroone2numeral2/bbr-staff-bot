import datetime
import pytz
import sys

print(f"python version: {sys.version}")
print(f"pytz version: {pytz.__version__}")

utcnow = datetime.datetime.utcnow()
now = utcnow.astimezone(pytz.timezone("Europe/Rome"))

print(f"utcnow: {utcnow}")
print(f"now: {now}")
print(f"utcnow.hour{utcnow.hour}, now.hour: {now.hour}")
