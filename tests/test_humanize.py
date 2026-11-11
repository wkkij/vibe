"""Проверки человекоподобного ввода (core/humanize.py) на поддельной странице, без браузера."""
import asyncio
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import humanize  # noqa: E402


class FakeMouse:
    def __init__(self):
        self.log = []

    async def move(self, x, y):
        self.log.append(("move", x, y))

    async def down(self):
        self.log.append(("down",))

    async def up(self):
        self.log.append(("up",))


class FakeKeyboard:
    def __init__(self):
        self.log = []

    async def type(self, ch):
        self.log.append(("type", ch))

    async def press(self, key):
        self.log.append(("press", key))

    async def down(self, key):
        self.log.append(("down", key))

    async def up(self, key):
        self.log.append(("up", key))

    async def insert_text(self, text):
        self.log.append(("insert", len(text)))


class FakePage:
    def __init__(self):
        self.mouse, self.keyboard = FakeMouse(), FakeKeyboard()

    async def evaluate(self, *_a, **_k):
        return [1200, 800]


class FakeLocator:
    def __init__(self, page, covered=False):
        self.page, self.covered, self.fallback = page, covered, False

    async def scroll_into_view_if_needed(self, timeout=0):
        pass

    async def is_visible(self):
        return True

    async def is_enabled(self):
        return True

    async def bounding_box(self):
        return {"x": 400, "y": 300, "width": 120, "height": 40}

    async def evaluate(self, *_a):
        return not self.covered

    async def click(self, timeout=0):
        self.fallback = True


def test_bezier_path_ends_exactly_and_curves():
    rng = random.Random(7)
    pts = humanize.bezier_path((10, 10), (500, 300), 40, rng)
    assert len(pts) == 40 and pts[-1] == (500, 300)
    # the path is not a straight line: some point is clearly off the straight segment
    def off(p):
        return abs((500 - 10) * (10 - p[1]) - (10 - p[0]) * (300 - 10)) / math.hypot(490, 290)
    assert max(off(p) for p in pts) > 3
    assert humanize.bezier_path((5, 5), (5, 5), 10) == [(5, 5)]


def test_human_click_moves_then_presses_inside_element():
    async def go():
        page = FakePage()
        loc = FakeLocator(page)
        await humanize.HumanInput().click(loc)
        return page, loc
    page, loc = asyncio.run(go())
    moves = [e for e in page.mouse.log if e[0] == "move"]
    assert len(moves) >= 10 and not loc.fallback
    assert [e[0] for e in page.mouse.log if e[0] != "move"] == ["down", "up"]
    x, y = moves[-1][1], moves[-1][2]
    assert 400 <= x <= 520 and 300 <= y <= 340  # lands inside the element, not necessarily in the centre


def test_human_click_falls_back_when_covered():
    async def go():
        page = FakePage()
        loc = FakeLocator(page, covered=True)
        await humanize.HumanInput().click(loc)
        return page, loc
    page, loc = asyncio.run(go())
    assert loc.fallback and not any(e[0] == "down" for e in page.mouse.log)


def test_typing_uses_shift_enter_and_long_text_uses_insert():
    async def go():
        page = FakePage()
        hi = humanize.HumanInput()
        await hi.type_text(page, "a\nb")
        short = list(page.keyboard.log)
        page.keyboard.log.clear()
        await hi.fill(page, "x" * 9000)
        return short, page.keyboard.log
    short, long_ = asyncio.run(go())
    assert ("type", "a") in short and ("down", "Shift") in short and ("press", "Enter") in short
    assert all(e[0] == "insert" for e in long_) and sum(e[1] for e in long_) == 9000
