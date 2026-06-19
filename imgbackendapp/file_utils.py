import os
import secrets
import string
from datetime import datetime

_ALPHANUM = string.ascii_letters + string.digits


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
