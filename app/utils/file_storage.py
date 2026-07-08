import os
import uuid
import aiofiles
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage"
MAX_PHOTO_SIZE = 5 * 1024 * 1024
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
ALLOWED_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
ALLOWED_ATTACHMENT_TYPES = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "text/plain",
})


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _generate_filename(original: str) -> str:
    ext = Path(original).suffix or ""
    return f"{uuid.uuid4().hex}{ext}"


async def save_photo(org_id: int, employee_id: int, content: bytes, original_filename: str) -> str:
    subdir = STORAGE_ROOT / "photos" / str(org_id) / str(employee_id)
    _ensure_dir(subdir)
    filename = _generate_filename(original_filename)
    filepath = subdir / filename
    async with aiofiles.open(str(filepath), "wb") as f:
        await f.write(content)
    return str(filepath)


async def remove_photo(file_path: str) -> None:
    p = Path(file_path)
    if p.exists():
        p.unlink()
    parent = p.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


async def save_attachment(
    org_id: int,
    employee_id: int,
    attachment_id: int,
    content: bytes,
    original_filename: str,
) -> str:
    subdir = STORAGE_ROOT / "attachments" / str(org_id) / str(employee_id) / str(attachment_id)
    _ensure_dir(subdir)
    filename = _generate_filename(original_filename)
    filepath = subdir / filename
    async with aiofiles.open(str(filepath), "wb") as f:
        await f.write(content)
    return str(filepath)


async def remove_attachment(file_path: str) -> None:
    p = Path(file_path)
    if p.exists():
        p.unlink()
    parent = p.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def validate_photo(file_content_type: str, file_size: int) -> None:
    if file_content_type not in ALLOWED_PHOTO_TYPES:
        raise ValueError(
            f"Invalid photo type '{file_content_type}'. Allowed: {', '.join(sorted(ALLOWED_PHOTO_TYPES))}"
        )
    if file_size > MAX_PHOTO_SIZE:
        raise ValueError(f"Photo too large. Max {MAX_PHOTO_SIZE // (1024*1024)} MB allowed.")


def validate_attachment(file_content_type: str, file_size: int) -> None:
    if file_content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise ValueError(
            f"Invalid file type '{file_content_type}'. Allowed: PDF, DOC, DOCX, images, text."
        )
    if file_size > MAX_ATTACHMENT_SIZE:
        raise ValueError(f"File too large. Max {MAX_ATTACHMENT_SIZE // (1024*1024)} MB allowed.")
