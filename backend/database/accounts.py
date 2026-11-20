from sqlalchemy import delete, insert, literal, or_, select, update

from .models import sessions, settings, users


def has_users(db):
    return db.scalar(select(literal(1)).select_from(users).limit(1)) is not None


def find_user(db, username):
    return db.execute(select(users).where(users.c.username == username)).mappings().first()


def user_exists(db, user_id):
    return db.scalar(select(users.c.id).where(users.c.id == user_id)) is not None


def create_user(db, name, username, password, role):
    result = db.execute(insert(users).values(name=name, username=username,
                                             password=password, role=role))
    return result.inserted_primary_key[0]


def members(db):
    return db.execute(select(users.c.id, users.c.name, users.c.role)
                      .order_by(users.c.name)).mappings()


def set_role(db, user_id, role):
    db.execute(update(users).where(users.c.id == user_id, users.c.role != "owner")
               .values(role=role))


def get_setting(db, key):
    return db.scalar(select(settings.c.value).where(settings.c.key == key))


def set_setup_key(db, key):
    if get_setting(db, "setup") is None:
        db.execute(insert(settings).values(key="setup", value=key))
    else:
        db.execute(update(settings).where(settings.c.key == "setup").values(value=key))


def create_invitation(db, key):
    db.execute(delete(settings).where(settings.c.key == "setup"))
    db.execute(insert(settings).values(key="invite", value=key))


def update_invitation(db, key):
    db.execute(update(settings).where(settings.c.key == "invite").values(value=key))


def session_user(db, token, now):
    statement = (select(users.c.id, users.c.name, users.c.role)
                 .select_from(sessions.join(users))
                 .where(sessions.c.token == token, sessions.c.expires > now))
    return db.execute(statement).mappings().first()


def replace_session(db, previous, token, now, expires, user_id):
    db.execute(delete(sessions).where(or_(sessions.c.token == previous, sessions.c.expires <= now)))
    db.execute(insert(sessions).values(token=token, user_id=user_id, expires=expires))


def delete_session(db, token):
    db.execute(delete(sessions).where(sessions.c.token == token))


def update_password(db, user_id, password):
    db.execute(update(users).where(users.c.id == user_id).values(password=password))


def set_invite_expiry(db, value):
    if get_setting(db, "invite_expires") is None:
        db.execute(insert(settings).values(key="invite_expires", value=value))
    else:
        db.execute(update(settings).where(settings.c.key == "invite_expires").values(value=value))
