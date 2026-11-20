# Household Chores

Household Chores is a shared calendar for one household. An owner can invite members and grant or revoke admin access. Admins can create, edit, delete, assign, unassign, and reassign chores. Members can claim an available occurrence and complete occurrences assigned to them. The server enforces assignment permissions.

Chores can repeat daily or on a chosen weekday starting on a specified date. Each occurrence has its own assignee and completion status. The default assignee applies to occurrences without an individual assignment change. A member claiming a chore claims that date only. The board shows one calendar week at a time and can jump to any date. Deleting a chore removes pending occurrences from the board and keeps completed occurrences visible.

## Run in VS Code or PyCharm

From the project root with Python 3.11 or newer, run these commands.

```sh
python -m pip install -r requirements.txt
python app.py
```

This starts Flask’s local development server with debug disabled. Open http://127.0.0.1:8000 and enter the owner setup key printed in the terminal. Create your owner account, then use **Invite family** to copy the signup link. To test another account locally, open it in a private browser window.

The local SQLite database is saved beside app.py. The server defaults to `America/New_York`. The dependencies include timezone data for Windows and the container.

## Run in Docker Desktop

From the project root, with Docker Desktop running:

```powershell
docker compose up --build -d --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/healthz
docker compose logs chores
```

Open http://127.0.0.1:8000. A fresh local database logs an owner setup key unless a hosted origin is configured. You can supply your own `CHORES_SETUP_KEY` through the environment or a private Compose `.env` file. The default port is published only on localhost. If the port is in use, set `CHORES_LOCAL_PORT` before starting and use the same port in the browser and probe command.

Waitress serves Flask and the static frontend in a single container as UID/GID 1000. The image uses Python slim, installs runtime dependencies only, and uses Python's standard library for the health check. `GET /healthz` checks whether the app can read the SQLite users table. It returns 200 when ready and 503 if that database read fails. It permits a local HTTP probe even in hosted mode. The remaining hosted routes still require HTTPS.

The `chores-data` volume mounts at `/data`, with SQLite at `/data/chores.sqlite3`. Keep the same Compose project name when upgrading or moving directories. Use `docker compose down` to stop and remove containers while retaining the named volume. Avoid `down --volumes` for real household data. For a pre-Alembic database, follow [MIGRATIONS.md](MIGRATIONS.md) before starting the new container. If you customize `DATABASE_URL`, keep your container SQLite file under the mounted `/data` directory.

Build without starting Compose using `docker build -t household-chores .`. To run that image directly with a named volume:

```powershell
docker run --rm -p 127.0.0.1:8000:8000 --mount type=volume,source=household-chores-data,target=/data household-chores
```

That standalone command uses a separate named volume from Compose.

## Host for your household

For a single-host deployment, use a persistent local volume. The image refuses to start with SQLite in Azure Container Apps. For the single-container Azure SQL configuration, import procedure, and staging checklist, see [AZURE-SQL.md](AZURE-SQL.md). Use one instance with a writable persistent volume mounted at /data. Route an HTTPS domain to the application's port, 8000 by default, through the host's HTTPS reverse proxy. Set CHORES_PUBLIC_URL to that HTTPS origin and CHORES_SETUP_KEY to a long random secret before starting the hosted app. You can produce a key with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Open the hosted URL and create the owner account. Copy the signup link from that hosted session.

Configure request rate limits for signup and login at your reverse proxy and back up the SQLite database regularly using SQLite's backup facility or a consistent volume snapshot. Keep the database and environment secrets out of source control. The localhost signup URL is for testing on the same computer.


## Frontend structure

- `frontend/index.html` is the page shell and loads the stylesheet and JavaScript entry point.
- `frontend/style.css` contains the existing responsive styles.
- `frontend/app.js` handles calendar and form rendering, browser state, and user actions.
- `frontend/api.js` exports `api(path, data)`. It makes same-origin JSON requests, uses GET without data and POST with data, and turns API errors into exceptions the UI can display.

The Python server serves the frontend at `/` with assets at `/style.css`, `/app.js`, and `/api.js`. Start the server using the commands above so module imports and session cookies use the same origin. No JavaScript build step is required. See [TESTING.md](TESTING.md) for the regression suite.

## Flask backend

