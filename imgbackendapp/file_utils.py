import os
import secrets
import string
from datetime import datetime

from django.conf import settings

_ALPHANUM = string.ascii_letters + string.digits

_NON_FILE_PATH_VALUES = frozenset({"Multiple products", "Multiple ornaments"})


def generate_unique_filename(original_filename: str = "image.jpg", suffix: str = "") -> str:
    """Build ``{YYYYMMDDHHMMSSmmm}_{abcd}.ext`` using local server time."""
    ext = os.path.splitext(original_filename)[1].lower() or ".jpg"
    now = datetime.now()
    dt_ms = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    rand = "".join(secrets.choice(_ALPHANUM) for _ in range(4))
    name = f"{dt_ms}_{rand}"
    if suffix:
        name = f"{name}_{suffix}"
    return f"{name}{ext}"


def generate_unique_image_path(
    base_dir: str,
    original_filename: str = "image.jpg",
    suffix: str = "",
) -> str:
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, generate_unique_filename(original_filename, suffix=suffix))


def path_stem(file_path: str) -> str:
    return os.path.splitext(os.path.basename(file_path))[0]


def _media_root_normalized() -> str:
    return os.path.normpath(str(settings.MEDIA_ROOT)).replace("\\", "/").rstrip("/")


def normalize_media_path(stored_path: str) -> str:
    """Return canonical ``/media/...`` form for comparisons and API payloads."""
    if not stored_path or stored_path in _NON_FILE_PATH_VALUES:
        return stored_path

    normalized = stored_path.replace("\\", "/")
    if normalized.startswith("/media/"):
        return normalized

    norm = os.path.normpath(stored_path).replace("\\", "/")
    media_root = _media_root_normalized()
    if norm.lower().startswith(media_root.lower() + "/") or norm.lower() == media_root.lower():
        rel = norm[len(media_root):].lstrip("/")
        return f"/media/{rel}"

    idx = norm.lower().find("/media/")
    if idx != -1:
        return norm[idx:]

    return normalized


def to_media_db_path(absolute_path: str) -> str:
    """Convert an absolute filesystem path under MEDIA_ROOT to ``/media/...``."""
    if not absolute_path or absolute_path in _NON_FILE_PATH_VALUES:
        return absolute_path
    return normalize_media_path(absolute_path)


def resolve_media_path(stored_path: str) -> str:
    """Resolve ``/media/...`` or legacy absolute paths to a filesystem path."""
    if not stored_path or stored_path in _NON_FILE_PATH_VALUES:
        return stored_path

    db_path = normalize_media_path(stored_path)
    if db_path.startswith("/media/"):
        rel = db_path[len("/media/"):].lstrip("/")
        return os.path.join(str(settings.MEDIA_ROOT), rel.replace("/", os.sep))

    return os.path.normpath(stored_path)


def media_paths_equal(path_a: str, path_b: str) -> bool:
    """Compare stored paths regardless of absolute vs ``/media/`` representation."""
    if not path_a or not path_b:
        return path_a == path_b
    if path_a in _NON_FILE_PATH_VALUES or path_b in _NON_FILE_PATH_VALUES:
        return path_a == path_b
    return normalize_media_path(path_a) == normalize_media_path(path_b)


def save_uploaded_file(uploaded_file, base_dir: str, suffix: str = "") -> str:
    local_path = generate_unique_image_path(base_dir, uploaded_file.name, suffix=suffix)
    with open(local_path, "wb+") as dest:
        for chunk in uploaded_file.chunks():
            dest.write(chunk)
    return local_path


def write_bytes_to_unique_path(
    base_dir: str,
    data: bytes,
    original_filename: str = "output.jpg",
    suffix: str = "",
) -> str:
    local_path = generate_unique_image_path(base_dir, original_filename, suffix=suffix)
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path


def django_upload_to(subfolder: str):
    def _upload_to(instance, filename):
        return os.path.join(subfolder, generate_unique_filename(filename)).replace("\\", "/")

    return _upload_to
