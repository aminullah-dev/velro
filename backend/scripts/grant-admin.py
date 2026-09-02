"""Make a real phone number an administrator.

The seed creates one administrator, +93700000001, which exists so the tests
have somebody to be. The operator's own handset is a different number, and
until now there was no way to give it the keys short of writing SQL -- which
is exactly the kind of thing that gets done once, wrong, at midnight.

Creates the user if the number has never signed in, grants the role, and
says what it did. Refuses nothing quietly.

    PYTHONPATH=. .venv/bin/python scripts/grant-admin.py +13438677631
    PYTHONPATH=. .venv/bin/python scripts/grant-admin.py +93700000001 --revoke
    PYTHONPATH=. .venv/bin/python scripts/grant-admin.py +13438677631 --email me@example.org

--email puts an address on the account so the console can send its code
there instead of by SMS -- free, and reachable from anywhere the SIM is not.

The number still signs in the ordinary way, with an OTP. This grants
authority, never access.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from domain.identity import ADMIN, SUPER_ADMIN, PhoneNumber
from infrastructure.db.repositories.identity import UserRepository
from shared.ids import new_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phone", help="E.164 or local form; normalised the same way sign-in does")
    parser.add_argument("--revoke", action="store_true", help="take the role away instead")
    parser.add_argument(
        "--email", default=None,
        help="an inbox for the console's sign-in code; clears it when given as ''",
    )
    parser.add_argument(
        "--role", default=ADMIN, choices=(ADMIN, SUPER_ADMIN),
        help="SUPER_ADMIN also carries settings.manage -- the owner's own "
             "account, not an operator's",
    )
    args = parser.parse_args()

    phone = PhoneNumber.parse(args.phone)
    url = os.environ.get(
        "VELRO_DATABASE_URL",
        "postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev",
    )
    engine = create_engine(url)
    with Session(engine) as session:
        users = UserRepository(session)
        row = users.find_by_phone(phone.value)
        if row is None:
            if args.revoke:
                print(f"no account for {phone.value}; nothing to revoke")
                return 1
            row = users.create(id=new_id(), phone=phone.value, locale="fa-AF", full_name=None)
            print(f"created account for {phone.value}")

        if args.revoke:
            users.revoke_role(row.id, args.role)
            session.commit()
            print(f"{phone.value} no longer holds {args.role}")
            return 0

        users.grant_role(row.id, args.role)
        if args.email is not None:
            address = args.email.strip().lower()
            if address and ("@" not in address or " " in address):
                print(f"that does not look like an email address: {args.email!r}")
                return 1
            row.email = address or None
            row.version += 1
            session.add(row)
        session.commit()
        print(f"{phone.value} now holds {args.role} ({row.id})")
        if args.email is not None:
            print(f"console codes may go to {row.email or 'SMS only (address cleared)'}")
        print("Sign in as usual; the OTP is unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
