"""Look of Vibe CLI: colours, banner with the Vibi mascot, help screen, prompt, «working» animation.

Everything here is presentation only. The brand colours are the same as in Vibe IDE (violet -> teal).
In IDE mode (VIBE_IDE=1) the CLI sends events instead and none of this is drawn.
"""
import html
import random
import time
from contextlib import contextmanager
from typing import Dict, List

from rich import box
from rich.align import Align
from rich.console import Group
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import mascot, vibi_run
from .sprites import PALETTE
from .i18n import LANG_TITLES, get_lang, t

BRAND = "#7c5cff"    # violet
BRAND2 = "#14d6c4"   # teal
OK = "#3ddc97"
WARN = "#f5b84a"
ERR = "#ff6b7a"
MUTED = "dim"

# panel kind -> (border colour, mood of Vibi in the title)
KIND_STYLE: Dict[str, tuple] = {
    "answer": (BRAND2, "happy"),
    "plan": (WARN, "think"),
    "repair": (WARN, "work"),
    "heal": (WARN, "work"),
    "partial": (WARN, "sleep"),
    "error": (ERR, "error"),
    "info": (BRAND, "idle"),
}

_ICONS = {"ok": ("✓", "+"), "err": ("✗", "x"), "warn": ("!", "!"), "info": ("•", "-"), "go": ("❯", ">"), "arrow": ("→", "->")}


def icon(name: str) -> str:
    return _ICONS[name][0 if mascot.unicode_ok() else 1]


# ---------------------------------------------------------------- status lines (rich markup strings)

def ok(text: str) -> str:
    return f"[{OK}]{icon('ok')}[/] {text}"


def err(text: str) -> str:
    return f"[{ERR}]{icon('err')}[/] {text}"


def warn(text: str) -> str:
    return f"[{WARN}]{icon('warn')}[/] {text}"


def info(text: str) -> str:
    return f"[{BRAND2}]{icon('info')}[/] {text}"


def step(text: str) -> str:
    """A bold step header, e.g. «Phase 1: planning»."""
    return f"[bold {BRAND}]{icon('go')}[/] [bold]{text}[/bold]"


def dim(text: str) -> str:
    return f"[dim]{text}[/dim]"


def vibi_says(text: str, mood: str = "idle") -> str:
    """One line spoken by Vibi: (•ω•) text."""
    return f"[bold {BRAND2}]{mascot.face(mood)}[/] {text}"


# ---------------------------------------------------------------- text helpers

def gradient(text: str, c1: str = BRAND, c2: str = BRAND2, bold: bool = True) -> Text:
    """Per-letter gradient between two hex colours."""
    out = Text()
    n = max(1, len(text) - 1)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    for i, ch in enumerate(text):
        k = i / n
        rgb = "#" + "".join(f"{round(a[j] + (b[j] - a[j]) * k):02x}" for j in range(3))
        out.append(ch, style=f"bold {rgb}" if bold else rgb)
    return out


def _art_text(mood: str = "idle", frame: int = None) -> Text:
    """The big pixel Vibi in its real colours (half-block characters, two columns per pixel)."""
    txt = Text()
    px = mascot.grid(mascot.still(mood) if frame is None else frame)
    if not mascot.unicode_ok():
        for row in px:
            for c in row:
                txt.append(mascot._ASCII_PIXELS[c], style=f"bold {PALETTE[c]}" if c in PALETTE else "")
            txt.append("\n")
        txt.rstrip()
        return txt
    for y in range(0, mascot.HEIGHT_PX, 2):
        for x in range(mascot.WIDTH_PX):
            ch, fg, bg = mascot.cell(px[y][x], px[y + 1][x])
            style = ""
            if fg:
                style = PALETTE[fg] + (f" on {PALETTE[bg]}" if bg else "")
            txt.append(ch * 2, style=style)
        txt.append("\n")
    txt.rstrip()
    return txt


# ---------------------------------------------------------------- banner

