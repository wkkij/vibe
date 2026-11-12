"""Машинно-читаемый протокол между Vibe CLI и Vibe IDE.

В режиме IDE (переменная окружения VIBE_IDE=1) CLI печатает события одной строкой:

    @@VIBE {"t": "phase", "phase": "thinking"}

IDE разбирает их и рисует интерфейс (карточки ответов, статус модели, список патчей).
Всё остальное, что попало в stdout, IDE показывает в «Журнале».

Типы событий (поле "t"):
    hello     — CLI запущен: provider, model, auto_context, prompt_style, ...
    phase     — этап работы: packing | selecting | sending | waiting | thinking | answering |
                applying | verifying | healing | checking_ui | idle
    context   — что ушло в чат: files, tokens, mode (all|auto), selected[], total_files
    progress  — живой прогресс ответа: chars, elapsed, tail
    answer    — готовый ответ модели: text, title, kind (answer|plan|repair|heal|partial), stopped
    patch     — результат применения: file, action, message, blocks
    cmd       — терминальная команда: command, status (run|ok|fail), code, output
    verify    — проверка сборки: command, attempt, total, ok, output
    ask       — вопрос пользователю: kind (confirm|input), text, default
    models    — список моделей: provider, current, entries[], levels[]
    setting   — изменение настройки: key, value
    log       — строка журнала: level (info|ok|warn|err|dim), text
    stopped   — генерация остановлена пользователем

Остановка ответа: IDE создаёт файл, путь которого лежит в VIBE_STOP_FILE; мост проверяет его
в цикле ожидания, нажимает «Stop» на странице провайдера и возвращает частичный ответ.
"""
import json
import os
import re
import sys
from typing import Any

from .i18n import t

PREFIX = "@@VIBE "

_MARKUP_RE = re.compile(r"\[/?[a-zA-Z#][^\[\]]*\]")


def ide_mode() -> bool:
    return bool(os.environ.get("VIBE_IDE"))


def emit(kind: str, /, **data: Any) -> None:
    """Отправляет событие в IDE. Вне режима IDE ничего не делает."""
    if not ide_mode():
        return
    payload = {"t": kind}
    payload.update(data)
    try:
        sys.stdout.write(PREFIX + json.dumps(payload, ensure_ascii=True, default=str) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def strip_markup(text: str) -> str:
    """Убирает rich-разметку ([bold], [/dim] …) для обычного текста."""
    try:
        from rich.text import Text

        return Text.from_markup(text).plain
    except Exception:
        return _MARKUP_RE.sub("", text)


# ---------------------------------------------------------------- остановка ответа

def stop_file() -> str:
    return os.environ.get("VIBE_STOP_FILE", "")


def stop_requested() -> bool:
    f = stop_file()
    return bool(f) and os.path.exists(f)


def clear_stop() -> None:
    f = stop_file()
    if f:
        try:
            os.remove(f)
        except OSError:
            pass


class GenerationStopped(Exception):
    """Пользователь остановил генерацию. partial — то, что модель успела написать."""

    def __init__(self, partial: str = ""):
        super().__init__(t("Генерация остановлена пользователем"))
        self.partial = partial

