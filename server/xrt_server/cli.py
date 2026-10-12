import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from .auth import issue
from .db import connect
from .models import User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    path = Path(args.output)
    if path.exists():
        raise SystemExit("Credential output already exists")
    _engine, sessions = connect()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sessions.begin() as s:
        if s.scalar(select(User).where(User.role == "ADMIN")):
            raise SystemExit("Admin exists; bootstrap disabled")
        user = User(id=str(uuid4()), name="Initial administrator", role="ADMIN")
        s.add(user)
        s.flush()
        client = str(uuid4())
        cred, token = issue(s, user.id, client)
        with path.open("x", encoding="utf-8") as out:
            json.dump(
                {
                    "user_id": user.id,
                    "client_id": client,
                    "credential_id": cred.id,
                    "credential": token,
                },
                out,
            )
        os.chmod(path, 0o600)
    print(
        "Administrator credential written to a private file; bootstrap is now disabled"
    )


if __name__ == "__main__":
    main()
