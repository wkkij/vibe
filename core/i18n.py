"""Interface language (ru / en) for Vibe CLI.

The source strings in the code are Russian (the original project language) and act as message ids, the
same way gettext uses the source text. `t("Русский текст")` returns the English text from `core/locale_en.py`
when the language is English, and the original string when it is Russian. A missing translation falls back to
the source string, so nothing ever breaks; `tests/test_i18n.py` checks that every `t(...)` call has an entry.

Language choice, in order of priority:
    1. `--lang en|ru` / `/lang en|ru`   (saved to .vibe.json as "language")
    2. environment variable VIBE_LANG   (en | ru | auto)
    3. "auto": the operating system language (Russian system -> ru, anything else -> en)

Placeholders use str.format: `t("Найдено файлов: {n}", n=5)`. Rich markup in the text is kept as is.
"""
import locale
import os
from typing import Optional

LANGS = ("en", "ru")
LANG_TITLES = {"en": "English", "ru": "Русский"}
DEFAULT_LANG = "en"

_lang = DEFAULT_LANG
_catalog: Optional[dict] = None


def detect_system_language() -> str:
    """ru if the operating system (or the shell locale) is Russian, otherwise en."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        v = os.environ.get(var, "").lower()
        if v.startswith("ru"):
            return "ru"
        if v.startswith("en"):
            return "en"
    if os.name == "nt":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            return "ru" if (lang_id & 0xFF) == 0x19 else "en"  # 0x19 = LANG_RUSSIAN
        except Exception:
            pass
    try:
        loc = (locale.getlocale()[0] or "").lower()
        if loc.startswith("ru"):
            return "ru"
    except Exception:
        pass
    return DEFAULT_LANG


def resolve_language(pref: Optional[str]) -> str:
    """'en' | 'ru' -> itself; 'auto' / empty / unknown -> VIBE_LANG or the system language."""
    p = (pref or "").strip().lower()
    if p in LANGS:
        return p
    env = os.environ.get("VIBE_LANG", "").strip().lower()
    if env in LANGS:
        return env
    return detect_system_language()


def set_lang(lang: Optional[str]) -> str:
    global _lang
    _lang = resolve_language(lang)
    return _lang


def get_lang() -> str:
    return _lang


def _load() -> dict:
    global _catalog
    if _catalog is None:
        from .locale_en import EN

        _catalog = EN
    return _catalog


def t(msg: str, **kw) -> str:
    """Translate a message id (the Russian source text) into the current language."""
    s = msg if _lang == "ru" else _load().get(msg, msg)
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s
    return s
