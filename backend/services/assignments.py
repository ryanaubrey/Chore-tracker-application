from ..database import chores
from .authorization import require_admin, require_user
from .schedule import scheduled
from .users import resolve_assignee
from .validation import integer, parse_day, require


def change_occurrence(db, user, data, action):
    require_user(user)
    chore_id = integer(data, "id")
    day = parse_day(data.get("day"))
    chore = chores.active_chore(db, chore_id)
    require(chore, "Chore is unavailable.", 404)
    saved = chores.find_occurrence(db, chore_id, day.isoformat())
    require(saved or scheduled(chore, day), "Chore is unavailable on this date.", 404)
    assignee = saved["assignee"] if saved else chore["assignee"]
    completed = saved["completed"] if saved else 0
    require(not completed, "This chore was already completed.", 409)
    if action == "assign":
        require_admin(user, "Only admins can change assignments.")
        assignee = resolve_assignee(db, data)
    elif action == "claim":
        require(assignee is None, "This chore is already assigned.", 409)
        assignee = user["id"]
    elif action == "complete":
        require(assignee == user["id"], "Only the assigned member can complete this chore.", 403)
        completed = 1
    else:
        raise ValueError("Unknown occurrence action.")
    chores.save_occurrence(db, chore_id, day.isoformat(), assignee, completed, exists=saved is not None)