def _tips() -> List[str]:
    return [
        t("Опишите задачу своими словами — Vibi соберёт контекст и применит патчи."),
        t("/plan <задача> — сначала план, потом код."),
        t("/undo откатывает последний патч, если что-то пошло не так."),
        t("/model и /reasoning меняют модель и уровень рассуждений."),
        t("/lang en|ru переключает язык интерфейса."),
        t("Tab дополняет команды и названия моделей."),
        t("/help — список всех команд."),
    ]


def banner(orch, version: str, width: int, mood: str = "idle", frame: int = None, tip: str = None) -> Panel:
    c = orch.config
    wide = width >= 78

    def row(label: str, value: str) -> tuple:
        return (f"[bold {BRAND2}]{label}[/]", value)

    verify = f"[yellow]{c.verify_cmd}[/yellow]" if c.verify_cmd else dim(t("не задана (укажите через /verify_cmd)"))
    rows = [
        row(t("Проект"), str(orch.root)),
        row(t("Провайдер"), f"[bold {BRAND}]{orch.title}[/]  {dim('(/provider)')}"),
        row(t("Модель"), f"[bold]{c.model or t('по умолчанию')}[/bold]  {dim('(/model)')}"),
        row(t("Рассуждения"), f"[bold]{c.reasoning or t('по умолчанию')}[/bold]  {dim('(/reasoning)')}"),
        row(t("Контекст"), f"{c.transport}  {dim('(/transport)')}"),
        row(t("Проверка"), verify),
        row(t("Авто-исправление"), t("до {n} попыток", n=c.max_heal_retries)),
        row(t("Язык"), f"{LANG_TITLES.get(get_lang(), get_lang())}  {dim('(/lang)')}"),
    ]
    rows_t = Table.grid(padding=(0, 2))
    rows_t.add_column(no_wrap=True)
    rows_t.add_column(overflow="fold")
    for label, value in rows:
        rows_t.add_row(label, value)
    title_line = Text()
    title_line.append_text(gradient("Vibe CLI"))
    title_line.append(f"  {version}  ", style="dim")
    title_line.append(" beta ", style=f"bold black on {BRAND2}")
    info_t = Group(title_line, Text.from_markup(dim(t("Локальный вайбкодер на вашей подписке — без платного API"))), Text(""), rows_t)

    greeting = vibi_says(t("Привет! Что будем делать?"), "idle")
    if wide:
        grid = Table.grid(padding=(0, 3))
        grid.add_column(no_wrap=True)
        grid.add_column()
        grid.add_row(Align(_art_text(mood, frame), vertical="middle"), info_t)
        body = Group(grid, Text(""), Text.from_markup(greeting))
    else:
        body = Group(info_t, Text(""), Text.from_markup(greeting))

    tip = dim(t("Совет") + ": " + (tip or random.choice(_tips())))
    return Panel(
        Group(body, Text(""), Text.from_markup(tip)),
        box=box.ROUNDED,
        border_style=BRAND,
        padding=(1, 2),
        title=f"[bold {BRAND2}]{mascot.face('idle')}[/] [bold]Vibe[/bold]",
        title_align="left",
        subtitle=dim("/plan  /fix  /undo  /context  /model  /lang  /help  /exit"),
        subtitle_align="right",
    )


def show_banner(console, orch, version: str, seconds: float = 3.2) -> None:
    """Print the banner. In a terminal Vibi plays her idle animation (blinks, looks around) for a few seconds
    and then stays on the still frame. VIBE_NO_ANIM=1 turns the animation off."""
    width = console.width
    if not (console.is_terminal and mascot.animation_enabled() and width >= 78):
        console.print(banner(orch, version, width))
        return
    seq = mascot.animation("idle")
    try:
        tip = random.choice(_tips())  # chosen once, so that it does not change between frames
        with Live(banner(orch, version, width, frame=seq[0][0], tip=tip), console=console, refresh_per_second=20) as live:
            end = time.monotonic() + seconds
            i = 0
            while time.monotonic() < end:
                frame, dur = seq[i % len(seq)]
                live.update(banner(orch, version, width, frame=frame, tip=tip))
                time.sleep(dur)
                i += 1
            live.update(banner(orch, version, width, frame=seq[0][0], tip=tip))
    except Exception:
        console.print(banner(orch, version, width))


