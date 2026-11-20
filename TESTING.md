# Testing Household Chores

From the project root, with Python 3.11 or newer, run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-test.txt
.\.venv\Scripts\python -m pytest -ra
```

On macOS or Linux use `.venv/bin/python` in the last two commands.
To rerun just the claim race, append
`tests/test_chores.py -k concurrent_claim` to the pytest command.

Each test starts a threaded Flask server on an ephemeral loopback port
and initializes a fresh SQLite file under pytest's temporary directory.
Accounts and setup credentials are synthetic. The application clock is fixed
for repeatable calendar assertions. Docker and Azure are unnecessary. The suite includes frontend asset, request validation, and debug configuration checks.

## Behavior to review separately

- Invite rotation is shown only to the owner in the browser, but the backend
  accepts it from admins. The current authority is recorded in the tests.
  A product decision is needed before changing either side.
- Moving a recurring chore can leave previously saved dates visible. The
  suite records that behavior so a migration cannot erase those selections.
- Retired chores retain completed occurrences. The app displays historical
  entries using the current chore definition's title and instructions.

- Assignment requests validate the chore and occurrence before checking
  administrator permission. An empty request returns 400. A valid request
  from the member who claimed the chore returns 403.

## Coverage limits

The suite exercises backend HTTP requests, the cookie jar, and SQLite.
The secure-cookie assertion checks the header emitted in hosted mode.
Browser rendering, real HTTPS, Docker, Azure SQL, and timezone/DST conversion
are outside this suite. The race test covers two clients on one server.
No line coverage percentage is collected.
