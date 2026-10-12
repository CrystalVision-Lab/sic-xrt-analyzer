"""Strict JSON codec for a fixed dataclass schema; no object tags, pickle or executable input."""

import json
import types
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Union, get_args, get_origin, get_type_hints

from .contracts import AnalysisProject
from .validation import SCHEMA_VERSION

FORMAT = "sic_xrt_analysis_project"
MAX_PROJECT_BYTES = 64 * 1024**2


def plain(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError("Unsupported non-JSON project value")


@lru_cache(maxsize=64)
def _hints(cls):
    return get_type_hints(cls)


def _decode(cls, value):
    origin, args = get_origin(cls), get_args(cls)
    if origin in (types.UnionType, Union):
        for option in args:
            try:
                return _decode(option, value)
            except (ValueError, TypeError):
                pass
        raise ValueError("Value does not match the declared union")
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("JSON array required")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], v) for v in value)
        if len(value) != len(args):
            raise ValueError("Tuple length mismatch")
        return tuple(_decode(t, v) for t, v in zip(args, value, strict=True))
    if cls is Mapping or origin is Mapping:
        if not isinstance(value, dict):
            raise ValueError("JSON mapping required")
        return value
    if cls is datetime:
        if not isinstance(value, str):
            raise ValueError("ISO timestamp required")
        return datetime.fromisoformat(value)
    if isinstance(cls, type) and issubclass(cls, Enum):
        return cls(value)
    if is_dataclass(cls):
        if not isinstance(value, dict):
            raise ValueError("JSON record required")
        hints = _hints(cls)
        known = {f.name for f in fields(cls)}
        if set(value) != known:
            raise ValueError(f"Missing or unknown {cls.__name__} fields")
        return cls(**{k: _decode(hints[k], v) for k, v in value.items()})
    if cls is float and type(value) in (float, int):
        return value  # Do not round or coerce the original numeric representation.
    if (
        cls is type(None)
        and value is None
        or cls in (str, int, bool)
        and type(value) is cls
    ):
        return value
    raise ValueError("Project value has an invalid type")


def dumps(project):
    if not isinstance(project, AnalysisProject):
        raise TypeError("Validated AnalysisProject required")
    # Reconstruct to validate even a caller that used object.__setattr__ on a frozen instance.
    AnalysisProject(**{f.name: getattr(project, f.name) for f in fields(project)})
    payload = {
        "format": FORMAT,
        "schema_version": project.schema_version,
        "project": plain(project),
    }
    if project.schema_version == "1.0.0":
        for event in payload["project"]["review_events"]:
            for field in ("existence", "class_decision", "geometry_decision"):
                del event[field]
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )
    if len(encoded) > MAX_PROJECT_BYTES:
        raise ValueError("Project manifest exceeds 64 MiB metadata limit")
    loads(encoded)
    return encoded


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def loads(encoded):
    if not isinstance(encoded, (bytes, str)) or len(encoded) > MAX_PROJECT_BYTES:
        raise ValueError("Project exceeds metadata read limit or has invalid input")
    try:
        data = json.loads(
            encoded,
            object_pairs_hook=_pairs,
            parse_constant=lambda v: (_ for _ in ()).throw(
                ValueError("Nonfinite JSON number")
            ),
        )
        if (
            not isinstance(data, dict)
            or set(data) != {"format", "schema_version", "project"}
            or data["format"] != FORMAT
        ):
            raise ValueError("Not a research project manifest")
        if data["schema_version"] not in (SCHEMA_VERSION, "1.1.0"):
            raise ValueError(
                f"Unsupported project schema: {data['schema_version']}; explicit migration required"
            )
        if (
            not isinstance(data["project"], dict)
            or data["project"].get("schema_version") != data["schema_version"]
        ):
            raise ValueError("Envelope/project schema mismatch")
        if data["schema_version"] == "1.0.0":
            # Explicit read migration: legacy status never invents independent judgements.
            for event in data["project"].get("review_events", []):
                for field in ("existence", "class_decision", "geometry_decision"):
                    if field in event:
                        raise ValueError("Schema 1.0.0 cannot contain 1.1.0 decisions")
                    event[field] = "NOT_REVIEWED"
        return _decode(AnalysisProject, data["project"])
    except (
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        KeyError,
        RecursionError,
    ) as exc:
        raise ValueError("Corrupt or invalid project manifest") from exc
