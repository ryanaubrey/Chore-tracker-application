import pytest


@pytest.mark.parametrize(
    ("frequency", "start", "weekday", "anchor", "week_start", "expected"),
    [
        ("daily", "2025-12-31", 0, "2026-01-01", "2025-12-29",
         ["2025-12-31", "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
        ("daily", "2024-02-28", 0, "2024-03-01", "2024-02-26",
         ["2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02", "2024-03-03"]),
        ("weekly", "2025-12-30", 0, "2026-01-01", "2025-12-29", []),
        ("weekly", "2025-12-30", 0, "2026-01-05", "2026-01-05", ["2026-01-05"]),
        ("weekly", "2025-12-28", 6, "2026-01-04", "2025-12-29", ["2026-01-04"]),
        ("weekly", "2024-02-28", 3, "2024-02-29", "2024-02-26", ["2024-02-29"]),
        ("once", "2026-01-01", 0, "2026-01-01", "2025-12-29", ["2026-01-01"]),
        ("once", "2026-01-01", 0, "2026-01-05", "2026-01-05", []),
    ],
)
def test_schedule_at_calendar_boundaries(owner, create_chore, frequency, start, weekday,
                                         anchor, week_start, expected):
    chore = create_chore(frequency=frequency, start=start, weekday=weekday)
    board = owner.board(anchor)
    assert len(board["days"]) == 7
    assert board["days"][0] == week_start
    assert [item["day"] for item in board["items"] if item["id"] == chore["id"]] == expected


@pytest.mark.parametrize("day", ["2026-02-29", "1900-12-31", "9999-01-01"])
def test_invalid_or_out_of_range_board_dates(owner, day):
    status, body, _ = owner.request("/api/board?day=" + day)
    assert status == 400
    assert "error" in body


def test_saved_occurrence_survives_recurrence_edit(owner, join, create_chore):
    member = join("member")
    chore = create_chore(frequency="daily")
    member.ok("/api/claim", {"id": chore["id"], "day": "2026-01-02"})
    owner.ok("/api/save", {**chore, "frequency": "once", "start": "2026-01-01"})
    assert [item["day"] for item in owner.board()["items"]] == ["2026-01-01", "2026-01-02"]
