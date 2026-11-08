"""Validated, non-executable media storage."""
import io
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class MediaValidationError(ValueError):
    pass


def _safe_svg(data: bytes) -> bytes:
    if len(data) > 2 * 1024 * 1024:
        raise MediaValidationError("حجم SVG بیش از حد مجاز است.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise MediaValidationError("فایل SVG معتبر نیست.") from exc
    if not root.tag.lower().endswith("svg"):
        raise MediaValidationError("فایل SVG معتبر نیست.")
    allowed_tags = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient", "stop", "title", "desc", "text"}
    for element in root.iter():
        tag = element.tag.lower().split("}")[-1]
        if tag not in allowed_tags:
            raise MediaValidationError("SVG حاوی عنصر غیرمجاز است.")
        for key, value in element.attrib.items():
            key = key.lower().split("}")[-1]
            if key.startswith("on") or key == "style" or (key in {"href", "src"} and not value.startswith("#")):
                raise MediaValidationError("SVG حاوی محتوای فعال یا پیوند خارجی است.")
            if "javascript:" in value.lower() or "url(" in value.lower():
                raise MediaValidationError("SVG امن نیست.")
    return data


def save_upload(file: FileStorage, kind: str = "image") -> dict:
    if not file or not file.filename:
        raise MediaValidationError("فایلی انتخاب نشده است.")
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    config = current_app.config
    groups = {
        "image": config["ALLOWED_IMAGE_EXTENSIONS"],
        "video": config["ALLOWED_VIDEO_EXTENSIONS"],
        "document": config["ALLOWED_DOCUMENT_EXTENSIONS"],
    }
    if kind not in groups or ext not in groups[kind]:
        raise MediaValidationError("نوع فایل برای این بخش مجاز نیست.")
    data = file.stream.read()
    if not data:
        raise MediaValidationError("فایل خالی است.")
    if kind == "image" and ext != "svg":
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise MediaValidationError("محتوای تصویر معتبر نیست.") from exc
    elif kind == "image":
        data = _safe_svg(data)
    elif kind == "document" and not data.startswith(b"%PDF-"):
        raise MediaValidationError("محتوای PDF معتبر نیست.")
    elif kind == "video":
        valid_signature = (
            (ext == "mp4" and len(data) >= 12 and data[4:8] == b"ftyp")
            or (ext == "webm" and data.startswith(b"\x1a\x45\xdf\xa3"))
            or (ext == "ogg" and data.startswith(b"OggS"))
        )
        if not valid_signature:
            raise MediaValidationError("محتوای ویدئو با پسوند فایل همخوانی ندارد.")

    folder = Path(config["UPLOAD_FOLDER"]) / kind
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = folder / filename
    path.write_bytes(data)
    path.chmod(0o640)
    relative = f"{kind}/{filename}"
    result = {"path": relative, "size": len(data), "mime_type": file.mimetype, "thumbnail": None}
    if kind == "image" and ext != "svg":
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.thumbnail((640, 640))
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGB")
                thumb_name = f"{uuid.uuid4().hex}.webp"
                thumb_path = folder / thumb_name
                image.save(thumb_path, "WEBP", quality=82, method=6)
                thumb_path.chmod(0o640)
                result["thumbnail"] = f"{kind}/{thumb_name}"
        except OSError:
            pass
    return result


def delete_upload(relative_path: str | None):
    if not relative_path or ".." in relative_path or relative_path.startswith("/"):
        return
    path = Path(current_app.config["UPLOAD_FOLDER"]) / relative_path
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    if path.resolve().is_relative_to(root) and path.is_file():
        path.unlink()
