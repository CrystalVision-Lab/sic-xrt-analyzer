import hashlib
import secrets
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from .models import Audit, Credential, Device, Membership, Project, User


def audit(session, action, actor=None, project=None, **detail):
    session.add(Audit(action=action, actor_id=actor, project_id=project, detail=detail))


def issue(session, user_id, client_id):
    user = session.get(User, user_id)
    if not user or not user.active:
        raise ValueError("USER_UNAVAILABLE")
    device = session.get(Device, client_id)
    if device and device.user_id != user_id:
        raise ValueError("DEVICE_OWNER_CONFLICT")
    if not device:
        session.add(Device(id=client_id, user_id=user_id))
        session.flush()
    token = "xrt_" + secrets.token_urlsafe(32)
    cred = Credential(
        id=str(uuid4()),
        device_id=client_id,
        digest=hashlib.sha256(token.encode()).hexdigest(),
    )
    session.add(cred)
    audit(
        session,
        "CREDENTIAL_ISSUED",
        user_id,
        device_id=client_id,
        credential_id=cred.id,
    )
    return cred, token


def authenticate(session, header):
    if not header or not header.startswith("Bearer ") or len(header) > 200:
        raise HTTPException(401, "AUTH_REQUIRED")
    sha = hashlib.sha256(header[7:].encode()).hexdigest()
    cred = session.scalar(
        select(Credential).where(
            Credential.digest == sha, Credential.revoked.is_(False)
        )
    )
    if not cred:
        raise HTTPException(401, "INVALID_CREDENTIAL")
    device = session.get(Device, cred.device_id)
    user = session.get(User, device.user_id)
    if not user.active:
        raise HTTPException(401, "INACTIVE_USER")
    return user, device


def authorize(session, user, project_id, *, crop=False):
    project = session.get(Project, project_id)
    member = session.get(Membership, (project_id, user.id))
    if not project or (
        user.role != "ADMIN" and (not member or (crop and not member.crops))
    ):
        raise HTTPException(403, "PROJECT_ACCESS_DENIED")
    return project


def grant(session, user_id, project_id, crops=False):
    if not session.get(User, user_id):
        raise ValueError("USER_UNAVAILABLE")
    if not session.get(Project, project_id):
        session.add(Project(id=project_id))
        session.flush()
    row = session.get(Membership, (project_id, user_id))
    if row:
        row.crops = crops
    else:
        session.add(Membership(project_id=project_id, user_id=user_id, crops=crops))
    audit(session, "PROJECT_GRANTED", user_id, project_id, crops=crops)
