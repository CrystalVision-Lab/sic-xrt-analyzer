"""Local artifact registration only; administrator credential never printed."""

import argparse
import json
import os
from pathlib import Path

import httpx

from .store import Store


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path)
    p.add_argument("--backup", type=Path)
    p.add_argument("--file", type=Path)
    p.add_argument("--source-file", type=Path)
    p.add_argument("--credential", type=Path)
    args = p.parse_args()
    if args.backup:
        store = Store(
            os.getenv("XRT_PORTAL_STATE", "/data/state"),
            os.getenv("XRT_DOWNLOAD_DIR", "/data/releases"),
            Path(os.getenv("XRT_PORTAL_KEY_FILE", "/run/secrets/portal_key"))
            .read_bytes()
            .strip(),
        )
        print(json.dumps(store.backup(args.backup)))
        return
    if not all((args.manifest, args.file, args.credential)):
        p.error("registration requires --manifest, --file, --credential")
    credential = json.loads(args.credential.read_text(encoding="utf-8"))["credential"]
    with httpx.Client(
        base_url=os.getenv("XRT_RESEARCH_API", "http://api:8000"),
        timeout=20,
        follow_redirects=False,
    ) as client:
        h = client.get(
            "/api/v1/health", headers={"Authorization": "Bearer " + credential}
        )
        h.raise_for_status()
        r = client.get(
            "/api/v1/admin/statistics",
            headers={"Authorization": "Bearer " + credential},
        )
        r.raise_for_status()
    store = Store(
        os.getenv("XRT_PORTAL_STATE", "/data/state"),
        os.getenv("XRT_DOWNLOAD_DIR", "/data/releases"),
        Path(os.getenv("XRT_PORTAL_KEY_FILE", "/run/secrets/portal_key"))
        .read_bytes()
        .strip(),
    )
    ident = store.register(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        args.file,
        h.json()["user_id"],
        args.source_file,
    )
    print(json.dumps({"release_id": ident, "status": "DRAFT", "sha_verified": True}))


if __name__ == "__main__":
    main()
