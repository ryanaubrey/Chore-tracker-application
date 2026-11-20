import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app


def today():
    try:
        return datetime.now(ZoneInfo(current_app.config["CHORES_TIMEZONE"] or "America/New_York")).date()
    except Exception:
        if os.name == "nt" and current_app.config["CHORES_TIMEZONE"] is None:
            return date.today()
        raise


def scheduled(chore, day):
    return day.isoformat() >= chore["start"] and (
        chore["frequency"] == "daily"
        or chore["frequency"] == "weekly" and day.weekday() == chore["weekday"]
        or chore["frequency"] == "once" and day.isoformat() == chore["start"]
    )


def week_days(anchor):
    monday = anchor - timedelta(days=anchor.weekday())
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def week_items(days, chores, occurrences):
    saved = {(row["chore_id"], row["day"]): row for row in occurrences}
    items = []
    for day in days:
        for chore in chores:
            existing = saved.get((chore["id"], day))
            if chore["retired"] and not (existing and existing["completed"]):
                continue
            if existing is None and not scheduled(chore, date.fromisoformat(day)):
                continue
            items.append(dict(id=chore["id"], day=day, title=chore["title"],
                              details=chore["details"], frequency=chore["frequency"],
                              assignee=existing["assignee"] if existing else chore["assignee"],
                              completed=bool(existing and existing["completed"])))
    return items
