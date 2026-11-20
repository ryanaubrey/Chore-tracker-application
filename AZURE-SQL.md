# Azure SQL deployment readiness

SQLite remains the default for local Python and Docker Compose. Azure SQL is selected by setting `DATABASE_URL` to a SQL Server URL. This release prepares the code and image. It does not create cloud resources or transfer production data.

## Connection and image

- Install Microsoft ODBC Driver 18 on the machine running migration commands. Install Python dependencies with `python -m pip install -r backend/requirements-azure.txt`.
- Build the production image with `docker build -f Dockerfile.azure -t household-chores:azure .`. The default Dockerfile still builds the lightweight SQLite image. The Azure image installs Microsoft's ODBC package and runs Waitress as a non-root user.
- Supply `DATABASE_URL` from a secret. The shape is `mssql+pyodbc://USERNAME:PASSWORD@SERVER.database.windows.net:1433/DATABASE`. Percent-encode the username and password individually when they contain URL-reserved characters. Use the server DNS name and a named database. The application fixes Driver 18, encryption, and certificate verification, and rejects URL query overrides. SQL username/password auth is implemented. Managed identity is a future option.
- Set `CHORES_PUBLIC_URL` to the public HTTPS origin and verify ingress passes the public Host and trusted scheme to Waitress. Set `CHORES_TRUSTED_PROXY` only to the actual trusted next-hop IP. If the ingress cannot provide a stable, verifiable trust boundary, resolve this before deployment. Keep direct application ingress behind the trusted proxy. A fresh installation also needs a secret `CHORES_SETUP_KEY`.
- Use a database principal with default schema `dbo`. Run Alembic with a provisioning principal that can create the tables and write the version record. The application principal needs table CRUD and schema visibility for startup checks. Explicit identity insert during import requires ownership or ALTER permission on the identity tables, so use the provisioning principal for import and keep schema privileges out of the app credential.

## Rehearse and transfer

1. Back up the local SQLite database using `python scripts/backup_sqlite.py chores.sqlite3 chores.sqlite3.azure-backup`. For a rehearsal use a private copy. For actual cutover, stop writes before producing the final backup and keep the original intact.
2. Run offline validation with `python -m scripts.transfer_sqlite chores.sqlite3.azure-backup --check`. This checks SQLite integrity and foreign keys, required values, column widths, account ownership, recurring chore fields, dates, and completion flags. It prints only table counts.
3. When an explicitly authorized staging SQL Server database exists, set its secret connection URL and run `python -m alembic upgrade head`, then `python -m alembic current`. Do this before starting the application. A fresh household can skip import and initialize through the app after schema migration.
4. With the application still stopped, run `python -m scripts.transfer_sqlite chores.sqlite3.azure-backup --apply`. The importer requires empty app tables, keeps original account and chore IDs, copies password hashes byte-for-byte, and compares every value with the source inside the same transaction before committing. A mismatch aborts the transfer. The private backup is never included in the container image.
5. Start the app against the imported database and verify owner and member sign-in, roles, a recurring chore, a claimed occurrence, a completion, an invitation, and writes after import. Rotate the invitation so published links point to the hosted origin. **Sessions are deliberately excluded.** Everyone signs in again with their existing password.
6. For rollback before enabling production writes, stop the target app and point back to the preserved SQLite database. If writes have already occurred on SQL Server, pause writes and reconcile those changes before switching back. SQL Server rollback uses a database restore or a separate database. This baseline deliberately refuses a SQL Server Alembic downgrade.

## Before production

- [ ] Test a live, certificate-verified Azure SQL connection, firewall rules, and both database principals.
- [ ] Run the real SQL Server Alembic bootstrap and transfer on a disposable database. Verify identity values advance beyond imported IDs, Unicode round-trips, and one of two simultaneous claims loses without overwriting.
- [ ] Confirm probe routing, HTTPS termination, forwarded scheme handling, host checks, login, Secure cookies, invite links, and rate limits in staging.
- [ ] Confirm backup retention and run a recovery exercise. Establish a write freeze and reconciliation plan.
- [ ] Verify runtime behavior after transient network failures and database resume. Connection pre-ping is enabled. The application does not automatically retry writes.

SQL Server stores IDs and session expiration in BIGINT, uses bounded Unicode values, and keeps the same ISO calendar dates and composite occurrence key as SQLite. The SQL Server transaction takes a write lock before reading assignment state. This matches SQLite’s serialized write behavior for application traffic. Administrative scripts that write outside the application must use the same lock or run with the app stopped.