- `backend/app.py` creates the Flask app, registers its routes, and initializes the database.
- `backend/config.py` defines environment settings and validates hosted configuration.
- `backend/routes/__init__.py` handles static assets, JSON parsing, response headers, cookie lookup, and the write transaction around each POST.
- `backend/routes/auth.py` handles setup, signup, login, logout, invitation rotation, and role updates.
- `backend/routes/chores.py` handles the board and chore, assignment, claim, and completion requests.
- `backend/services/auth.py` manages credentials and sessions. `invitations.py` manages setup and invite keys. `users.py` handles role changes and assignee validation.
- `backend/services/chores.py` manages chore definitions and assembles the board. `assignments.py` applies the rules for claiming, assigning, and completing occurrences. `schedule.py` calculates which occurrences appear in a week.
- `backend/services/authorization.py` enforces signed-in, admin, and owner permissions. `validation.py` holds shared field checks and application errors.
- `backend/database/__init__.py` owns SQLite connections and transactions. Table mappings are in `models.py` and the versioned schema is in `backend/migrations/`. `accounts.py` and `chores.py` contain queries and return SQLite rows.
- `backend/requirements.txt` lists runtime dependencies. The root `requirements.txt` delegates to it.
- `backend/wsgi.py` exports the WSGI callable `backend.wsgi:app`. Run `python -m backend.wsgi` to serve it with Waitress, as Docker Compose does.

| Environment variable | Default or purpose |
| --- | --- |
| `CHORES_DB` | `chores.sqlite3` beside the root `app.py`. The container uses `/data/chores.sqlite3`. |
| `CHORES_HOST` | `127.0.0.1` locally and `0.0.0.0` inside the container. |
| `PORT` | `8000`. Match the Compose port mapping if you change it in the container. |
| `CHORES_TIMEZONE` | `America/New_York`. |
| `CHORES_PUBLIC_URL` | Set to the external HTTPS origin for hosted use to enable secure session cookies. |
| `CHORES_SETUP_KEY` | Set through the environment before fresh hosted startup. Local startup can generate a key. |

A POST route parses JSON, opens an SQLite write transaction, and resolves the session. The service checks permissions and business rules, then calls the database functions using the same connection. Flask sends the existing JSON and cookie response after the transaction commits. The board reads saved occurrences and passes them to the scheduling functions for display.

The application factory disables Flask debug mode even if `FLASK_DEBUG` is set. The existing opaque session cookies are validated against SQLite. A Flask signing key is unnecessary for this session design.

See [MIGRATIONS.md](MIGRATIONS.md) for `DATABASE_URL`, backup instructions, the Alembic baseline, integrity checks, and rollback. Back up and apply the baseline before starting this release with an existing household database.

## Security and hosting

- New passwords use Werkzeug scrypt with N=131072, r=8, and p=1. A successful login upgrades the previous scrypt format automatically. Existing session tokens remain usable until their normal expiry or revocation. A successful login rotates the session for that browser, and logout revokes it in the database.
- Browser writes use JSON and send `X-Chores-Request: 1`. Use the same header in scripts calling POST endpoints. Cross-origin browser credentials and CORS are disabled by design.
- Invitations can be reused for multiple family members until they expire after seven days or an administrator replaces them. A preexisting link receives seven days from the first startup of this release. New links put the token in a URL fragment. Old query-string links work until their deadline. Avoid logging query strings or request bodies at the reverse proxy.
- Set `CHORES_PUBLIC_URL` to the public HTTPS origin. Hosted mode requires HTTPS, checks the host, and uses Secure cookies and HSTS. When Waitress sits behind a TLS-terminating reverse proxy, set `CHORES_TRUSTED_PROXY` to the immediate proxy's IP as seen by Waitress. The proxy should preserve the public Host, overwrite `X-Forwarded-Proto` with the actual scheme, and control access to the backend listener. Waitress trusts only that IP and header. If using another WSGI server, configure equivalent trusted proxy handling there.
- Keep rate limits on login, signup, and setup at the reverse proxy. Errors sent to clients contain a generic message for unexpected failures. Application error logs record the exception class without request bodies or exception details.
- Before downgrading to a release that only understands the old password format, back up the database. Accounts created or upgraded by this release use the new hash format. Their passwords require this release or a compatible release for sign-in.

## GitHub Actions

See [GITHUB-ACTIONS.md](GITHUB-ACTIONS.md) for CI checks, repository settings, troubleshooting, and the optional OIDC deployment workflow. Deployment is disabled by default.
