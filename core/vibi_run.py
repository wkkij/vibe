"""Vibi runs across the terminal while the model is answering (every new message).

The cat is drawn as a real picture when the terminal can show inline images, otherwise as colour half-blocks:
  kitty   Kitty graphics protocol (Kitty, Ghostty)
  iterm   iTerm2 inline images (iTerm2, WezTerm)
  sixel   Sixel graphics (Windows Terminal 1.22+, foot, mlterm, ...)
  blocks  true-colour half-block characters (any UTF-8 terminal with 24-bit colour)

Force a mode with VIBE_IMAGES=kitty|iterm|sixel|blocks (VIBE_IMAGES=off = blocks). VIBE_NO_ANIM=1 disables the
running cat. Sixel needs the size of a terminal cell in pixels: VIBE_CELL_PX=WxH (default 10x20) and
VIBE_IMG_SCALE=N (pixels per sprite pixel) can be tuned if the cat looks too big or too small.

Pure standard library: the PNG and Sixel pictures are encoded here.
"""
import base64
import os
import struct
import sys
import threading
import time
import zlib
from typing import Dict, List, Optional, Tuple

from . import mascot
from .sprites import FRAMES, PALETTE

CANVAS = 16            # the picture is 16x16 sprite pixels (a 16x14 sprite plus room to hop)
IMG_COLS, IMG_ROWS = 16, 8   # size of the picture in terminal cells when it is shown as an image
RUN_FRAMES = (14, 15, 16, 17)  # the "work" frames: the cat looks around while running
FPS = 12
SPEED = 16.0           # columns per second

_RGB = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in PALETTE.items()}


# ---------------------------------------------------------------- picture of one frame

def canvas(frame: int, flip: bool = False, hop: bool = False) -> List[str]:
    """16x16 palette rows: the sprite stands on the ground (y=2) or, when `hop`, is lifted by two pixels."""
    sprite = FRAMES[frame % len(FRAMES)]
    rows = list(sprite)
    if flip:
        rows = [r[::-1] for r in rows]
    top = 0 if hop else 2
    empty = "." * CANVAS
    return [empty] * top + rows + [empty] * (CANVAS - len(rows) - top)


def _scale_rows(cv: List[str], s: int) -> List[str]:
    out = []
    for row in cv:
        wide = "".join(c * s for c in row)
        out.extend([wide] * s)
    return out


def encode_png(cv: List[str], s: int = 8) -> bytes:
    """RGBA PNG of the canvas, every sprite pixel scaled to s x s (nearest neighbour = crisp pixel art)."""
    w, h = len(cv[0]) * s, len(cv) * s
    raw = bytearray()
    for row in cv:
        line = bytearray(b"\x00")
        for c in row:
            line += (bytes(_RGB[c]) + b"\xff" if c != "." else b"\x00\x00\x00\x00") * s
        raw += bytes(line) * s

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def encode_sixel(cv: List[str], s: int = 10) -> str:
    """Sixel picture with a transparent background (P2=1: pixels without colour keep what is under them)."""
    rows = _scale_rows(cv, s)
    h, w = len(rows), len(rows[0])
    keys = sorted({c for r in rows for c in r if c != "."})
    out = ["\x1bP0;1;0q", f'"1;1;{w};{h}']
    for i, k in enumerate(keys):
        r, g, b = _RGB[k]
        out.append(f"#{i};2;{r * 100 // 255};{g * 100 // 255};{b * 100 // 255}")
    for y0 in range(0, h, 6):
        band = rows[y0:y0 + 6]
        first = True
        for i, k in enumerate(keys):
            bits = []
            for x in range(w):
                m = 0
                for j, r in enumerate(band):
                    if r[x] == k:
                        m |= 1 << j
                bits.append(m)
            if not any(bits):
                continue
            if not first:
                out.append("$")
            first = False
            out.append(f"#{i}" + _rle(bits))
        out.append("-")
    out.append("\x1b\\")
    return "".join(out)


def _rle(bits: List[int]) -> str:
    out, i = [], 0
    while i < len(bits):
        j = i
        while j < len(bits) and bits[j] == bits[i]:
            j += 1
        ch, n = chr(63 + bits[i]), j - i
        out.append(f"!{n}{ch}" if n > 3 else ch * n)
        i = j
    return "".join(out)


def encode_kitty(png: bytes, cols: int, rows: int) -> str:
    data = base64.b64encode(png).decode()
    parts = [data[i:i + 4096] for i in range(0, len(data), 4096)]
    out = ["\x1b_Ga=d,d=A,q=2\x1b\\"]  # remove the previous picture of the cat
    for i, part in enumerate(parts):
        more = 1 if i < len(parts) - 1 else 0
        ctrl = f"a=T,f=100,t=d,c={cols},r={rows},C=1,q=2,m={more}" if i == 0 else f"m={more}"
        out.append(f"\x1b_G{ctrl};{part}\x1b\\")
    return "".join(out)


def encode_iterm(png: bytes, cols: int, rows: int) -> str:
    data = base64.b64encode(png).decode()
    return f"\x1b]1337;File=inline=1;size={len(png)};width={cols};height={rows};preserveAspectRatio=0:{data}\x07"


def blocks_lines(cv: List[str]) -> List[str]:
    """True-colour half-block lines (2 columns per pixel) -> 8 lines x 32 columns."""
    def fg(k):
        r, g, b = _RGB[k]
        return f"\x1b[38;2;{r};{g};{b}m"

    def bg(k):
        r, g, b = _RGB[k]
        return f"\x1b[48;2;{r};{g};{b}m"

    lines = []
    for y in range(0, len(cv), 2):
        parts = []
        for x in range(len(cv[0])):
            ch, f, b = mascot.cell(cv[y][x], cv[y + 1][x])
            parts.append((fg(f) if f else "") + (bg(b) if b else "") + ch * 2 + "\x1b[0m")
        lines.append("".join(parts))
    return lines


