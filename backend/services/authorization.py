from .validation import require


def require_user(user):
    require(user, "Sign in first.", 401)


def is_admin(user):
    return user is not None and user["role"] in ("admin", "owner")


def require_admin(user, message="Only admins can make this change."):
    require_user(user)
    require(is_admin(user), message, 403)


def require_owner(user):
    require_admin(user)
    require(user["role"] == "owner", "Only the owner can manage admin access.", 403)
