from datetime import date

import pytest

from backend.database import accounts, connect, write_transaction
from backend.services import chores, invitations, users
from backend.services.schedule import week_days, week_items
from backend.services.validation import RequestError


@pytest.mark.parametrize("operation", [chores.save, chores.retire, users.change_role])
def test_service_checks_permissions_before_using_database(operation):
    with pytest.raises(RequestError) as error:
        operation(None, {"id": 2, "role": "member"}, {})
    assert error.value.args == (403, "Only admins can make this change.")


def test_invite_rotation_requires_admin_at_service_boundary():
    with pytest.raises(RequestError) as error:
        invitations.rotate(None, {"id": 2, "role": "member"})
    assert error.value.args == (403, "Only admins can make this change.")


def test_failed_write_rolls_back(app_context):
    with pytest.raises(RuntimeError, match="abort"):
        with write_transaction() as db:
            accounts.set_setup_key(db, "replacement")
            raise RuntimeError("abort")
    with connect() as db:
        assert accounts.get_setting(db, "setup") == "synthetic-owner-setup-key"


def test_week_projection_honors_explicit_unassignment_without_database():
    days = week_days(date(2026, 1, 1))
    assert (days[0], days[-1]) == ("2025-12-29", "2026-01-04")
    definition = {
        "id": 1, "start": "2026-01-01", "weekday": 0, "frequency": "daily",
        "assignee": 10, "title": "Bins", "details": "", "retired": 0,
    }
    override = {"chore_id": 1, "day": "2026-01-02", "assignee": None, "completed": 0}
    items = week_items(days, [definition], [override])
    assert [(item["day"], item["assignee"]) for item in items] == [
        ("2026-01-01", 10), ("2026-01-02", None),
        ("2026-01-03", 10), ("2026-01-04", 10),
    ]


def test_unknown_post_preserves_validation_and_role_order(clients, owner, join):
    assert clients().request("/api/unknown", {})[:2] == (401, {"error": "Sign in first."})
    assert join("member").request("/api/unknown", {})[:2] == (
        403, {"error": "Only admins can make this change."},
    )
    for url in ("/api/unknown", "/"):
        assert owner.request(url, {})[:2] == (404, {"error": "Action not found."})
