"""Проверки перевода: у каждого t("…") есть английский текст, плейсхолдеры совпадают, языки переключаются."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import i18n, mascot  # noqa: E402
from core.commands import COMMANDS, GROUPS  # noqa: E402
from core.config import TRANSPORT_INFO  # noqa: E402
from core.locale_en import EN  # noqa: E402
from core.prompts import STYLE_TITLES, PromptBook  # noqa: E402
from core.providers import MODEL_CATALOG  # noqa: E402

_PH = re.compile(r"\{(\w+)\}")


def _literal_ids():
    """Все строки-аргументы вызовов t("…") в коде CLI."""
    ids = set()
    for f in list((ROOT / "core").glob("*.py")) + [ROOT / "vibe.py"]:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    ids.add(node.args[0].value)
    return ids


def _table_ids():
    """Строки, которые переводятся через t(переменная): описания команд, группы, форматы, каталог моделей, стили."""
    ids = set(COMMANDS.values()) | {title for title, _ in GROUPS} | set(STYLE_TITLES.values())
    ids |= {x for pair in TRANSPORT_INFO.values() for x in pair}
    ids |= {m["desc"] for models in MODEL_CATALOG.values() for m in models}
    return ids


def test_every_message_has_english():
    missing = sorted((_literal_ids() | _table_ids()) - set(EN))
    assert not missing, "нет английского текста для:\n" + "\n".join(missing)


def test_no_stale_catalog_entries():
    stale = sorted(set(EN) - (_literal_ids() | _table_ids()))
    assert not stale, "в locale_en.py есть строки, которых нет в коде:\n" + "\n".join(stale)


def test_placeholders_match():
    bad = [ru for ru, en in EN.items() if set(_PH.findall(ru)) != set(_PH.findall(en))]
    assert not bad, "плейсхолдеры не совпадают: " + "; ".join(bad)


def test_english_has_no_cyrillic():
    bad = [en for en in EN.values() if re.search("[а-яА-ЯёЁ]", en)]
    assert not bad, "в английском тексте осталась кириллица: " + "; ".join(bad)


def test_switching_language():
    try:
        i18n.set_lang("ru")
        assert i18n.t("Файл") == "Файл"
        assert i18n.t("Найдено файлов: {n}", n=3) == "Найдено файлов: {n}"[:0] + "Найдено файлов: {n}".replace("{n}", "3")
        i18n.set_lang("en")
        assert i18n.t("Файл") == "File"
        assert i18n.t("Неизвестная команда.") == "Unknown command."
        assert i18n.t("нет такой строки") == "нет такой строки"  # нет перевода -> исходный текст
    finally:
        i18n.set_lang("en")


def test_resolve_language(monkeypatch=None):
    assert i18n.resolve_language("ru") == "ru"
    assert i18n.resolve_language("en") == "en"
    assert i18n.resolve_language("auto") in i18n.LANGS
    assert i18n.resolve_language("") in i18n.LANGS
    assert i18n.resolve_language("de") in i18n.LANGS


def test_prompts_follow_language():
    ru = PromptBook("classic", lang="ru")
    en = PromptBook("classic", lang="en")
    assert "КРИТИЧЕСКИЕ ПРАВИЛА" in ru.system_patcher()
    assert "CRITICAL CODE FORMATTING RULES" in en.system_patcher()
    # маркеры формата патчей, на которые опирается парсер, одинаковы в обоих языках
    for marker in ("<<<FILE:", "<<<CREATE:", "<<<DELETE:", "<<<RUN_CMD>>>", "<<<END_CMD>>>", "<<<<<<< SEARCH", ">>>>>>> REPLACE"):
        assert marker in ru.system_patcher() and marker in en.system_patcher()
    assert "{canary}" not in en.canary("abc123") and "CONTEXT_OK abc123" in en.canary("abc123")
    for kind in ("task", "heal", "repair", "need_files", "cont", "dirty", "approve", "revise", "plan_task"):
        assert kind in en.pack.CLASSIC and kind in en.pack.POOLS
        assert len(en.pack.POOLS[kind]) == len(ru.pack.POOLS[kind]), kind


def test_prompt_prompts_dynamic_language():
    try:
        i18n.set_lang("en")
        book = PromptBook("classic")
        assert "Principal Software Engineer" in book.system_patcher()
        assert "Ты —" not in book.system_patcher()
        i18n.set_lang("ru")
        assert "Ты —" in book.system_patcher()
    finally:
        i18n.set_lang("en")


def test_mascot_shapes():
    for uni in (True, False):
        for mood in mascot.MOODS:
            art = mascot.art(mood, uni)
            assert len(art) == (mascot.ART_ROWS if uni else mascot.HEIGHT_PX) and len({len(r) for r in art}) == 1, (mood, uni)
            assert len(art[0]) == mascot.ART_COLS
            face = mascot.face(mood, uni)
            assert face.startswith("[") and face.endswith("]")
    assert all(ord(c) < 128 for row in mascot.art("idle", False) for c in row)


def test_mascot_frames_and_animation():
    from core import sprites
    assert len(sprites.FRAMES) == 22
    for fr in sprites.FRAMES:
        assert len(fr) == mascot.HEIGHT_PX and all(len(r) == mascot.WIDTH_PX for r in fr)
        assert all(c == "." or c in sprites.PALETTE for r in fr for c in r)
    for mood in mascot.MOODS:
        seq = mascot.animation(mood)
        assert seq and all(0 <= f < len(sprites.FRAMES) and d > 0 for f, d in seq), mood


def test_vibi_run_pictures():
    import io
    import struct
    import zlib
    from core import vibi_run
    cv = vibi_run.canvas(14, flip=True, hop=True)
    assert len(cv) == vibi_run.CANVAS and all(len(r) == vibi_run.CANVAS for r in cv)
    png = vibi_run.encode_png(cv, 4)
    assert png.startswith(b"\x89PNG") and struct.unpack(">II", png[16:24]) == (64, 64)
    sixel = vibi_run.encode_sixel(cv, 6)
    assert sixel.startswith("\x1bP0;1;0q") and sixel.endswith("\x1b\\") and '"1;1;96;96' in sixel
    assert vibi_run.encode_kitty(png, 16, 8).startswith("\x1b_G")
    assert vibi_run.encode_iterm(png, 16, 8).startswith("\x1b]1337;File=inline=1")
    assert len(vibi_run.blocks_lines(cv)) == vibi_run.CANVAS // 2
    assert vibi_run.detect_mode({"WT_SESSION": "1"}) == "sixel"
    assert vibi_run.detect_mode({"VIBE_IMAGES": "off"}) == "blocks"
    assert vibi_run.detect_mode({"WT_SESSION": "1", "TMUX": "x"}) == "blocks"
