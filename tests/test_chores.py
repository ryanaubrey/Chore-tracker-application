from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest


DAY = "2026-01-01"


def user_id(client):
    return client.board()["user"]["id"]


def occurrence(client, chore, day=DAY):
    return next(
        item for item in client.board(day)["items"]
        if item["id"] == chore["id"] and item["day"] == day
    )


def promote(owner, client, role="admin"):
    owner.ok("/api/role", {"id": user_id(client), "role": role})


@pytest.mark.parametrize("path", ["save", "delete", "role", "renew-invite"])
def test_member_cannot_use_privileged_routes(join, path):
    member = join("member")
    status, payload, _ = member.request("/api/" + path, {})
    assert status == 403
    assert "error" in payload


def test_multiple_admins_and_owner_only_role_management(owner, join):
    first, second = join("first"), join("second")
    promote(owner, first)
    promote(owner, second)
    assert first.board()["user"]["role"] == second.board()["user"]["role"] == "admin"
    assert "chores" in first.board()
    assert first.request("/api/role", {"id": user_id(second), "role": "member"})[0] == 403
    promote(owner, first, "member")
    assert first.board()["user"]["role"] == "member"
    assert "chores" not in first.board()
    assert second.board()["user"]["role"] == "admin"


def test_claim_locks_member_assignment_and_admin_can_reassign(owner, join, create_chore):
    claimant, replacement, admin = join("claimant"), join("replacement"), join("admin")
    promote(owner, admin)
    chore = create_chore(frequency="daily")
    target = {"id": chore["id"], "day": DAY}
    claimant.ok("/api/claim", target)
    assert occurrence(owner, chore)["assignee"] == user_id(claimant)
    assert occurrence(owner, chore, "2026-01-02")["assignee"] is None
    for assignee in (None, user_id(replacement)):
        assert claimant.request("/api/assign", {**target, "assignee": assignee})[0] == 403
        assert occurrence(owner, chore)["assignee"] == user_id(claimant)
    assert replacement.request("/api/claim", target)[0] == 409
    admin.ok("/api/assign", {**target, "assignee": user_id(replacement)})
    assert occurrence(owner, chore)["assignee"] == user_id(replacement)
    assert claimant.request("/api/complete", target)[0] == 403
    replacement.ok("/api/complete", target)
    assert occurrence(owner, chore)["completed"] is True
    assert admin.request("/api/assign", {**target, "assignee": None})[0] == 409
    assert replacement.request("/api/complete", target)[0] == 409


def test_admin_chore_lifecycle_preserves_completed_history(owner, join):
    admin, member = join("admin"), join("member")
    promote(owner, admin)
    chore = {
        "title": "Before edit", "details": "Original", "frequency": "daily",
        "start": DAY, "assignee": user_id(member),
    }
    admin.ok("/api/save", chore)
    saved, = admin.board()["chores"]
    admin.ok("/api/save", {**chore, "id": saved["id"], "title": "After edit", "details": "Updated"})
    item = occurrence(member, saved)
    assert (item["title"], item["details"]) == ("After edit", "Updated")
    member.ok("/api/complete", {"id": saved["id"], "day": DAY})
    admin.ok("/api/delete", {"id": saved["id"]})
    assert admin.board()["chores"] == []
    history, = admin.board()["items"]
    assert (history["day"], history["completed"]) == (DAY, True)


def test_explicit_unassignment_overrides_default_assignee(owner, join, create_chore):
    member = join("member")
    chore = create_chore(frequency="daily", assignee=user_id(member))
    owner.ok("/api/assign", {"id": chore["id"], "day": DAY, "assignee": None})
    assert occurrence(member, chore)["assignee"] is None
    assert occurrence(member, chore, "2026-01-02")["assignee"] == user_id(member)


def test_concurrent_claim_persists_only_winning_assignment(owner, join, create_chore):
    first, second = join("first"), join("second")
    chore = create_chore()
    ids = [user_id(first), user_id(second)]
    barrier = Barrier(2)

    def claim(client):
        barrier.wait(timeout=5)
        return client.request("/api/claim", {"id": chore["id"], "day": DAY})[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (first, second)))
    assert sorted(results) == [200, 409]
    assert occurrence(owner, chore)["assignee"] == ids[results.index(200)]
