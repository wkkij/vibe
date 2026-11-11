"""Vibi — the Vibe mascot: a square pixel-art cat (purple body, teal ear tips, pink cheeks, little «ω» mouth).

The big picture is drawn from pixel frames (core/sprites.py): each pixel is two terminal columns wide and two
pixels share one text row (half-block «▀▄»), so the cat is 32 columns x 7 rows. `grid(frame)` gives the raw
pixels, `art(mood)` plain text lines (used for tests and by ui.py, which colours them), `animation(mood)` the
frame sequence with timings, `face(mood)` the small inline face used in the prompt and in status lines.
Unicode half-blocks are used when the terminal can show them, otherwise a plain ASCII version (force it with
VIBE_ASCII=1).

Moods: idle, happy, think, work, error, sleep, wink.
"""
import os
import sys
from typing import List, Optional, Tuple

from .sprites import FRAMES, PALETTE

MOODS = ("idle", "happy", "think", "work", "error", "sleep", "wink")

WIDTH_PX, HEIGHT_PX = 16, 14   # pixels of one frame
ART_COLS = WIDTH_PX * 2        # terminal columns of the big picture
ART_ROWS = HEIGHT_PX // 2      # terminal rows of the big picture

# mood -> [(frame index in sprites.FRAMES, seconds on screen), ...]; the first frame is the still picture of the mood
_ANIM = {
    "idle": [(0, 1.4), (3, 0.12), (0, 0.9), (1, 0.45), (2, 0.45), (0, 1.0), (3, 0.12), (0, 0.7),
             (4, 0.45), (5, 0.45), (6, 0.35), (0, 1.1)],
    "happy": [(7, 0.30), (8, 0.30), (9, 0.30), (10, 0.30)],
    "think": [(11, 0.45), (12, 0.45), (13, 0.45)],
    "work": [(14, 0.35), (15, 0.35), (16, 0.35), (17, 0.35)],
    "error": [(18, 0.5), (19, 0.5)],
    "sleep": [(20, 0.8), (21, 0.8)],
    "wink": [(10, 0.4), (0, 0.4)],
}

# mood -> (left eye, right eye, mouth) for the one-line face: [ eye mouth eye ]
_SMALL = {
    "idle": ("•", "•", "ω"),
    "happy": ("^", "^", "ω"),
    "think": ("•", "•", "~"),
    "work": ("◕", "◕", "ω"),
    "error": ("×", "×", "n"),
    "sleep": ("-", "-", "ω"),
    "wink": ("•", ">", "ω"),
}
_ASCII_EYES = {"◕": "O", "•": "o", "ω": "w", "×": "x"}

_ASCII_PIXELS = {".": "  ", "B": "##", "D": "%%", "K": "@@", "W": "oo", "T": "**", "P": "++"}


def unicode_ok() -> bool:
    """False only if the user asked for ASCII (VIBE_ASCII=1) or the output encoding is known to be a legacy one.

    The encoding of sys.stdout is often missing when the stream is wrapped (prompt_toolkit, colorama): then the
    real console stream is asked, and if that tells nothing either, Unicode is assumed (rich does the same).
    VIBE_UNICODE=1 forces the block-character Vibi."""
    env = os.environ
    if env.get("VIBE_ASCII", "").lower() in ("1", "true", "yes", "on"):
        return False
    if env.get("VIBE_UNICODE", "").lower() in ("1", "true", "yes", "on"):
        return True
    for stream in (sys.stdout, getattr(sys, "__stdout__", None)):
        enc = (getattr(stream, "encoding", None) or "").lower()
        if enc:
            return "utf" in enc
    return True


def animation_enabled() -> bool:
    return os.environ.get("VIBE_NO_ANIM", "").lower() not in ("1", "true", "yes", "on")


def animation(mood: str = "idle") -> List[Tuple[int, float]]:
    """Frame sequence of a mood: [(frame index, seconds)]."""
    return list(_ANIM.get(mood, _ANIM["idle"]))


def still(mood: str = "idle") -> int:
    """Index of the frame shown when the mood is not animated."""
    return animation(mood)[0][0]


def grid(frame: int = 0) -> Tuple[str, ...]:
    """Raw pixels of a frame: 14 strings of 16 palette characters ('.' = transparent)."""
    return FRAMES[frame % len(FRAMES)]


def cell(top: str, bottom: str, uni: bool = True) -> Tuple[str, Optional[str], Optional[str]]:
    """One terminal cell made of two stacked pixels -> (character, foreground palette key, background palette key)."""
    if top == "." and bottom == ".":
        return " ", None, None
    if bottom == ".":
        return "▀", top, None
    if top == ".":
        return "▄", bottom, None
    if top == bottom:
        return "█", top, None
    return "▀", top, bottom


def art(mood: str = "idle", uni: bool = None, frame: int = None) -> list:
    """Big Vibi as plain text: 7 lines x 32 columns (half-blocks) or 14 lines x 32 columns (ASCII)."""
    uni = unicode_ok() if uni is None else uni
    px = grid(still(mood) if frame is None else frame)
    if not uni:
        return ["".join(_ASCII_PIXELS[c] for c in row) for row in px]
    lines = []
    for y in range(0, HEIGHT_PX, 2):
        lines.append("".join(cell(px[y][x], px[y + 1][x])[0] * 2 for x in range(WIDTH_PX)))
    return lines


def face(mood: str = "idle", uni: bool = None) -> str:
    """Small Vibi for one line: [•ω•]."""
    uni = unicode_ok() if uni is None else uni
    l, r, m = _SMALL.get(mood, _SMALL["idle"])
    if not uni:
        l, r, m = (_ASCII_EYES.get(x, x) for x in (l, r, m))
    return f"[{l}{m}{r}]"


# Frames for the «working» spinner (used when the terminal is too small for the big animated Vibi).
def work_frames(uni: bool = None) -> list:
    uni = unicode_ok() if uni is None else uni
    if uni:
        return ["[•ω•]", "[•ω•]", "[•ω•]", "[-ω-]", "[•ω•]", "[◕ω◕]", "[•ω•]", "[•ω•]"]
    return ["[owo]", "[owo]", "[owo]", "[-w-]", "[owo]", "[OwO]"]
