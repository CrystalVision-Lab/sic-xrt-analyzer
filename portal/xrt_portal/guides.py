"""Private read-only screenshots. No dataset pixels or credentials enter the web build."""
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
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.directory:
            raise ValueError("GUIDE_IMAGE_PATH")
        raw = path.read_bytes() if path.stat().st_size <= 8 * 1024**2 else b""
        if len(raw) != record["size"] or hashlib.sha256(raw).hexdigest() != record["sha256"] or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("GUIDE_IMAGE_INTEGRITY")
        return raw
