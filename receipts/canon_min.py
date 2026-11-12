"""Canonical JSON encoding and SHA-256, as used by evidence.py."""
import hashlib, json


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()