# ---------------------------------------------------------------- help

def help_panel(groups, describe) -> Panel:
    """groups: [(title, [command names])], describe(name) -> localized description."""
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column()
    first = True
    for title, names in groups:
        if not first:
            table.add_row("", "")
        first = False
        table.add_row(f"[bold {BRAND}]{title}[/]", "")
        for name in names:
            table.add_row(f"  [bold {BRAND2}]/{name}[/]", escape(describe(name)))
    table.add_row("", "")
    table.add_row(f"  [bold {BRAND2}]<{t('текст')}>[/]", escape(t("задача: упаковать проект → модель → патчи → проверка")))
    return Panel(
        table,
        box=box.ROUNDED,
        border_style=BRAND,
        title=f"[bold {BRAND2}]{mascot.face('happy')}[/] [bold]{t('Команды')}[/bold]",
        title_align="left",
        padding=(1, 2),
    )


# ---------------------------------------------------------------- panels and tables

def answer_panel(renderable, title: str, kind: str = "answer") -> Panel:
    border, mood = KIND_STYLE.get(kind, KIND_STYLE["answer"])
    return Panel(
        renderable,
        box=box.ROUNDED,
        border_style=border,
        title=f"[bold {border}]{mascot.face(mood)}[/] [bold]{title}[/bold]",
        title_align="left",
        padding=(1, 2),
    )


def error_panel(renderable, title: str) -> Panel:
    return answer_panel(renderable, title, "error")


def info_panel(renderable, title: str, border: str = BRAND2) -> Panel:
    return Panel(renderable, box=box.ROUNDED, border_style=border, title=f"[bold]{title}[/bold]", title_align="left", padding=(1, 2))


def new_table(title: str = "", show_lines: bool = False) -> Table:
    return Table(title=title or None, title_style=f"bold {BRAND}", box=box.ROUNDED, border_style=BRAND, header_style=f"bold {BRAND2}", show_lines=show_lines)


# ---------------------------------------------------------------- prompt

def prompt_markup(mood: str = "idle") -> str:
    """rich markup of the input prompt (used when prompt_toolkit is not available)."""
    return f"\n[bold {BRAND2}]{mascot.face(mood)}[/] [bold {BRAND}]vibe[/] [dim]{icon('go')}[/dim]"


def prompt_html(mood: str = "idle") -> str:
    """prompt_toolkit HTML of the same prompt."""
    f = html.escape(mascot.face(mood))
    return f'\n<style fg="{BRAND2}"><b>{f}</b></style> <style fg="{BRAND}"><b>vibe</b></style> <style fg="ansibrightblack">{html.escape(icon("go"))}</style> '


# ---------------------------------------------------------------- «working» animation

def _register_spinner() -> str:
    try:
        from rich._spinners import SPINNERS

        SPINNERS.setdefault("vibi", {"interval": 220, "frames": mascot.work_frames()})
        return "vibi"
    except Exception:
        return "dots"


@contextmanager
def working(console, text: str, enabled: bool = True):
    """Vibi runs across the terminal while the model is answering (terminal only): as a picture where the terminal
    can show images, otherwise as colour pixels; on small or plain terminals a small blinking face next to the
    status text. See core/vibi_run.py."""
    if not enabled or not console.is_terminal:
        yield
        return
    mode = vibi_run.pick_mode(console)
    if mode:
        runner = vibi_run.VibiRunner(console, text, mode)
        runner.start()
        try:
            yield
        finally:
            runner.stop()
        return
    status = console.status(f"[{BRAND}]{text}[/]", spinner=_register_spinner(), spinner_style=f"bold {BRAND2}")
    status.start()
    try:
        yield
    finally:
        status.stop()
