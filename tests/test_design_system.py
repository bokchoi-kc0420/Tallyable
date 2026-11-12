"""The design system's rules, checked on every CSS file and UI module, so a stray value can't creep back in."""
import re
from pathlib import Path

UI = Path(__file__).parent.parent / "ui"
CSS = {p.name: p.read_text(encoding="utf-8") for p in UI.glob("*.css")}
TOKENS = re.compile(r":root\s*{[^}]*}")


HAND_TUNED = {"home.css"}  # Club home: Kevin kept its own sizes, corners and shadow


def values(prop: str):
    for name, css in CSS.items():
        if name in HAND_TUNED:
            continue
        for v in re.findall(rf"(?<![-\w]){prop}:\s*([^;}}]+)", TOKENS.sub("", css)):
            yield name, v.replace("!important", "").strip()


def test_spacing_is_on_the_8pt_scale():
    sizes = [(f, v, float(n) * (16 if unit == "rem" else 1))
             for prop in ("margin(?:-[a-z]+)?", "padding(?:-[a-z]+)?", "(?:row-|column-)?gap")
             for f, v in values(prop) for n, unit in re.findall(r"(-?[\d.]+)(px|rem)", v)]
    assert not [(f, v) for f, v, px in sizes if px % 8 and abs(px) != 4]


def test_one_radius_one_shadow_one_type_ramp():
    assert not [v for _, v in values("border-radius") if not re.fullmatch(r"((var\(--tly-r(-in)?\)|999px|50%|4px|0)\s*)+", v)]
    assert not [v for _, v in values("box-shadow") if v not in ("var(--tly-shadow)", "var(--tly-ring)", "none")]
    assert not [v for _, v in values("font-size") if not v.startswith("var(--tly-t-")]


def test_colors_come_from_tokens():
    assert not [(f, c) for f, css in CSS.items() for c in re.findall(r"#[0-9A-Fa-f]{3,6}\b", TOKENS.sub("", css))]


def test_no_emoji_in_the_ui():
    emoji = re.compile(r"[\u2300-\u23ff\u2600-\u26ff\u2705\u274c\U0001F000-\U0001FAFF]")  # a plain check mark is text
    assert not [p.name for p in UI.glob("*.py") if emoji.search(p.read_text(encoding="utf-8"))]
