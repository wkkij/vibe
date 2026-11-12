"""Screen-only Humanize driver (no CDP / Playwright connection to Chrome).

Drives an open Chrome window strictly like a person at the computer:
- finds and activates the Chrome window with the chat (Win32 API via core/osinput.py);
- moves the real mouse cursor along curved Bezier paths (`bezier_path` from core/humanize.py);
- types short messages key by key or pastes longer messages in chunks via the clipboard;
- reads the model's answer by clicking a neutral blank spot on the page and pressing Ctrl+A, Ctrl+C.
"""
import asyncio
import math
import os
import random
import re
import time
from typing import Iterable, List, Optional, Tuple

from . import osinput
from .events import GenerationStopped, clear_stop, emit, stop_requested
from .humanize import Point, _clamp, bezier_path
from .i18n import t

VK_RETURN, VK_SHIFT, VK_CONTROL = 0x0D, 0x10, 0x11
VK_A, VK_C, VK_O = 0x41, 0x43, 0x4F

TITLE_HINTS = {
    "gemini": ("gemini", "google"),
    "claude": ("claude", "anthropic"),
    "aistudio": ("ai studio", "aistudio", "google ai"),
}

# Trailing UI footers that get selected when copying the whole page with Ctrl+A
FOOTER_PATTERNS = [
    re.compile(r"\n*\s*(?:Gemini может ошибаться|Gemini can make mistakes|Google Gemini может допускать ошибки)[\s\S]*$", re.I),
    re.compile(r"\n*\s*(?:Claude can make mistakes|Claude может ошибаться)[\s\S]*$", re.I),
    re.compile(r"\n*\s*(?:Use code with caution|Используйте код с осторожностью)[\s\S]*$", re.I),
    re.compile(r"\n*\s*(?:Введите запрос для Gemini|Ask Gemini|Спросите Gemini|Reply to Claude|Напишите Claude|Type something|Enter a prompt)[\s\S]*$", re.I),
]


def _strip_footers(text: str) -> str:
    out = text.strip()
    for pat in FOOTER_PATTERNS:
        out = pat.sub("", out).strip()
    return out


def _normalize_code_blocks(text: str) -> str:
    """Clean up common artifacts from copying rendered chat pages (non-breaking spaces, stray Copy buttons)."""
    text = text.replace("\u00a0", " ").replace("\r\n", "\n")
    text = re.sub(r"(?m)^\s*(?:Copy code|Копировать код|Copy|Копировать)\s*\n(?=\s*<<<)", "", text)
    return text.strip()


def extract_answer(text: str, base_text: str, message: str) -> str:
    """Extract the model's latest answer from the full-page text copied via Ctrl+A, Ctrl+C.

    1. Primary method: locate the last occurrence of the sent message's tail (~60 non-space chars, words joined by \\s+)
       and take everything after it.
    2. Fallback (e.g. when the chat UI collapses a long prompt): strip the common prefix shared with `base_text`
       (the page snapshot taken before sending).
    3. Strip trailing chat UI footers/disclaimers.
    """
    if not text:
        return ""
    norm_text = _normalize_code_blocks(text)
    candidate = ""

    # 1) Search for the tail of the sent message
    msg_clean = (message or "").strip()
    if msg_clean:
        words = msg_clean.split()
        tail_words: List[str] = []
        chars = 0
        for w in reversed(words):
            tail_words.append(w)
            chars += len(w)
            if chars >= 60 or len(tail_words) >= 12:
                break
        tail_words.reverse()
        if tail_words:
            pat_str = r"\s+".join(re.escape(w) for w in tail_words)
            matches = list(re.finditer(pat_str, norm_text))
            if matches:
                candidate = norm_text[matches[-1].end():].strip()

    # 2) Fallback: remove common prefix with base_text
    if not candidate and base_text:
        norm_base = _normalize_code_blocks(base_text)
        common = 0
        limit = min(len(norm_text), len(norm_base))
        while common < limit and norm_text[common] == norm_base[common]:
            common += 1
        if common > 0:
            # Step back to the last newline so we don't slice a line in half
            nl = norm_text.rfind("\n", 0, common)
            cut = nl + 1 if nl >= 0 else common
            candidate = norm_text[cut:].strip()
            # If the user message is partially visible at the start of the diff, strip its first line
            first_line = msg_clean.splitlines()[0].strip() if msg_clean else ""
            if first_line and len(first_line) >= 12:
                pos = candidate.rfind(first_line)
                if pos != -1 and pos < 400:
                    after_nl = candidate.find("\n", pos + len(first_line))
                    if after_nl != -1:
                        candidate = candidate[after_nl + 1:].strip()

    if not candidate:
        candidate = norm_text

    return _strip_footers(candidate)


