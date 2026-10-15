"""Durable correction outbox and the deliberately small server report contract."""
import base64
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from uuid import UUID

from .protocol import digest, encode
from .client import SyncError

REASONS = ("결함 아님", "종류가 다름", "위치가 다름", "영역이 다름", "중복 후보", "누락 결함", "기타")


def validate_report(value):
    if set(value) != {"schema","report_id","created_at","reason","comment","candidates","run_id","source","roi","model_version","correction","crops","approval"}:
        raise ValueError("INVALID_REPORT_FIELDS")
    if value["schema"]!="xrt_correction/v1" or value["approval"]!="UNVERIFIED":
        raise ValueError("INVALID_REPORT_SCHEMA")
    UUID(value["report_id"])
    if value["reason"] not in REASONS or not isinstance(value["comment"],str) or len(value["comment"])>2000:
        raise ValueError("INVALID_REPORT_REASON")
    source=value["source"]
    if set(source)!={"sha256","width","height","dtype","page"} or len(source["sha256"])!=64:
        raise ValueError("INVALID_REPORT_SOURCE")
    int(source["sha256"],16)
    w,h=source["width"],source["height"]
    if any(type(n) is not int or n<=0 or n>10000000 for n in (w,h)) or type(source["page"]) is not int or source["page"]<0:
        raise ValueError("INVALID_REPORT_EXTENT")
    if not isinstance(value["candidates"],list) or len(value["candidates"])>500:
        raise ValueError("REPORT_SELECTION_LIMIT")
    ids=set()
    for c in value["candidates"]:
        if set(c)!={"id","x","y","type","score"} or not isinstance(c["id"],str) or c["id"] in ids:
            raise ValueError("INVALID_REPORT_CANDIDATE")
        ids.add(c["id"])
        if not all(isinstance(n,(int,float)) and math.isfinite(n) for n in (c["x"],c["y"],c["score"])) or not (0<=c["x"]<w and 0<=c["y"]<h and 0<=c["score"]<=1):
            raise ValueError("INVALID_REPORT_COORDINATE")
    if not value["candidates"] and value["reason"]!="누락 결함":
        raise ValueError("CANDIDATES_REQUIRED")
    roi=value["roi"]
    if roi is not None:
        if not isinstance(roi,list) or len(roi)!=4 or any(type(n) is not int for n in roi) or not (0<=roi[0]<w and 0<=roi[1]<h and roi[2]>0 and roi[3]>0 and roi[0]+roi[2]<=w and roi[1]+roi[3]<=h):
            raise ValueError("INVALID_REPORT_ROI")
    if value["reason"]=="누락 결함" and roi is None:
        raise ValueError("MISSING_DEFECT_REQUIRES_ROI")
    if value["reason"]=="중복 후보" and len(ids)<2:
        raise ValueError("DUPLICATE_REQUIRES_TWO_CANDIDATES")
    if value["correction"] not in ("", "BPD", "TED", "TSD", "미확정"):
        raise ValueError("INVALID_CORRECTION")
    if not isinstance(value["crops"],list) or len(value["crops"])>2:
        raise ValueError("CROP_LIMIT")
    for crop in value["crops"]:
        if set(crop)!={"kind","rect","png","sha256"} or crop["kind"] not in ("detail","context"):
            raise ValueError("INVALID_CROP")
        raw=base64.b64decode(crop["png"],validate=True)
        if len(raw)>2*1024**2 or not raw.startswith(b"\x89PNG\r\n\x1a\n") or hashlib.sha256(raw).hexdigest()!=crop["sha256"]:
            raise ValueError("INVALID_CROP_DATA")
        x,y,cw,ch=crop["rect"]
        if any(type(n) is not int for n in (x,y,cw,ch)) or not (0<=x<w and 0<=y<h and 0<cw<=512 and 0<ch<=512 and x+cw<=w and y+ch<=h):
            raise ValueError("INVALID_CROP_EXTENT")
    for key in ("created_at","run_id","model_version"):
        if not isinstance(value[key],str) or len(value[key])>512:
            raise ValueError("INVALID_REPORT_METADATA")
    if len(encode(value))>6*1024**2:
        raise ValueError("REPORT_TOO_LARGE")
    return value


class ReportQueue:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL,endpoint TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '')")

    def db(self):
        return sqlite3.connect(self.path,timeout=10)

    def stage(self,payload):
        validate_report(payload)
        with self.db() as db:
            db.execute("INSERT INTO reports(id,payload,hash) VALUES(?,?,?)",(payload["report_id"],encode(payload).decode(),digest(payload)))

    def rows(self):
        with self.db() as db:
            return [dict(id=r[0],reason=r[1],count=r[2],state=r[3],error=r[4]) for r in db.execute("SELECT id,json_extract(payload,'$.reason'),json_array_length(payload,'$.candidates'),state,error FROM reports ORDER BY rowid DESC LIMIT 100")]

    def counts(self):
        with self.db() as db:
            values=dict(db.execute("SELECT state,COUNT(*) FROM reports GROUP BY state"))
        return sum(v for k,v in values.items() if k!="SENT"),values.get("SENT",0)

    def pending(self,endpoint):
        with self.db() as db:
            return [dict(id=r[0],payload=json.loads(r[1]),hash=r[2],endpoint=r[3],state=r[4],attempts=r[5],error=r[6]) for r in db.execute("SELECT * FROM reports WHERE state!='SENT' AND endpoint IN ('',?) ORDER BY rowid LIMIT 20",(endpoint,))]

    def send(self,rows,transport):
        for row in rows:
            with self.db() as db:
                current=db.execute("SELECT state,endpoint,hash FROM reports WHERE id=?",(row["id"],)).fetchone()
                if not current or current[0]=="SENT":
                    continue
                if current[1] not in ("",transport.endpoint) or current[2]!=row["hash"]:
                    raise SyncError("REPORT_PREVIEW_CHANGED")
                db.execute("UPDATE reports SET endpoint=?,state='SENDING',attempts=attempts+1,error='' WHERE id=?",(transport.endpoint,row["id"]))
            try:
                ack=transport.request("POST","/api/v1/reports",row["payload"])
                if (ack.get("report_id"),ack.get("payload_hash"),ack.get("status"))!=(row["id"],row["hash"],"ACKNOWLEDGED"):
                    raise SyncError("REPORT_ACK_MISMATCH")
            except Exception as exc:
                code=str(exc) if isinstance(exc,SyncError) else "REPORT_SEND_FAILED"
                with self.db() as db:
                    db.execute("UPDATE reports SET state='FAILED',error=? WHERE id=?",(code,row["id"]))
                raise SyncError(code) from None
            with self.db() as db:
                db.execute("UPDATE reports SET state='SENT',error='' WHERE id=?",(row["id"],))
