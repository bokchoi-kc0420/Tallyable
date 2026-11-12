"""Get an uploaded file ready for reading, and say plainly what's wrong with it.

- JPG, PNG, WEBP: phone rotation fixed (EXIF), shrunk to 1600px on the long
  side (big photos only cost more tokens; Claude doesn't read them better).
- HEIC (iPhone default): converted to JPG (pillow-heif).
- PDF: passed through as is; Claude reads PDFs directly.
- Anything else, or a file that won't open: UnsupportedFile with a message.

Warnings (blurry, tiny) never block: the human still decides. The blur score
is the variance of an edge filter; sharp fake receipts score ~1500 and a light
blur drops them under 50, so 150 is a cautious line.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pillow_heif
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

pillow_heif.register_heif_opener()  # lets Image.open read iPhone HEIC photos

MAX_SIDE = 1600
MIN_SIDE = 400
BLUR_LINE = 150.0
MAX_PDF_BYTES = 30 * 1024 * 1024  # API request limit is 32 MB
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
UPLOAD_TYPES = ["jpg", "jpeg", "png", "webp", "heic", "heif", "pdf"]


class UnsupportedFile(Exception):
    """The file can't be read at all. The message says what to do instead."""


@dataclass
class Prepared:
    data: bytes
    filename: str           # what the extractor sees, e.g. R03.heic becomes R03.jpg
    media_type: str
    warnings: list[str] = field(default_factory=list)


def blur_score(im: Image.Image) -> float:
    g = im.convert("L")
    g.thumbnail((1000, 1000))
    return ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]


def prepare(data: bytes, filename: str) -> Prepared:
    name, ext = Path(filename).name, Path(filename).suffix.lower()
    if not data:
        raise UnsupportedFile(f"{name} is empty. Upload it again, or enter it by hand below.")

    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise UnsupportedFile(f"{name} says it's a PDF but isn't one. Enter it by hand below.")
        if len(data) > MAX_PDF_BYTES:
            raise UnsupportedFile(f"{name} is over 30 MB. Export just the receipt page, or enter it by hand.")
        return Prepared(data, name, "application/pdf")

    if ext not in IMAGE_TYPES and ext not in (".heic", ".heif"):
        raise UnsupportedFile(f"{name}: {ext or 'no extension'} files aren't supported. Use JPG, PNG, HEIC or PDF.")

    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except UnsupportedFile:
        raise
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedFile(f"{name} won't open as an image (it may be damaged). Enter it by hand below.") from e

    warnings = []
    upright = ImageOps.exif_transpose(im)  # phones store "turn me" as a tag; apply it (no warning: nothing to check)
    turned = upright.size != im.size or im.getexif().get(0x0112, 1) != 1
    im = upright
    if min(im.size) < MIN_SIDE:
        warnings.append(f"Small image ({im.size[0]}x{im.size[1]}px); small print may be misread. Check each line.")
    if blur_score(im) < BLUR_LINE:
        warnings.append("Looks blurry. Check every number against the photo, or retake it.")

    changed = ext in (".heic", ".heif") or max(im.size) > MAX_SIDE or turned
    if not changed:
        return Prepared(data, name, IMAGE_TYPES[ext], warnings)
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90)
    return Prepared(buf.getvalue(), Path(name).stem + ".jpg", "image/jpeg", warnings)
