"""Messy uploads: rotation, blur, HEIC, PDF, damaged and unsupported files."""
import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageFilter

from treasurer.images import MAX_SIDE, UnsupportedFile, prepare

R01 = (Path(__file__).parent.parent / "fake_event" / "receipts" / "R01.jpg").read_bytes()


def jpeg(im, **kw):
    buf = io.BytesIO()
    im.save(buf, "JPEG", **kw)
    return buf.getvalue()


def test_clean_photo_passes_through_untouched():
    f = prepare(R01, "R01.jpg")
    assert f.data == R01 and f.media_type == "image/jpeg" and f.warnings == []


def test_sideways_phone_photo_is_turned_upright():
    im = Image.open(io.BytesIO(R01)).rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 8  # "rotate 90 CW to view"
    f = prepare(jpeg(im, exif=exif), "R01.jpg")
    out = Image.open(io.BytesIO(f.data))
    assert out.size == Image.open(io.BytesIO(R01)).size
    assert any("Rotated" in w for w in f.warnings)


def test_blurry_photo_warns_but_does_not_block():
    blurry = jpeg(Image.open(io.BytesIO(R01)).filter(ImageFilter.GaussianBlur(4)))
    f = prepare(blurry, "R01.jpg")
    assert any("blurry" in w for w in f.warnings)


def test_huge_photo_is_shrunk():
    big = jpeg(Image.open(io.BytesIO(R01)).resize((3000, 3080)))
    f = prepare(big, "R01.jpg")
    assert max(Image.open(io.BytesIO(f.data)).size) == MAX_SIDE


def test_heic_without_plugin_says_what_to_do(monkeypatch):
    monkeypatch.setitem(sys.modules, "pillow_heif", None)  # simulate not installed
    with pytest.raises(UnsupportedFile, match="pillow-heif"):
        prepare(b"\x00\x00\x00\x18ftypheic", "IMG_0001.HEIC")


def test_heic_converts_to_jpg_when_plugin_present():
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.open(io.BytesIO(R01)).save(buf, "HEIF")
    f = prepare(buf.getvalue(), "R01.heic")
    assert f.filename == "R01.jpg" and f.media_type == "image/jpeg"


def test_pdf_passes_through_and_fake_pdf_is_refused():
    f = prepare(b"%PDF-1.7 fake receipt", "R16.pdf")
    assert f.is_pdf and f.filename == "R16.pdf"
    with pytest.raises(UnsupportedFile, match="isn't one"):
        prepare(b"hello", "R16.pdf")


@pytest.mark.parametrize("data,name,msg", [
    (b"", "R01.jpg", "empty"),
    (b"not an image at all", "R01.jpg", "won't open"),
    (b"x", "notes.docx", "aren't supported"),
])
def test_unreadable_files_get_a_plain_message(data, name, msg):
    with pytest.raises(UnsupportedFile, match=msg):
        prepare(data, name)
