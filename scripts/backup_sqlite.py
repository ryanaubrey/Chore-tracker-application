"""Create a checked SQLite snapshot without overwriting an existing file."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def backup_database(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    # Reserve the name exclusively before sqlite3 opens it.
    destination.touch(exist_ok=False, mode=0o600)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(destination)) as copy:
                original.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise RuntimeError("SQLite backup integrity check failed.")
    except BaseException:
        destination.unlink()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    backup_database(arguments.source, arguments.destination)
    print(f"Verified SQLite backup: {arguments.destination}")