class ScreenSession:
    """Drives the browser window using real OS coordinates, mouse curve, keyboard and clipboard."""

    def __init__(self, config):
        if not osinput.available():
            raise RuntimeError(t("Режим Humanize доступен только в Windows."))
        self.config = config
        self.os = osinput.OsInput()
        self.hwnd: Optional[int] = None

    @staticmethod
    async def pause(lo: float, hi: float) -> None:
        await asyncio.sleep(random.uniform(lo, hi))

    def ensure_window(self, provider_key: str, provider_title: str) -> Tuple[int, int, int, int]:
        hints: Iterable[str] = TITLE_HINTS.get(provider_key, (provider_title.lower(), "chrome"))
        hwnd = self.os.find_window(hints)
        if not hwnd:
            raise RuntimeError(
                t("Окно Chrome с чатом {title} не найдено. Откройте браузер, войдите в аккаунт и оставьте вкладку с чатом активной.", title=provider_title)
            )
        if not self.os.activate(hwnd):
            raise RuntimeError(
                t("Не удалось вывести окно Chrome на передний план. Сделайте окно с чатом видимым и повторите.")
            )
        self.hwnd = hwnd
        return self.os.window_rect(hwnd)

    def _rect(self) -> Tuple[int, int, int, int]:
        if not self.hwnd:
            raise RuntimeError("window is not initialized")
        self.os.activate(self.hwnd)
        return self.os.window_rect(self.hwnd)

    async def move_to(self, x: float, y: float, overshoot: bool = True) -> None:
        start = self.os.cursor()
        dist = math.hypot(x - start[0], y - start[1])
        if overshoot and dist > 150 and random.random() < 0.2:
            ux, uy = (x - start[0]) / dist, (y - start[1]) / dist
            k = random.uniform(6, 18)
            await self._travel(start, (x + ux * k, y + uy * k), max(14, min(70, int(dist / 9))))
            await self.pause(0.04, 0.12)
            await self._travel(self.os.cursor(), (x, y), random.randint(5, 9))
        else:
            await self._travel(start, (x, y), max(10, min(70, int(dist / 9))))

    async def _travel(self, start: Point, end: Point, steps: int) -> None:
        for sx, sy in bezier_path(start, end, steps):
            self.os.move(sx, sy)
            await asyncio.sleep(random.uniform(0.006, 0.016))
            cx, cy = self.os.cursor()
            if abs(cx - round(sx)) > 40 or abs(cy - round(sy)) > 40:
                raise RuntimeError(t("Движение мыши прервано пользователем."))

    async def click_at(self, x: float, y: float, jitter: float = 4.0) -> None:
        tx = x + random.uniform(-jitter, jitter)
        ty = y + random.uniform(-jitter, jitter)
        await self.move_to(tx, ty)
        await self.pause(0.06, 0.20)
        self.os.button(True)
        await self.pause(0.045, 0.12)
        self.os.button(False)
        await self.pause(0.06, 0.18)

    def _input_point(self, rect: Tuple[int, int, int, int]) -> Point:
        left, top, right, bottom = rect
        w, h = max(200, right - left), max(200, bottom - top)
        off = getattr(self.config, "human_input_offset", 90) or 90
        x = left + w * 0.5 + random.uniform(-w * 0.08, w * 0.08)
        y = bottom - off + random.uniform(-6, 6)
        return x, _clamp(y, top + 120, bottom - 25)

    def _blank_point(self, rect: Tuple[int, int, int, int]) -> Point:
        left, top, right, bottom = rect
        h = max(200, bottom - top)
        margin = getattr(self.config, "human_blank", 45) or 45
        x = right - margin + random.uniform(-5, 5)
        y = top + h * 0.45 + random.uniform(-18, 18)
        return _clamp(x, left + 40, right - 15), _clamp(y, top + 120, bottom - 140)

    async def type_text(self, text: str) -> None:
        for ch in text:
            if stop_requested():
                clear_stop()
                raise GenerationStopped("")
            if ch == "\n":
                self.os.shift_enter()
                delay = random.uniform(0.15, 0.4)
            else:
                self.os.type_char(ch)
                delay = _clamp(random.lognormvariate(math.log(0.07), 0.45), 0.02, 0.35)
                if ch == " ":
                    delay += random.uniform(0.01, 0.07)
                elif ch in ".,!?;:" and random.random() < 0.3:
                    delay += random.uniform(0.1, 0.3)
                if random.random() < 0.015:
                    delay += random.uniform(0.5, 1.4)
            await asyncio.sleep(delay)

    async def type_or_paste(self, text: str, typed_limit: int = 400) -> None:
        if len(text) <= typed_limit:
            await self.type_text(text)
            return
        i = 0
        while i < len(text):
            if stop_requested():
                clear_stop()
                raise GenerationStopped("")
            size = random.randint(2500, 5000)
            self.os.paste(text[i : i + size])
            i += size
            await self.pause(0.12, 0.35)

    async def copy_page_text(self) -> str:
        """Press Ctrl+A, Ctrl+C and return the copied page text."""
        self.os.set_clipboard("")
        self.os.hotkey(VK_CONTROL, VK_A)
        await self.pause(0.08, 0.16)
        self.os.hotkey(VK_CONTROL, VK_C)
        await self.pause(0.12, 0.22)
        return self.os.get_clipboard()

    async def send_and_read(self, message: str, provider_key: str, provider_title: str, new_chat: bool = False) -> str:
        rect = self.ensure_window(provider_key, provider_title)
        await self.pause(0.25, 0.5)

        if new_chat and provider_key in ("gemini", "claude"):
            self.os.hotkey(VK_CONTROL, VK_SHIFT, VK_O)
            await self.pause(2.5, 3.5)
            rect = self._rect()

        # Take a baseline snapshot of the page before sending
        bx, by = self._blank_point(rect)
        await self.click_at(bx, by)
        base_text = await self.copy_page_text()

        # Click the chat input box, clear any leftover draft, type/paste and send with Enter
        ix, iy = self._input_point(rect)
        await self.click_at(ix, iy)
        await self.pause(0.15, 0.35)
        self.os.select_all_delete()
        await self.pause(0.1, 0.25)
        await self.type_or_paste(message)

        await self.pause(0.6, 1.6)  # reading pause before sending
        emit("phase", phase="sending")
        self.os.press(VK_RETURN)

        # Move focus to the blank margin once, then poll via Ctrl+A, Ctrl+C every 3-4 seconds
        await self.pause(1.2, 1.8)
        rect = self._rect()
        bx, by = self._blank_point(rect)
        await self.click_at(bx, by)

        start = time.time()
        limit = float(os.environ.get("VIBE_RESPONSE_TIMEOUT", "300") or 300)
        emit("phase", phase="waiting")

        stable = 0
        last_ans = ""
        phase = "waiting"

        while time.time() - start < limit:
            await self.pause(3.0, 4.0)
            if stop_requested():
                clear_stop()
                raise GenerationStopped(last_ans.strip())

            self.os.activate(self.hwnd)
            raw = await self.copy_page_text()
            ans = extract_answer(raw, base_text, message)
            elapsed = time.time() - start

            new_phase = "answering" if ans else "thinking"
            if new_phase != phase:
                phase = new_phase
                emit("phase", phase=phase)

            if ans and ans != last_ans:
                emit(
                    "progress",
                    chars=len(ans),
                    elapsed=int(elapsed),
                    text=ans if len(ans) < 150_000 else ans[-150_000:],
                )

            if ans and ans == last_ans and elapsed >= 6.0:
                stable += 1
                if stable >= 2:
                    # Deselect page text with a light click on the blank spot
                    await self.click_at(bx, by)
                    return ans.strip()
            else:
                stable = 0
                last_ans = ans

        if last_ans:
            return last_ans.strip()
        raise TimeoutError(t("Превышено время ожидания ответа от {title}.", title=provider_title))

