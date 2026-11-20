# SQLite migrations

This release uses SQLAlchemy Core and Alembic. Set `DATABASE_URL` to select the SQLite file. If it is unset, the existing `CHORES_DB` setting applies, followed by the default file beside `app.py`. The Docker default stays `/data/chores.sqlite3` in the existing named volume. Run commands from the project root.

A fresh database gets the first revision at startup. An existing household database without an Alembic revision requires the explicit procedure below. The first revision checks the legacy columns, keys, and SQLite integrity and records the baseline. The five application tables and their rows are kept in place. The existing unique username and composite occurrence key `(chore_id, day)` are retained. SQLite writes take a lock before reading the current assignment so competing claims cannot overwrite one another.

## Back up and apply the baseline

Stop the application first, including any Compose instance using the database. These PowerShell commands assume the default local path. For a custom file, set the path in both the backup command and the database configuration.

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = 'sqlite:///chores.sqlite3'
python scripts/backup_sqlite.py chores.sqlite3 chores.sqlite3.pre-alembic
python -m alembic upgrade head
python -m alembic current
```

The backup utility opens the source read-only, uses the SQLite backup API, checks the resulting file, and refuses to overwrite an existing backup. Keep the backup in a private location because it contains household records and credentials. For a rehearsal, back up the backup to a disposable working file and set `DATABASE_URL` to that file before upgrading.

For the default Compose volume, run the following with the same Compose project name used for your existing household data. Keep that volume across the upgrade.

```powershell
docker compose stop chores
docker compose build chores
docker compose run --rm --no-deps chores python scripts/backup_sqlite.py /data/chores.sqlite3 /data/chores.sqlite3.pre-alembic
docker compose run --rm --no-deps chores python -m alembic upgrade head
docker compose run --rm --no-deps chores python -m alembic current
docker compose up -d
```

Adjust both the backup source and the migration URL if your Compose configuration uses a different path. Keep a separate backup outside the volume for recovery.

## Verify integrity

Check that Alembic reports `0001_sqlite_baseline (head)`. Open the migrated file with SQLite and run:

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Expect `ok` from the first check and zero rows from the second. Compare row counts in `users`, `settings`, `sessions`, `chores`, and `occurrences` with the backup before starting the app. Then sign in with an existing account and confirm older assignments and completions on the calendar. The automated rehearsal tests compare every row in those five tables before and after the migration.

## Roll back safely

Stop the app first. For this baseline, the previous app can use the current SQLite file and retain writes made since the upgrade. If you also want to remove the Alembic revision record, run `python -m alembic downgrade base` before restarting the previous app. This revision leaves the household tables in place. Reapply `upgrade head` before starting the current app again.

If the database itself needs recovery, preserve the current database and its companion files. Copy the verified backup to a new SQLite file with the backup utility and point the app at that file. The restored copy reflects only the backup time. Reconcile any later household writes before switching over.

## Azure SQL

See [AZURE-SQL.md](AZURE-SQL.md) for SQL Server setup and the SQLite transfer procedure.