# ---------------------------------------------------------------- which mode does this terminal speak

def detect_mode(env=None) -> str:
    """kitty | iterm | sixel | blocks (never raises)."""
    env = os.environ if env is None else env
    forced = env.get("VIBE_IMAGES", "auto").strip().lower()
    if forced in ("kitty", "iterm", "sixel", "blocks"):
        return forced
    if forced in ("off", "0", "no", "false", "none"):
        return "blocks"
    if env.get("TMUX") or env.get("STY"):
        return "blocks"  # pictures do not pass through tmux / screen without extra setup
    prog = env.get("TERM_PROGRAM", "")
    if prog == "iTerm.app" or prog == "WezTerm":
        return "iterm"
    if env.get("KITTY_WINDOW_ID") or env.get("TERM", "").startswith("xterm-kitty") or prog == "ghostty":
        return "kitty"
    if env.get("WT_SESSION"):
        return "sixel"  # Windows Terminal 1.22+
    return "blocks"


def pick_mode(console) -> Optional[str]:
    """Mode for the running cat, or None if the terminal is not suitable (then a small spinner is used)."""
    if not console.is_terminal or not mascot.animation_enabled():
        return None
    if console.height < 16 or console.width < 50:
        return None
    mode = detect_mode()
    if mode == "blocks":
        truecolor = getattr(console, "color_system", None) == "truecolor"
        if not (mascot.unicode_ok() and truecolor):
            return None
    return mode


# ---------------------------------------------------------------- the runner

class VibiRunner:
    """Reserves a few lines under the cursor and lets Vibi run left and right in them while a `with` block works."""

    def __init__(self, console, text: str, mode: str):
        self.console = console
        self.text = text
        self.mode = mode
        self.out = console.file
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._cache: Dict[Tuple[int, bool, bool], object] = {}
        if mode == "blocks":
            self.cols, self.rows = CANVAS * 2, CANVAS // 2
        else:
            self.cols, self.rows = IMG_COLS, IMG_ROWS
        self.total = self.rows + 1  # picture rows + one status line

    # --- encoded pictures (cached: a handful of distinct frames)
    def _picture(self, frame: int, flip: bool, hop: bool):
        key = (frame, flip, hop)
        if key not in self._cache:
            cv = canvas(frame, flip, hop)
            if self.mode == "blocks":
                self._cache[key] = blocks_lines(cv)
            elif self.mode == "sixel":
                self._cache[key] = encode_sixel(cv, self._sixel_scale())
            else:
                png = encode_png(cv, 8)
                self._cache[key] = encode_kitty(png, self.cols, self.rows) if self.mode == "kitty" else encode_iterm(png, self.cols, self.rows)
        return self._cache[key]

    @staticmethod
    def _sixel_scale() -> int:
        try:
            return max(2, int(os.environ["VIBE_IMG_SCALE"]))
        except (KeyError, ValueError):
            pass
        try:
            _, ch = os.environ.get("VIBE_CELL_PX", "10x20").lower().split("x")
            return max(2, round(IMG_ROWS * int(ch) / CANVAS))
        except ValueError:
            return 10

    def _w(self, s: str) -> None:
        self.out.write(s)

    def start(self) -> None:
        if os.name == "nt":
            os.system("")  # switches the Windows console to ANSI / VT mode
        self._w("\x1b[?25l" + "\n" * self.total)  # hide the cursor, reserve the lines
        self.out.flush()
        self.thread = threading.Thread(target=self._loop, name="vibi-run", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        try:
            tail = "\x1b_Ga=d,d=A,q=2\x1b\\" if self.mode == "kitty" else ""
            self._w(f"\x1b[{self.total}A\r\x1b[0J{tail}\x1b[?25h")  # back to the first reserved line, wipe it
            self.out.flush()
        except Exception:
            pass

    def _loop(self) -> None:
        try:
            x, step, t0, n = 0.0, 1, time.monotonic(), 0
            while not self.stop_event.wait(1.0 / FPS):
                max_x = max(0, self.console.width - self.cols - 1)
                x += step * SPEED / FPS
                if x >= max_x:
                    x, step = float(max_x), -1
                elif x <= 0:
                    x, step = 0.0, 1
                n += 1
                frame = RUN_FRAMES[(n // 3) % len(RUN_FRAMES)]
                self._draw(int(x), frame, flip=step < 0, hop=(n // 2) % 2 == 0, t=time.monotonic() - t0)
        except Exception:
            pass  # a drawing problem must never break the actual work

    def _draw(self, x: int, frame: int, flip: bool, hop: bool, t: float) -> None:
        pic = self._picture(frame, flip, hop)
        dots = "." * (int(t * 2.5) % 4)
        status = f"\x1b[38;2;124;92;255m{self.text}\x1b[38;2;20;214;196m\x1b[1m{dots}\x1b[0m"
        move = f"\x1b[{x}C" if x else ""
        buf = [f"\x1b[?2026h\x1b[{self.total}A\r\x1b[0J"]  # synchronized update: up to the top, wipe the block
        if self.mode == "blocks":
            for line in pic:
                buf.append(f"{move}{line}\n\r")
        else:
            buf.append(f"\x1b7{move}{pic}\x1b8\x1b[{self.rows}B\r")
        buf.append(f"{status}\n\r\x1b[?2026l")
        self._w("".join(buf))
        self.out.flush()

