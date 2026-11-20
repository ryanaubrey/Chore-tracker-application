from contextlib import closing
from urllib.parse import parse_qs

from flask import request

from ..database import connect
from ..services import auth, chores
from ..services.assignments import change_occurrence
from . import json_response, mutation, session_token, web


@web.get("/api/board")
def board():
    query = parse_qs(request.query_string.decode("latin-1"))
    with closing(connect()) as db:
        return json_response(chores.board(db, auth.current_user(db, session_token()), query))


@mutation("/api/save")
def save(db, data, user, token):
    chores.save(db, user, data)


@mutation("/api/delete")
def retire(db, data, user, token):
    chores.retire(db, user, data)


@mutation("/api/assign")
def assign(db, data, user, token):
    change_occurrence(db, user, data, "assign")


@mutation("/api/claim")
def claim(db, data, user, token):
    change_occurrence(db, user, data, "claim")


@mutation("/api/complete")
def complete(db, data, user, token):
    change_occurrence(db, user, data, "complete")
