"""Read-only operating DB preservation snapshot; never exports rows or credentials."""

import argparse
import json
from pathlib import Path

from server_ops import compose

SCRIPT = r"""import hashlib,json
from sqlalchemy import inspect,text
from xrt_server.db import connect
e,_=connect();result={}
with e.connect() as c:
 for name in sorted(inspect(e).get_table_names()):
  if name in ('audit_events','alembic_version'):continue
  rows=[json.dumps(r[0],sort_keys=True,separators=(',',':'),default=str) for r in c.execute(text('SELECT to_jsonb(t) FROM "'+name+'" t'))]
  result[name]={'count':len(rows),'sha256':hashlib.sha256(('\n'.join(sorted(rows))).encode()).hexdigest()}
 print(json.dumps(result,sort_keys=True))
e.dispose()
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", default="xrt-research")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--before", type=Path)
    a = p.parse_args()
    data = json.loads(
        compose(
            a.project,
            ["exec", "-T", "api", "python", "-c", SCRIPT],
            capture_output=True,
            text=True,
        ).stdout
    )
    if a.before:
        before = json.loads(a.before.read_text(encoding="utf-8"))["tables"]
        assert all(data.get(k) == v for k, v in before.items()), (
            "Operating table changed"
        )
        assert all(
            data[k]["count"] == 0
            for k in ("model_candidates", "model_events", "model_releases")
        ), "Production QA model forbidden"
    a.output.write_text(
        json.dumps({"status": "PASS", "tables": data}, indent=2), encoding="utf-8"
    )
    print("Operating table hash preservation PASS; table count", len(data))


if __name__ == "__main__":
    main()
