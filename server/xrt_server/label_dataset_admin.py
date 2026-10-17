"""Explicit local export of verified_xrt_dataset/v2. Credential file contents are never printed."""

import argparse
import json
from pathlib import Path

from .auth import authenticate
from .datasets import require_admin
from .db import connect
from .label_datasets import export_version
from .models import LabelDatasetVersion


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
            record = s.get(LabelDatasetVersion, args.dataset_id)
            if not record:
                raise ValueError("DATASET_NOT_FOUND")
            result = export_version(s, user, record, args.output)
        print(json.dumps(result, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
