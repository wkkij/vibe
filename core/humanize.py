"""Human-like input for the browser chat (Humanize mode, switched on in Vibe IDE).

On Windows the mode imitates a person with real operating-system input (core/osinput.py): the actual cursor travels
along a curved path with easing, jitter and now and then a small overshoot; clicks land on a random point of the
element after a short hover with a realistic press time; text is typed key by key with irregular delays (short
messages) or pasted with a real Ctrl+V in chunks (long text). The page is not asked to produce any of these events.
While it works the program owns the mouse and keyboard, so they should be left alone; if you grab the mouse in the
middle of a move, Humanize notices, stops and the normal action is used instead.

If anything fails (the window is not in focus, the element moved, something covers it, not Windows), the caller
falls back to the normal action, so the mode never makes the tool less reliable. It only makes the input look
natural: it does not guarantee that a service will not notice automation, and automation may be against its terms.
"""
import asyncio
import math
import random
from typing import List, Optional, Tuple

from . import osinput

Point = Tuple[float, float]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def bezier_path(p0: Point, p3: Point, steps: int, rng: random.Random = random) -> List[Point]:
    """Points of a curved path from p0 to p3 (the last point is exactly p3).

    A cubic Bezier with two control points pushed sideways by a random amount; the parameter is eased
    (slow start, fast middle, slow finish) like a real hand movement; small jitter on all but the last point."""
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    dist = math.hypot(dx, dy)
    if dist < 1 or steps < 1:
        return [p3]
    nx, ny = -dy / dist, dx / dist  # unit normal
    bend = dist * 0.18

    def ctrl(frac: float) -> Point:
        off = rng.uniform(-1, 1) * bend
        return (p0[0] + dx * frac + nx * off, p0[1] + dy * frac + ny * off)

    p1, p2 = ctrl(rng.uniform(0.2, 0.4)), ctrl(rng.uniform(0.6, 0.8))
    pts: List[Point] = []
    for i in range(1, steps + 1):
        u = i / steps
        t = 0.5 - 0.5 * math.cos(math.pi * u)  # ease in-out
        mt = 1 - t
        x = mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0]
        y = mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]
        if i < steps:
            x += rng.gauss(0, 0.45)
            y += rng.gauss(0, 0.45)
        pts.append((x, y))
    pts[-1] = p3
    return pts


