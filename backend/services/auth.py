import hashlib
import hmac
import secrets
import time

from werkzeug.security import check_password_hash, generate_password_hash

from ..database import accounts
from . import invitations
from .authorization import require_user
from .validation import clean, require


SESSION_AGE = 86400 * 14


PASSWORD_METHOD = "scrypt:131072:8:1"
DUMMY_HASH = PASSWORD_METHOD + "$missing-account-salt$" + "0" * 128


def password_hash(password):
    return generate_password_hash(password, method=PASSWORD_METHOD)


def verify_legacy(password, stored):
    salt, separator, digest = stored.partition(":")
    if not separator or len(salt) != 32 or len(digest) != 128:
        return False
    try:
        raw_salt = bytes.fromhex(salt)
    except ValueError:
        return False
    actual = hashlib.scrypt(password.encode(), salt=raw_salt, n=16384, r=8, p=1)
    return hmac.compare_digest(actual.hex().encode(), digest.encode())


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(db, token):
    return accounts.session_user(db, token, int(time.time()))


def credentials(db, data):
    username = clean(data, "username", 64).casefold()
    password = data.get("password")
    require(isinstance(password, str) and 8 <= len(password) <= 128
            and not any(0xD800 <= ord(character) <= 0xDFFF for character in password),
            "Use a password with 8 to 128 characters.")
    return username, password, accounts.find_user(db, username)


def start_session(db, previous, user_id):
    fresh = secrets.token_urlsafe(32)
    now = int(time.time())
    accounts.replace_session(db, previous, token_hash(fresh), now, now + SESSION_AGE, user_id)
    return fresh


def login(db, data, previous):
    _, password, account = credentials(db, data)
    stored = account["password"] if account else DUMMY_HASH
    legacy = "$" not in stored
    valid = verify_legacy(password, stored) if legacy else check_password_hash(stored, password)
    require(account and valid, "Username or password is incorrect.", 401)
    if legacy:
        accounts.update_password(db, account["id"], password_hash(password))
    return start_session(db, previous, account["id"])


def register(db, data, previous, *, owner):
    username, password, account = credentials(db, data)
    invitations.validate_key(db, data, owner)
    require(not account, "That username is already in use.", 409)
    user_id = accounts.create_user(db, clean(data, "name", 80), username, password_hash(password),
                                   "owner" if owner else "member")
    if owner:
        invitations.finish_setup(db)
    return start_session(db, previous, user_id)


def logout(db, user, token):
    require_user(user)
    accounts.delete_session(db, token)
