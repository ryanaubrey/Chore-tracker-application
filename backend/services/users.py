from ..database import accounts
from .authorization import require_owner
from .validation import integer, require


def change_role(db, user, data):
    require_owner(user)
    role = data.get("role")
    require(role in ("member", "admin"), "Invalid role.")
    accounts.set_role(db, integer(data, "id"), role)


def resolve_assignee(db, data):
    if data.get("assignee") is None:
        return None
    assignee = integer(data, "assignee")
    require(accounts.user_exists(db, assignee), "Choose a household member.")
    return assignee
