#!/usr/bin/env python3
"""
Timezone utilities for Indian trading bot
==========================================
Provides IST (Indian Standard Time) timezone support
"""

from datetime import datetime, date, time as dt_time
from zoneinfo import ZoneInfo

# IST Timezone
IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Get current time in IST"""
    return datetime.now(IST)


def today_ist() -> date:
    """Get today's date in IST"""
    return now_ist().date()


def current_time_ist() -> dt_time:
    """Get current time (without date) in IST"""
    return now_ist().time()


def ist_datetime(dt: datetime) -> datetime:
    """Convert a naive datetime to IST datetime"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def format_ist_datetime(dt: datetime = None, fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Format datetime in IST
    If dt is None, uses current time
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime(fmt)
