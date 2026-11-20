import hmac
import secrets
import time


from ..database import accounts
from .authorization import require_admin
from .validation import clean, require


INVITE_AGE = 7 * 86400


def set_invite_deadline(db):
    accounts.set_invite_expiry(db, str(int(time.time()) + INVITE_AGE))


def invitation_expired(db):
    expires = accounts.get_setting(db, "invite_expires")
    return not expires or not expires.isascii() or not expires.isdecimal() or int(expires) <= int(time.time())


def initialize_setup(db, configured_key, hosted):
    if accounts.has_users(db):
        if accounts.get_setting(db, "invite") and accounts.get_setting(db, "invite_expires") is None:
            set_invite_deadline(db)
        return
    if hosted and not configured_key and not accounts.get_setting(db, "setup"):
        raise ValueError("Set CHORES_SETUP_KEY before the first hosted startup.")
    key = configured_key
    if not key and accounts.get_setting(db, "setup") is None:
        key = secrets.token_urlsafe(18)
    if key:
        accounts.set_setup_key(db, key)
    if not hosted:
        print("Owner setup key:", key or accounts.get_setting(db, "setup"), flush=True)


def validate_key(db, data, owner):
    key = accounts.get_setting(db, "setup" if owner else "invite")
    supplied = clean(data, "key", 200).encode()
    require(key is not None and hmac.compare_digest(key.encode(), supplied),
            "This setup key or invitation is invalid.", 403)
    if not owner:
        require(not invitation_expired(db), "This invitation has expired. Ask an administrator for a new link.", 403)


def finish_setup(db):
    accounts.create_invitation(db, secrets.token_urlsafe(24))
    set_invite_deadline(db)


def rotate(db, user):
    require_admin(user)
    accounts.update_invitation(db, secrets.token_urlsafe(24))
    set_invite_deadline(db)
