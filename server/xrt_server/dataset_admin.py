"""Explicit local export. Credential file contents are never printed."""

import argparse
import json
import os
from pathlib import Path

from .auth import authenticate
from .datasets import export_version, require_admin
from .db import connect
from .models import DatasetVersion


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credential-file", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    private = Path(args.credential_file)
    if private.is_symlink() or not private.is_file() or private.stat().st_size > 8192:
        raise ValueError("PRIVATE_CREDENTIAL_FILE_REQUIRED")
    credential = json.loads(private.read_text(encoding="utf-8"))["credential"]
    engine, sessions = connect()
    try:
        with sessions.begin() as s:
            user, _ = authenticate(s, "Bearer " + credential)
            require_admin(user)
            record = s.get(DatasetVersion, args.dataset_id)
            if not record:
                raise ValueError("DATASET_NOT_FOUND")
            result = export_version(
                s, user, record, os.getenv("XRT_ASSET_DIR", "/data/assets"), args.output
            )
        print(json.dumps(result, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