class HumanInput:
    """Moves the cursor, clicks and types like a person on a Playwright page. Keeps the last cursor position."""

    def __init__(self, use_os: Optional[bool] = None):
        self.pos: Optional[Point] = None          # cursor position in page coordinates
        self.os = None                            # OsInput when real input is used
        if use_os is None:
            use_os = osinput.available()
        if use_os:
            self.os = osinput.OsInput()
        self.m: Optional[dict] = None             # window metrics of the page (OS mode)

    def reset(self) -> None:
        """Forget the cursor position (a new browser connection starts somewhere else)."""
        self.pos = None

    # ------------------------------------------------------------ helpers
    @staticmethod
    async def pause(lo: float, hi: float) -> None:
        await asyncio.sleep(random.uniform(lo, hi))

    async def _metrics(self, page) -> dict:
        self.m = await page.evaluate(
            "() => ({sx: window.screenX, sy: window.screenY, ow: window.outerWidth, oh: window.outerHeight,"
            " iw: window.innerWidth, ih: window.innerHeight, dpr: window.devicePixelRatio, focus: document.hasFocus()})")
        return self.m

    async def prepare(self, page) -> None:
        """OS mode: bring the tab to the front and make sure the browser window really has the focus."""
        if self.os is None:
            return
        for _ in range(3):
            await page.bring_to_front()
            await asyncio.sleep(0.25)
            if (await self._metrics(page)).get("focus"):
                return
        raise RuntimeError("the browser window is not in focus")

    async def _start_pos(self, page) -> Point:
        if self.os is not None:
            m = self.m or await self._metrics(page)
            self.pos = osinput.screen_to_page(m, *self.os.cursor())
            return self.pos
        if self.pos is None:
            try:
                w, h = await page.evaluate("[window.innerWidth, window.innerHeight]")
            except Exception:
                w, h = 1200, 800
            self.pos = (w * random.uniform(0.3, 0.7), h * random.uniform(0.5, 0.8))
        return self.pos

    # ------------------------------------------------------------ cursor
    async def move_to(self, page, x: float, y: float, overshoot: bool = True) -> None:
        start = await self._start_pos(page)
        dist = math.hypot(x - start[0], y - start[1])
        if overshoot and dist > 150 and random.random() < 0.2:
            # fly a little past the target, then come back
            ux, uy = (x - start[0]) / dist, (y - start[1]) / dist
            k = random.uniform(6, 18)
            await self._travel(page, start, (x + ux * k, y + uy * k), max(14, min(70, int(dist / 9))))
            await self.pause(0.04, 0.12)
            await self._travel(page, self.pos, (x, y), random.randint(5, 9))
        else:
            await self._travel(page, start, (x, y), max(10, min(70, int(dist / 9))))

    async def _travel(self, page, start: Point, end: Point, steps: int) -> None:
        if self.os is not None:
            m = await self._metrics(page)
            for px, py in bezier_path(start, end, steps):
                sx, sy = osinput.page_to_screen(m, px, py)
                self.os.move(sx, sy)
                self.pos = (px, py)
                await asyncio.sleep(random.uniform(0.006, 0.016))
                cx, cy = self.os.cursor()
                if abs(cx - round(sx)) > 40 or abs(cy - round(sy)) > 40:
                    raise RuntimeError("the mouse was moved by the user")
            return
        for px, py in bezier_path(start, end, steps):
            await page.mouse.move(px, py)
            self.pos = (px, py)
            await asyncio.sleep(random.uniform(0.004, 0.013))

    async def drift(self, page) -> None:
        """A small idle cursor movement (used while waiting for the answer). Not done with the real cursor."""
        if self.os is not None:
            return
        try:
            x0, y0 = await self._start_pos(page)
            w, h = await page.evaluate("[window.innerWidth, window.innerHeight]")
            ang, d = random.uniform(0, 2 * math.pi), random.uniform(20, 120)
            x = _clamp(x0 + math.cos(ang) * d, 5, w - 5)
            y = _clamp(y0 + math.sin(ang) * d, 5, h - 5)
            await self._travel(page, (x0, y0), (x, y), random.randint(8, 18))
        except Exception:
            pass

    # ------------------------------------------------------------ click
    async def click(self, loc, timeout: int = 8000) -> None:
        """Human click on a Playwright locator; falls back to `loc.click()` if the human click cannot be done safely."""
        page = loc.page
        try:
            await self.prepare(page)
            await loc.scroll_into_view_if_needed(timeout=timeout)
            if not (await loc.is_visible() and await loc.is_enabled()):
                raise RuntimeError("not clickable yet")
            box = await loc.bounding_box()
            if not box or box["width"] < 2 or box["height"] < 2:
                raise RuntimeError("no box")
            fx = _clamp(random.gauss(0.5, 0.17), 0.15, 0.85)
            fy = _clamp(random.gauss(0.5, 0.17), 0.2, 0.8)
            x, y = box["x"] + box["width"] * fx, box["y"] + box["height"] * fy
            await self.move_to(page, x, y)
            # make sure the thing under the cursor is really this element (not an overlay)
            hit = await loc.evaluate(
                "(el, p) => { const h = document.elementFromPoint(p[0], p[1]); return !!h && (el === h || el.contains(h) || h.contains(el)); }",
                [x, y],
            )
            if not hit:
                raise RuntimeError("covered")
            await self.pause(0.06, 0.22)       # hover before pressing
            if self.os is not None:
                self.os.button(True)
                await self.pause(0.045, 0.13)  # how long a finger holds the button
                self.os.button(False)
            else:
                await page.mouse.down()
                await self.pause(0.045, 0.13)
                await page.mouse.up()
            self.pos = (x, y)
            await self.pause(0.05, 0.18)
        except Exception:
            await loc.click(timeout=timeout)

    # ------------------------------------------------------------ typing
    async def type_text(self, page, text: str) -> None:
        """Type with real key events and irregular rhythm. Newlines become Shift+Enter (plain Enter would send)."""
        if self.os is not None:
            await self.prepare(page)
        for ch in text:
            if ch == "\n":
                if self.os is not None:
                    self.os.shift_enter()
                else:
                    await page.keyboard.down("Shift")
                    await page.keyboard.press("Enter")
                    await page.keyboard.up("Shift")
                delay = random.uniform(0.15, 0.4)
            else:
                if self.os is not None:
                    self.os.type_char(ch)
                else:
                    await page.keyboard.type(ch)
                delay = _clamp(random.lognormvariate(math.log(0.07), 0.45), 0.02, 0.35)
                if ch == " ":
                    delay += random.uniform(0.01, 0.07)
                elif ch in ".,!?;:" and random.random() < 0.3:
                    delay += random.uniform(0.1, 0.3)
                if random.random() < 0.015:
                    delay += random.uniform(0.5, 1.4)  # a moment of thought
            await asyncio.sleep(delay)

    async def insert_long(self, page, text: str) -> None:
        """Long text: pasted in chunks with short pauses (like pasting several pieces)."""
        if self.os is not None:
            await self.prepare(page)
        i = 0
        while i < len(text):
            size = random.randint(2500, 5000)
            if self.os is not None:
                self.os.paste(text[i:i + size])
            else:
                await page.keyboard.insert_text(text[i:i + size])
            i += size
            await self.pause(0.1, 0.35)

    async def clear(self, page) -> None:
        """Select everything in the focused field and delete it."""
        if self.os is not None:
            await self.prepare(page)
            self.os.select_all_delete()
        else:
            await page.keyboard.press("ControlOrMeta+A")
            await page.keyboard.press("Backspace")
        await self.pause(0.1, 0.3)

    async def fill(self, page, text: str, typed_limit: int = 400) -> None:
        if len(text) <= typed_limit:
            await self.type_text(page, text)
        else:
            await self.insert_long(page, text)

