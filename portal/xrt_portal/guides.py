"""Read-only screenshots with explicit publication snapshots. No pixels enter the web build."""

import hashlib
import json
import re
from pathlib import Path
from uuid import UUID


class Guides:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def manifest(self):
        path = self.directory / "manifest.json"
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 512 * 1024:
            return {"schema": "xrt_research_guide/v1", "groups": [], "images": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != "xrt_research_guide/v1":
            raise ValueError("GUIDE_SCHEMA")
        for group in data["groups"]:
            UUID(group["project_id"])
            if not re.fullmatch(r"[a-z0-9-]{1,80}", group["id"]):
                raise ValueError("GUIDE_ID")
            for tab in group["tabs"]:
                if tab.get("image_id") and tab["image_id"] not in data["images"]:
                    raise ValueError("GUIDE_IMAGE_MISSING")
        return data

    def image(self, ident, data):
        if not re.fullmatch(r"[a-z0-9-]{1,80}", ident):
            raise KeyError(ident)
        record = data["images"][ident]
        name = record["filename"]
        if not re.fullmatch(r"[a-z0-9-]{1,80}\.png", name):
            raise ValueError("GUIDE_IMAGE_NAME")
        path = self.directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.resolve().parent != self.directory
        ):
            raise ValueError("GUIDE_IMAGE_PATH")
        raw = path.read_bytes() if path.stat().st_size <= 8 * 1024**2 else b""
        if (
            len(raw) != record["size"]
            or hashlib.sha256(raw).hexdigest() != record["sha256"]
            or not raw.startswith(b"\x89PNG\r\n\x1a\n")
        ):
            raise ValueError("GUIDE_IMAGE_INTEGRITY")
        return raw

    def published_groups(self, data):
        """Only individually approved tabs and image digests may be public.

        New captures remain private until an operator publishes a new snapshot.
        Never return private project UUIDs, file paths or the image inventory.
        """
        approved = {
            (r.get("group_id"), r.get("tab_id")): r for r in data.get("public_tabs", [])
        }
        groups = []
        for group in data["groups"]:
            tabs = []
            for tab in group["tabs"]:
                record = approved.get((group["id"], tab["id"]))
                if record is None or record.get("image_id") != tab.get("image_id"):
                    continue
                ident = tab.get("image_id")
                if ident and data["images"][ident]["sha256"] != record.get("sha256"):
                    continue
                tabs.append(
                    {
                        k: tab[k]
                        for k in (
                            "id",
                            "title",
                            "summary",
                            "image_id",
                            "steps",
                            "notes",
                            "callouts",
                        )
                        if k in tab
                    }
                )
            if tabs:
                groups.append(
                    {
                        **{
                            k: group[k]
                            for k in ("id", "title", "subtitle")
                            if k in group
                        },
                        "tabs": tabs,
                    }
                )
        return groups
