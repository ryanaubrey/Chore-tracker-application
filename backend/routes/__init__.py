import json
from functools import wraps
from http.cookies import SimpleCookie

from sqlalchemy.exc import SQLAlchemyError

from flask import Blueprint, Response, current_app, request
from werkzeug.exceptions import HTTPException

from ..config import ROOT
from ..database import connect, write_transaction
from ..database.accounts import has_users
from ..services import auth as authentication
from ..services.authorization import require_admin
from ..services.validation import RequestError, require


web = Blueprint("chores", __name__)
FRONTEND = ROOT / "frontend"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript"),
    "/api.js": ("api.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
}


@web.before_app_request
def require_hosted_https():
    if (current_app.config["CHORES_PUBLIC_URL"] and not request.is_secure
            and request.endpoint != "chores.health"):
        return json_response({"error": "HTTPS is required."}, 400)


@web.after_app_request
def add_response_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if current_app.config["CHORES_PUBLIC_URL"] and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


def json_response(result, status=200, cookie=None):
    response = Response(json.dumps(result), status=status, mimetype="application/json")
    if cookie:
        response.headers["Set-Cookie"] = cookie
    return response


@web.errorhandler(RequestError)
def request_error(error):
    status, message = error.args
    return json_response({"error": message}, status)


def asset():
    filename, content_type = ASSETS[request.path]
    return Response((FRONTEND / filename).read_bytes(), content_type=content_type)


def session_token():
    cookie = SimpleCookie(request.headers.get("Cookie", "")).get("chores_session")
    return authentication.token_hash(cookie.value) if cookie else ""


@web.app_errorhandler(Exception)
def unexpected_error(error):
    if isinstance(error, HTTPException):
        return json_response({"error": error.name}, error.code)
    current_app.logger.error("Unhandled request error (%s)", type(error).__name__)
    return json_response({"error": "Something went wrong."}, 500)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Invalid request.")
        result[key] = value
    return result


def reject_constant(value):
    raise RequestError(400, "Invalid request.")


def check_csrf():
    expected = current_app.config["CHORES_PUBLIC_URL"] or request.host_url.rstrip("/")
    origin = request.headers.get("Origin")
    require(request.headers.get("X-Chores-Request") == "1"
            and request.headers.get("Sec-Fetch-Site") not in {"cross-site", "same-site"}
            and (origin is None or origin == expected),
            "Request could not be verified. Refresh this page and try again.", 403)



def mutation(url):
    def register(action):
        @web.post(url)
        @wraps(action)
        def endpoint(**_):
            require(request.mimetype == "application/json", "Expected JSON.", 415)
            require(0 < (request.content_length or 0) <= 16384, "Invalid request size.")
            try:
                data = json.loads(request.get_data().decode("utf-8"),
                                  object_pairs_hook=unique_object, parse_constant=reject_constant)
            except (ValueError, RecursionError):
                raise RequestError(400, "Invalid request.") from None
            require(isinstance(data, dict), "Invalid request.")
            check_csrf()
            token = session_token()
            with write_transaction() as db:
                user = authentication.current_user(db, token)
                cookie = action(db, data, user, token)
            return json_response({}, cookie=cookie)
        return endpoint
    return register


for url in ASSETS:
    web.add_url_rule(url, view_func=asset, methods=["GET"])


@web.get("/healthz")
def health():
    try:
        with connect() as db:
            has_users(db)
    except SQLAlchemyError:
        return json_response({"status": "unavailable"}, 503)
    return json_response({"status": "ok"})


@web.get("/<path:unmatched>")
def page_not_found(unmatched):
    return json_response({"error": "Page not found."}, 404)


def unknown_mutation(db, data, user, token):
    require_admin(user)
    raise RequestError(404, "Action not found.")

unknown_endpoint = mutation("/<path:unmatched>")(unknown_mutation)
web.add_url_rule("/", view_func=unknown_endpoint, methods=["POST"])

from . import auth, chores
