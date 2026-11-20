from ..database import accounts, chores
from .invitations import invitation_expired
from .authorization import is_admin, require_admin
from .schedule import today, week_days, week_items
from .users import resolve_assignee
from .validation import clean, integer, parse_day, require


def board(db, user, query):
    current = today()
    result = dict(user=dict(user) if user else None, today=current.isoformat(),
                  setup=not accounts.has_users(db))
    if not user:
        return result
    anchor = parse_day(query["day"][0]) if "day" in query else current
    require(1901 <= anchor.year <= 9998, "Date is outside the supported range.")
    days = week_days(anchor)
    result["days"] = days
    definitions = list(chores.all_chores(db))
    result["items"] = week_items(
        days, definitions, chores.occurrences_between(db, days[0], days[-1]),
    )
    result["members"] = [dict(row) for row in accounts.members(db)]
    if is_admin(user):
        result["chores"] = [dict(row) for row in chores.active_chores(db)]
        result["invite"] = accounts.get_setting(db, "invite")
        result["invite_expired"] = invitation_expired(db)
    return result


def save(db, user, data):
    require_admin(user)
    frequency = data.get("frequency")
    require(frequency in ("once", "daily", "weekly"), "Choose a repeat schedule.")
    start = parse_day(data.get("start"))
    require(1901 <= start.year <= 9998, "Date is outside the supported range.")
    weekday = data.get("weekday") if frequency == "weekly" else start.weekday()
    require(type(weekday) is int and 0 <= weekday <= 6, "Choose a weekday.")
    values = dict(title=clean(data, "title", 100), details=clean(data, "details", 500, False),
                  frequency=frequency, start=start.isoformat(), weekday=weekday,
                  assignee=resolve_assignee(db, data))
    if data.get("id") is None:
        chores.create_chore(db, values)
    else:
        chores.update_chore(db, integer(data, "id"), values)


def retire(db, user, data):
    require_admin(user)
    chores.retire_chore(db, integer(data, "id"))
