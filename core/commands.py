"""Разбор ввода пользователя: команды, префиксы, опечатки, аргументы /model. Без внешних зависимостей."""
import difflib
from typing import Dict, List, Optional, Tuple

from .i18n import t

COMMANDS: Dict[str, str] = {
    "plan": "сначала план, потом код: /plan <задача>",
    "model": "модель и уровень: /model [имя|номер] [low|medium|high]",
    "reasoning": "уровень рассуждений: /reasoning low|medium|high|off",
    "provider": "ИИ-провайдер: /provider gemini|claude|aistudio",
    "autocontext": "автоподбор контекста по задаче: /autocontext on|off",
    "autocontext_set": "лимиты автоподбора: /autocontext_set <файлов> [токенов]",
    "promptstyle": "тексты промптов: /promptstyle auto|classic",
    "attach": "прикрепить файл к следующему сообщению: /attach <путь> (zip, png, jpg, webp, gif)",
    "attach_clear": "убрать все вложения",
    "yolo": "без подтверждений: /yolo on|off",
    "human": "человекоподобный ввод в браузере (курсор, набор текста): /human on|off",
    "continue": "продолжить остановленный ответ",
    "list_models": "список моделей (для IDE)",
    "transport": "как передавать контекст: auto|file|paste|inline|base64|zip",
    "verify_cmd": "команда проверки после патчей",
    "fix": "прогнать проверку и починить ошибки",
    "check_ui": "проверить фронтенд в headless-браузере",
    "undo": "откатить последний патч",
    "context": "что попадёт в контекст",
    "reset": "новый чат",
    "init": "создать .vibe.json и VIBE.md",
    "lang": "язык интерфейса: /lang en|ru|auto",
    "help": "список команд",
    "exit": "выход",
}

# Группы для экрана /help: (заголовок, команды). Заголовки и описания переводятся через t().
GROUPS: List[Tuple[str, List[str]]] = [
    ("Задачи", ["plan", "continue", "undo", "fix", "check_ui"]),
    ("Модель", ["provider", "model", "reasoning", "promptstyle"]),
    ("Контекст", ["context", "autocontext", "autocontext_set", "transport", "attach", "attach_clear"]),
    ("Безопасность", ["yolo", "human", "verify_cmd"]),
    ("Сессия", ["reset", "init", "lang", "help", "exit"]),
]


def describe(name: str) -> str:
    """Описание команды на текущем языке интерфейса."""
    return t(COMMANDS.get(name, ""))


def help_groups() -> List[Tuple[str, List[str]]]:
    return [(t(title), names) for title, names in GROUPS]
ALIASES = {"new": "reset", "quit": "exit", "q": "exit"}

# слова, которые считаются уровнем рассуждений, если стоят последними после названия модели
LEVEL_WORDS = {
    "off", "none", "min", "minimal", "low", "medium", "mid", "standard", "high", "max", "extended",
    "выкл", "низкий", "средний", "высокий",
}


def resolve(text: str) -> Tuple[str, str, str, List[str]]:
    """-> (kind, command, arg, hints)

    kind: task | command | unknown | ambiguous
    Команда по однозначному префиксу раскрывается (/und -> undo; неоднозначные префиксы вроде /re возвращают список вариантов).
    """
    text = text.strip()
    if not text.startswith("/"):
        return "task", "", text, []

    head, _, arg = text[1:].partition(" ")
    name = head.lower()
    arg = arg.strip()
    name = ALIASES.get(name, name)
    if name in COMMANDS:
        return "command", name, arg, []

    prefix = [c for c in COMMANDS if c.startswith(name)] if name else []
    if len(prefix) == 1:
        return "command", prefix[0], arg, []
    if len(prefix) > 1:
        return "ambiguous", "", arg, prefix
    close = difflib.get_close_matches(name, list(COMMANDS) + list(ALIASES), n=3, cutoff=0.5)
    return "unknown", "", arg, [ALIASES.get(c, c) for c in close]


def parse_model_args(arg: str) -> Tuple[str, str]:
    """`3.1 pro high` -> ("3.1 pro", "high"); `2` -> ("2", ""); `thinking` -> ("thinking", "")."""
    tokens = arg.split()
    if len(tokens) >= 2 and tokens[-1].lower() in LEVEL_WORDS:
        return " ".join(tokens[:-1]), tokens[-1].lower()
    return arg.strip(), ""
