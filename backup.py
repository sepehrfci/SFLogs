"""Create and restore consistent SQLite snapshots for SFLogs."""

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("SFLOGS_DATABASE", BASE_DIR / "data" / "sflogs.sqlite3"))
BACKUP_DIR = Path(os.environ.get("SFLOGS_BACKUP_DIR", BASE_DIR / "backups"))


def check_database(path: Path) -> None:
    with sqlite3.connect(path) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed for {path}: {result}")


def copy_database(source: Path, destination: Path) -> None:
    source_db = sqlite3.connect(source, timeout=30)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db)
    finally:
        destination_db.close()
        source_db.close()


def create_backup(keep: int) -> Path:
    if not DATABASE.is_file():
        raise FileNotFoundError(f"Database not found: {DATABASE}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f"sflogs-{timestamp}.sqlite3"
    temporary = destination.with_suffix(".tmp")
    if temporary.exists():
        temporary.unlink()
    copy_database(DATABASE, temporary)
    check_database(temporary)
    temporary.replace(destination)
    snapshots = sorted(BACKUP_DIR.glob("sflogs-*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_snapshot in snapshots[max(keep, 1):]:
        old_snapshot.unlink()
    return destination


def restore_backup(source: Path) -> None:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Backup not found: {source}")
    if source == DATABASE.resolve():
        raise ValueError("Backup source and live database must be different files")
    check_database(source)
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATABASE.with_name(f".{DATABASE.name}.restore.tmp")
    if temporary.exists():
        temporary.unlink()
    copy_database(source, temporary)
    check_database(temporary)
    temporary.replace(DATABASE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up or restore the SFLogs SQLite database")
    parser.add_argument("--keep", type=int, default=14, help="number of recent snapshots to retain")
    parser.add_argument("--restore", type=Path, help="restore from this snapshot; stop the web service first")
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    if args.restore:
        restore_backup(args.restore)
        print(f"Restored SFLogs database from {args.restore}")
    else:
        print(f"Created SFLogs backup: {create_backup(args.keep)}")


if __name__ == "__main__":
    main()
