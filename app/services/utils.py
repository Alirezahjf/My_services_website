"""Small shared utilities."""
import hashlib
import re
import unicodedata
from flask import request


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    value = re.sub(r"[^\w\-\s\u0600-\u06FF]", "", value, flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", value).strip("-")[:170]


def split_lines(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def persian_digits(value) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def normalize_digits(value: str) -> str:
    return (value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def client_ip_hash() -> str:
    secret = "lead-ip-v1"  # keyed only to prevent storing raw addresses
    return hashlib.sha256(f"{secret}:{request.remote_addr or ''}".encode()).hexdigest()
