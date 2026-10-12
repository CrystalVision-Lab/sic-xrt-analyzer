"""Authenticated one-shot registry operations; private signing is offline and separate."""

import argparse
import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from sic_xrt_analyzer.model_updates.contracts import (
    canonical,
    read_json,
    safe_path,
    sign_release,
)
from sic_xrt_analyzer.model_updates.validation import validate_bundle

from .auth import audit, authenticate
from .datasets import require_admin
from .db import connect
from .model_registry import (
    BASELINE_SHA,
    approve_model,
    check_files,
    config,
    event,
    head,
    lookup,
    prepare_release,
    publish,
    register,
    register_key,
    scientific_gate,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "action",
        choices=[
            "list",
            "audit",
            "statistics",
            "register",
            "gate",
            "approve",
            "prepare",
            "sign",
            "publish",
            "revoke",
            "key-create",
            "key-register",
            "key-revoke",
            "beta-grant",
            "beta-revoke",
            "measure",
        ],
    )
    for name in (
        "credential-file",
        "bundle",
        "model-id",
        "version",
        "dataset-id",
        "candidate-id",
        "channel",
        "key-id",
        "key-file",
        "public-key-file",
        "metadata",
        "output",
        "reason",
        "previous-event-id",
        "release-id",
        "user-id",
        "baseline-bundle",
    ):
        p.add_argument("--" + name)
    a = p.parse_args()
    if a.action == "key-create":
        key = Ed25519PrivateKey.generate()
        path = safe_path(a.output)
        path.mkdir(mode=0o700)
        (path / "private.key").write_bytes(
            key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        )
        (path / "private.key").chmod(0o600)
        (path / "public.json").write_bytes(
            canonical(
                {
                    "key_id": a.key_id,
                    "public_key": base64.b64encode(
                        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                    ).decode(),
                }
            )
        )
        print("Private key created; protect OS ACL; contents are not printed")
        return
    if a.action == "sign":
        raw = safe_path(a.key_file).read_bytes()
        if len(raw) != 32:
            raise ValueError("PRIVATE_KEY_FORMAT")
        metadata = read_json(safe_path(a.metadata).read_bytes())
        envelope = sign_release(metadata, raw)
        with safe_path(a.output).open("xb") as f:
            f.write(canonical(envelope))
        print("Offline signing completed; key never sent to API")
        return
    credential = read_json(safe_path(a.credential_file).read_bytes())["credential"]
    engine, sessions = connect()
    cfg = config()
    try:
        with sessions.begin() as s:
            user, _ = authenticate(s, "Bearer " + credential)
            require_admin(user)
            c = lookup(s, a.candidate_id, cfg) if a.candidate_id else None
            if a.action in ("list", "audit", "statistics"):
                from sqlalchemy import select

                from .models import ModelCandidate, ModelEvent, ModelRelease

                candidates = s.scalars(
                    select(ModelCandidate)
                    .where(ModelCandidate.realm == cfg["realm"])
                    .limit(1000)
                ).all()
                if a.action == "audit":
                    result = [
                        {
                            "event_id": e.id,
                            "subject": e.subject_id,
                            "revision": e.revision,
                            "actor": e.actor_id,
                            "payload": e.payload,
                        }
                        for e in s.scalars(
                            select(ModelEvent)
                            .order_by(ModelEvent.created_at.desc())
                            .limit(1000)
                        )
                    ]
                elif a.action == "list":
                    result = [
                        {
                            "candidate_id": c.id,
                            "model_id": c.model_id,
                            "version": c.version,
                            "event_id": head(s, c.id).id,
                            "state": head(s, c.id).payload,
                        }
                        for c in candidates
                    ]
                else:
                    result = {
                        "candidates": len(candidates),
                        "approved": sum(
                            head(s, c.id).payload["action"] == "APPROVED"
                            for c in candidates
                        ),
                        "releases": len(s.scalars(select(ModelRelease)).all()),
                    }
            elif a.action == "register":
                c = register(
                    s, user, a.bundle, a.model_id, a.version, a.dataset_id, cfg
                )
                result = {"candidate_id": c.id, "event_id": head(s, c.id).id}
            elif a.action == "gate":
                result = scientific_gate(s, c, "/data/assets", a.channel or "STABLE")
            elif a.action == "approve":
                e = approve_model(
                    s,
                    user,
                    c,
                    cfg,
                    "/data/assets",
                    a.channel,
                    a.reason,
                    a.previous_event_id,
                )
                result = {"event_id": e.id}
            elif a.action == "measure":
                new = validate_bundle(check_files(c, cfg))
                baseline = validate_bundle(a.baseline_bundle)
                if baseline["model_sha256"] != BASELINE_SHA:
                    raise ValueError("BASELINE_HASH")
                e = event(
                    s,
                    user,
                    c.id,
                    "CPU_COMPARISON",
                    {
                        "candidate": new,
                        "baseline": baseline,
                        "conditions": "random float32 RGB128 input; batch1/7; CPU2 threads; warmup1/repeat5",
                    },
                    a.previous_event_id,
                )
                result = {"event_id": e.id}
            elif a.action == "prepare":
                result = prepare_release(
                    s, user, c, cfg, "/data/assets", a.channel, a.key_id, a.reason
                )
                with safe_path(a.output).open("xb") as f:
                    f.write(canonical(result))
                audit(
                    s,
                    "MODEL_SIGNING_PREPARED",
                    user.id,
                    release_id=result["release_id"],
                )
                # Approval remains the latest approval assertion; preparation is audit only.
                result = {"release_id": result["release_id"], "output_created": True}
            elif a.action == "publish":
                r = publish(
                    s,
                    user,
                    read_json(safe_path(a.metadata).read_bytes()),
                    cfg,
                    "/data/assets",
                )
                result = {"release_id": r.id}
            elif a.action in ("key-register", "key-revoke"):
                public = read_json(safe_path(a.public_key_file).read_bytes())
                if a.action == "key-register":
                    e = register_key(s, user, public["key_id"], public["public_key"])
                else:
                    e = event(
                        s,
                        user,
                        "key." + public["key_id"],
                        "KEY_REVOKED",
                        {"public_key": public["public_key"], "status": "REVOKED"},
                        a.previous_event_id,
                    )
                result = {"event_id": e.id}
            elif a.action in ("beta-grant", "beta-revoke"):
                e = event(
                    s,
                    user,
                    "beta." + a.user_id,
                    "BETA_GRANTED" if a.action == "beta-grant" else "BETA_REVOKED",
                    {"reason": a.reason},
                    a.previous_event_id,
                )
                result = {"event_id": e.id}
            else:
                from .models import ModelRelease

                if (
                    not a.previous_event_id
                    or not a.reason
                    or not 10 <= len(a.reason) <= 4000
                    or not s.get(ModelRelease, a.release_id)
                ):
                    raise ValueError("RELEASE_REVOCATION_CONTEXT")
                e = event(
                    s,
                    user,
                    "release." + a.release_id,
                    "REVOKED",
                    {"reason": a.reason},
                    a.previous_event_id,
                )
                result = {"event_id": e.id}
        print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
