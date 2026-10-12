"""Explicit isolated synthetic ML→registry→real HTTP→install→rollback→backup QA.
Requires existing TD07 ML checkout/environment; writes only a NEW private QA folder.
Does not train on research data, publish production releases, or alter ML sources.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from server_ops import PRIVATE, ROOT

from sic_xrt_analyzer.model_updates.client import UpdateClient
from sic_xrt_analyzer.model_updates.contracts import canonical, file_sha, read_json
from sic_xrt_analyzer.model_updates.store import ModelStore
from sic_xrt_analyzer.model_updates.validation import validate_bundle

SEED = r"""
import json,sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,'/opt/xrt/server/tests')
from conftest import project
from test_datasets import clone_fixture,register,mapping,approval,post
from xrt_server.api import create_app
from xrt_server.db import connect
from xrt_server.models import User,DatasetVersion
from xrt_server.auth import issue,grant
from xrt_server.datasets import export_version
from fastapi.testclient import TestClient
root=Path('/qa');work=root/'generated';work.mkdir()
p=project.__wrapped__(work);e,sessions=connect()
u=User(id=str(uuid4()),name='TD110 QA researcher',role='RESEARCHER');a=User(id=str(uuid4()),name='TD110 QA ADMIN',role='ADMIN')
with sessions.begin() as s:
 s.add_all([u,a]);s.flush();client=str(uuid4());_,token=issue(s,u.id,client);ac=str(uuid4());_,admin=issue(s,a.id,ac)
(root/'admin.json').write_text(json.dumps({'credential':admin,'user_id':a.id,'client_id':ac}))
(root/'researcher.json').write_text(json.dumps({'credential':token,'user_id':u.id,'client_id':client}))
app=create_app(asset_dir='/data/assets');ids=[]
with TestClient(app) as http:
 api=(http,app,sessions,u,client,token,admin,'qa')
 for group in range(3):
  for i,k in enumerate(('BPD','TED','TSD')):
   value=clone_fixture(p,work,110000+group*3+i)
   with sessions.begin() as s:grant(s,u.id,value.project_id,True)
   asset=register(api,value);post(api,'/groups',mapping(value,group='synthetic-independent-'+str(group),wafer='8' if group==2 else str(group),evaluation=group==2))
   body=approval(value,asset);body['approved_class']=k;post(api,'/approvals',body);ids.append(value.project_id)
 d=post(api,'',{'version':'td110-functional-'+str(uuid4()),'project_ids':ids,'seed':2026})
 with sessions.begin() as s:export_version(s,s.get(User,a.id),s.get(DatasetVersion,d['dataset_id']),'/data/assets',root/'dataset')
