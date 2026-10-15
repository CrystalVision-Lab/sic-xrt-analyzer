"""Small strict validators for the additional project contract."""

import math
import re
from datetime import datetime
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, uuid4, uuid5

from sic_xrt_analyzer.analysis.contracts import freeze

SCHEMA_VERSION = "1.0.0"


def new_id():
    return str(uuid4())


def stable_id(namespace, key):
    return str(uuid5(NAMESPACE_URL, namespace + ":" + key))


def text(value, name="identifier", *, optional=False):
    if optional and value is None:
        return
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError(f"{name} must be a nonempty string without control characters")


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def number(value, name, minimum=None, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if (
        minimum is not None
        and value < minimum
        or maximum is not None
        and value > maximum
    ):
        raise ValueError(f"{name} outside range")


def timestamp(value):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("Timestamps require a timezone")


def digest(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError(
            "A recorded SHA256 requires 64 lowercase hexadecimal characters"
        )


def asset_reference(value):
    text(value, "asset reference")
    if (
        "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(p in ("", ".", "..") for p in value.split("/"))
    ):
        raise ValueError("Asset references must be safe relative POSIX paths")
    if PurePosixPath(value).is_absolute():
        raise ValueError("Absolute asset references are forbidden")


def freeze_fields(record, *names):
    for name in names:
        value = getattr(record, name)
        if not hasattr(value, "items"):
            raise ValueError(f"{name} requires a JSON mapping")
        object.__setattr__(record, name, freeze(value))


def unique(records, field):
    result = {}
    for record in records:
        key = getattr(record, field)
        text(key)
        if key in result:
            raise ValueError(f"Duplicate {field}: {key}")
        result[key] = record
    return result
