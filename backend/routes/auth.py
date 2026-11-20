from flask import current_app

from ..services import auth, invitations, users
from . import mutation


def session_cookie(value, age):
    secure = "; Secure" if current_app.config["CHORES_PUBLIC_URL"].startswith("https://") else ""
    return f"chores_session={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}{secure}"


@mutation("/api/setup")
def setup(db, data, user, token):
    return session_cookie(auth.register(db, data, token, owner=True), auth.SESSION_AGE)


@mutation("/api/signup")
def signup(db, data, user, token):
    return session_cookie(auth.register(db, data, token, owner=False), auth.SESSION_AGE)


@mutation("/api/login")
def login(db, data, user, token):
    return session_cookie(auth.login(db, data, token), auth.SESSION_AGE)


@mutation("/api/logout")
def logout(db, data, user, token):
    auth.logout(db, user, token)
    return session_cookie("", 0)


@mutation("/api/renew-invite")
def renew_invite(db, data, user, token):
    invitations.rotate(db, user)


@mutation("/api/role")
def role(db, data, user, token):
    users.change_role(db, user, data)