(root/'seed.json').write_text(json.dumps({'dataset_id':d['dataset_id'],'dataset_hash':d['dataset_hash'],'synthetic_rows':len(d['rows'])}))
e.dispose();print('Nine synthetic approval fixtures exported to private QA; no production writes')
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--qa-only", action="store_true", required=True)
    p.add_argument("--ml-root", type=Path, required=True)
    p.add_argument("--ml-python", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError("New protected private QA path required")
    out.mkdir(parents=True)
    project = "xrt-restore-td110-qa-" + uuid4().hex[:6]
    restored = project + "-copy"
    registry = "qa-" + uuid4().hex
    env = {
        **os.environ,
        "XRT_MODEL_REALM": "INTERNAL_TEST",
        "XRT_MODEL_REGISTRY_ID": registry,
        "XRT_API_PORT": "18769",
    }
    log = (out / "operations.log").open("w", encoding="utf-8")

    def command(args, environment=env):
        result = subprocess.run(
            [str(x) for x in args],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        log.write(result.stdout)
        log.flush()
        if result.returncode:
            raise RuntimeError("QA command failed; inspect protected operations log")
        return result.stdout

    def ops(*args):
        return command([sys.executable, "tools/server_ops.py", *args])

    origin = "http://127.0.0.1:18769"

    def ready(url):
        for _ in range(60):
            try:
                if (
                    httpx.get(url + "/api/v1/models/releases", timeout=2).status_code
                    == 401
                ):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise TimeoutError("Isolated API not ready")

    ops("start", "--project", project)
    ready(origin)
    command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            project + "_default",
            "-e",
            "XRT_DB_PASSWORD_FILE=/run/secrets/db_password",
            "-e",
            "XRT_MODEL_REALM=INTERNAL_TEST",
            "-e",
            "XRT_MODEL_REGISTRY_ID=" + registry,
            "--mount",
            "type=bind,source="
            + str(PRIVATE / "db-password.txt")
            + ",target=/run/secrets/db_password,readonly",
            "-v",
            project + "_assets:/data/assets",
            "-v",
            str(out) + ":/qa",
            "xrt-research-testing",
            "python",
            "-c",
            SEED,
        ]
    )
    seed = read_json((out / "seed.json").read_bytes())
    ml_env = {
        **os.environ,
        "PYTHONPATH": str(a.ml_root.resolve() / "src"),
        "OMP_NUM_THREADS": "2",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    config = read_json((a.ml_root / "configs/patch-baseline.json").read_bytes())
    config["epochs"] = 1
    (out / "train-config.json").write_bytes(canonical(config))
    ml = [a.ml_python, "-m", "sic_xrt_ml"]
    command(
        [
            *ml,
            "train",
            out / "dataset",
            "--synthetic-smoke",
            "--config",
            out / "train-config.json",
            "--output",
            out / "run",
        ],
        ml_env,
    )
    command(
        [
            *ml,
            "evaluate",
            out / "dataset",
            "--synthetic-smoke",
            "--checkpoint",
            out / "run/checkpoint.pt",
            "--output",
            out / "evaluation",
            "--existing-bundle",
            ROOT / "artifacts/models/research",
        ],
        ml_env,
    )
    command(
        [
            *ml,
            "export",
            "--checkpoint",
            out / "run/checkpoint.pt",
            "--evaluation",
            out / "evaluation/evaluation.json",
            "--output",
            out / "candidate",
        ],
        ml_env,
    )
    candidate = out / "candidate"
    validation = validate_bundle(candidate)

    def admin(action, *args, input_path=None, output_path=None, key=None):
        values = [
            "model-admin",
            "--project",
            project,
            "--admin-credential",
            str(out / "admin.json"),
        ]
        if input_path:
            values += ["--input", str(input_path)]
        if output_path:
            values += ["--output", str(output_path)]
        if key:
            values += ["--signing-key", str(key)]
        result = ops(*values, "--model-command", action, *args)
        for line in reversed(result.splitlines()):
            if line.startswith("{"):
                return json.loads(line)
        return None

    c = admin(
        "register",
        "--bundle",
        "/input",
        "--model-id",
        "td110-ml-functional",
        "--version",
        "0.1.0",
        "--dataset-id",
        seed["dataset_id"],
        input_path=candidate,
    )
    admin_token = read_json((out / "admin.json").read_bytes())["credential"]
    user_token = read_json((out / "researcher.json").read_bytes())["credential"]
    headers = {"Authorization": "Bearer " + admin_token}
    with httpx.Client(
        base_url=origin, headers=headers, trust_env=False, follow_redirects=False
    ) as http:
        response = http.post(
            "/api/v1/admin/models/approvals",
            json={
                "candidate_id": c["candidate_id"],
                "channel": "STABLE",
                "reason": "Synthetic must never be stable",
                "previous_event_id": c["event_id"],
            },
        )
        assert response.status_code == 409
        response = http.post(
            "/api/v1/admin/models/approvals",
            json={
                "candidate_id": c["candidate_id"],
                "channel": "INTERNAL_TEST",
                "reason": "Isolated synthetic updater acceptance only",
                "previous_event_id": c["event_id"],
            },
        )
        assert response.status_code == 200, response.status_code
        assert (
            httpx.get(
                origin + "/api/v1/models/releases?channel=INTERNAL_TEST",
                headers={"Authorization": "Bearer " + user_token},
            ).status_code
            == 403
        )
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    key_id = "td110-qa-key"
    (out / "private.key").write_bytes(raw)
    (out / "private.key").chmod(0o600)
    public = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    (out / "public.json").write_bytes(
        canonical({"key_id": key_id, "public_key": public})
    )
    admin("key-register", "--public-key-file", "/input/public.json", input_path=out)
    admin(
        "prepare",
        "--candidate-id",
        c["candidate_id"],
        "--channel",
        "INTERNAL_TEST",
        "--key-id",
        key_id,
        "--reason",
        "TD110 synthetic end to end only",
        "--output",
        "/operation/prepared.json",
        output_path=out / "prepared",
    )
    admin(
        "sign",
        "--metadata",
        "/input/prepared.json",
        "--key-file",
        "/signing/private.key",
        "--output",
        "/operation/release.json",
        input_path=out / "prepared",
        output_path=out / "signed",
        key=out / "private.key",
    )
    published = admin(
        "publish", "--metadata", "/input/release.json", input_path=out / "signed"
    )
    rid = published["release_id"]
    trust = {
        "schema": "xrt_release_trust/v1",
        "origins": {
            origin: {
                "registry_id": registry,
                "keys": {key_id: {"status": "TRUSTED", "public_key": public}},
            }
        },
    }
    store = ModelStore(out / "desktop-models")
    client = UpdateClient(origin, admin_token)
    try:
        rows = client.listing("INTERNAL_TEST")
        assert len(rows) == 1 and rows[0]["status"] == "AVAILABLE"
        record = store.install(client, rows[0]["release"], trust, "INTERNAL_TEST")
    finally:
        client.close()
    from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter

    adapter = DesktopResearchAdapter(store.verify_installed(record, trust))
    assert adapter.model_version == validation["model_sha256"]
    baseline = ROOT / "artifacts/models/research"
    previous = {
        "legacy_bundle": str(baseline),
        "model_hash": file_sha(baseline / "model.onnx"),
    }
    store.activate(record, previous)
    store.activate(store.rollback_record())
    assert store.verify_installed(store.state()["current"], trust) == baseline
    ops("backup", "--project", project, "--output", str(out / "backup"))
    ops("stop", "--project", project)
    ops("start", "--project", project)
    ready(origin)
    client = UpdateClient(origin, admin_token)
    try:
        assert client.status(rid)["status"] == "AVAILABLE"
    finally:
        client.close()
    ops(
        "restore",
        "--project",
        restored,
        "--backup",
        str(out / "backup"),
        "--port",
        "18771",
    )
    ready("http://127.0.0.1:18771")
    restored_trust = {
        "schema": "xrt_release_trust/v1",
        "origins": {"http://127.0.0.1:18771": trust["origins"][origin]},
    }
    client = UpdateClient("http://127.0.0.1:18771", admin_token)
    try:
        envelope = client.listing("INTERNAL_TEST")[0]["release"]
        assert envelope["metadata"]["release_id"] == rid
        copied = ModelStore(out / "restored-desktop")
        copied_record = copied.install(
            client, envelope, restored_trust, "INTERNAL_TEST"
        )
        assert (
            file_sha(
                copied.verify_installed(copied_record, restored_trust) / "model.onnx"
            )
            == validation["model_sha256"]
        )
    finally:
        client.close()
    report = {
        "status": "PASS",
        "synthetic_only": True,
        "dataset_hash": seed["dataset_hash"],
        "dataset_samples": 9,
        "model_sha256": validation["model_sha256"],
        "manifest_sha256": file_sha(candidate / "manifest.json"),
        "validation": validation,
        "candidate_id": c["candidate_id"],
        "release_id": rid,
        "qa_stack": project,
        "restore_stack": restored,
        "production_stable_created": 0,
        "ml_sources_modified": False,
        "real_http_install": True,
        "cpu_model_load": True,
        "local_rollback": True,
        "server_restart": True,
        "backup_restore": True,
        "private_signing_key_backed_up": False,
    }
    (out / "report.json").write_bytes(canonical(report))
    (ROOT / "artifacts/td110-ml-e2e.json").write_bytes(canonical(report))
    ops("stop", "--project", restored)
    ops("stop", "--project", project)
    log.close()
    print(
        "Isolated synthetic ML/registry/sign/HTTP/install/rollback/restart/backup/restore PASS"
    )


if __name__ == "__main__":
    main()
