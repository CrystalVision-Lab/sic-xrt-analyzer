"""Local administrator provisioning. Passwords enter via a hidden prompt or stdin."""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import httpx

from .passwords import username
from .store import Store


def provision(store, client, name, password, config):
    name = username(name)
    credential = config["credential"]
    headers = {"Authorization": "Bearer " + credential}
    health = client.get("/api/v1/health", headers=headers)
    admin = client.get("/api/v1/admin/openapi", headers=headers)
    if health.status_code != 200 or admin.status_code != 200:
        raise ValueError("ACTIVE_ADMIN_CREDENTIAL_REQUIRED")
    identity = health.json()
    if identity.get("client_id") != config.get("client_id") or not identity.get("user_id"):
        raise ValueError("ADMIN_IDENTITY_MISMATCH")
    user = {"id": identity["user_id"], "client_id": identity["client_id"], "role": "ADMIN"}
    store.set_admin_login(name, password, credential, user)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--credential", type=Path, required=True)
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    password = sys.stdin.readline(1025).removesuffix("\n").removesuffix("\r") if args.password_stdin else getpass.getpass("New administrator password: ")
    try:
        config = json.loads(args.credential.read_text(encoding="utf-8"))
        store = Store(
            os.getenv("XRT_PORTAL_STATE", "/data/state"),
            os.getenv("XRT_DOWNLOAD_DIR", "/data/releases"),
            Path(os.getenv("XRT_PORTAL_KEY_FILE", "/run/secrets/portal_key")).read_bytes().strip(),
        )
        with httpx.Client(base_url=os.getenv("XRT_RESEARCH_API", "http://api:8000"),
                          timeout=20, follow_redirects=False) as client:
            provision(store, client, args.username, password, config)
    except (ValueError, KeyError, OSError, httpx.HTTPError):
        # Neither submitted values nor upstream response bodies belong in logs.
        parser.exit(1, "Administrator login setup failed; check identity, password length and API availability.\n")
    print(json.dumps({"username": username(args.username), "status": "CONFIGURED",
                      "previous_password_sessions": "INVALIDATED"}))


if __name__ == "__main__":
    main()
