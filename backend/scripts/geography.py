"""Move the geography between a database and the repository.

    PYTHONPATH=. .venv/bin/python scripts/geography.py export
    PYTHONPATH=. .venv/bin/python scripts/geography.py import
    PYTHONPATH=. .venv/bin/python scripts/geography.py import --dry-run

Export after a placing session and commit the file. Import into any other
database -- a fresh laptop, a colleague's clone, the server -- and the
villages, their stations and every placed coordinate arrive together.

The file is the master copy. A database is a cache of it.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrastructure import geo_coordinates as coords


def _engine():
    return create_engine(os.environ.get(
        "VELRO_DATABASE_URL",
        "postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev",
    ))


def do_export() -> int:
    with Session(_engine()) as session:
        places = coords.gather(session)
    if not places:
        print("this database has no geography to export")
        return 1
    path = coords.write(places)
    villages = [p for p in places if p.kind == "village"]
    placed = sum(1 for p in villages if p.latitude is not None)
    print(f"wrote {path}")
    print(f"  {len(villages)} villages ({placed} placed), "
          f"{len(places) - len(villages)} stations")
    print("  commit it: this file is the only copy of that work")
    return 0


def do_import(dry_run: bool) -> int:
    points = coords.read()
    if not points:
        print(f"no {coords.FILE.name}; nothing to import")
        return 1
    with Session(_engine()) as session:
        applied = coords.apply(session, points)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    print(("would apply: " if dry_run else "applied: ") + applied.summary())
    for code, why in applied.skipped[:10]:
        print(f"  skipped {code}: {why}")
    if len(applied.skipped) > 10:
        print(f"  ... and {len(applied.skipped) - 10} more")
    return 0


def do_check() -> int:
    """Has anyone placed a village and forgotten to export it?

    The failure this guards against is quiet: an afternoon of placing lives
    in one database, the file still says what it said yesterday, and nobody
    notices until the laptop does not start.
    """
    on_file = {(p.kind, p.code): p for p in coords.read()}
    with Session(_engine()) as session:
        live = {(p.kind, p.code): p for p in coords.gather(session)}

    missing = [k for k in on_file if k not in live]
    unexported = [k for k in live if k not in on_file]
    moved = [
        k for k, p in live.items()
        if k in on_file and p.latitude is not None
        and (on_file[k].latitude is None or p.latitude != on_file[k].latitude)
    ]
    if not (missing or unexported or moved):
        placed = sum(1 for p in on_file.values() if p.latitude is not None)
        print(f"in step: {len(on_file)} rows, {placed} placed")
        return 0

    if unexported:
        print(f"{len(unexported)} rows in the database are not in the file")
    if moved:
        print(f"{len(moved)} coordinates have changed since the last export")
        for kind, code in moved[:8]:
            print(f"   {code}: {on_file[(kind, code)].latitude} -> {live[(kind, code)].latitude}")
    if missing:
        print(f"{len(missing)} rows in the file are missing from the database")
    print("run: scripts/geography.py export   (and commit the file)")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "import", "check"))
    parser.add_argument("--dry-run", action="store_true",
                        help="import only: say what would change and change nothing")
    args = parser.parse_args()
    if args.action == "export":
        return do_export()
    if args.action == "check":
        return do_check()
    return do_import(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
