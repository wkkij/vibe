"""Автодополнение команд и аргументов (prompt_toolkit). Если библиотеки нет — возвращает None."""
from typing import Callable, List

from .commands import COMMANDS, LEVEL_WORDS


def make_session(history_path: str, get_models: Callable[[], List[str]]):
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.history import FileHistory
    except ImportError:
        return None

    static_args = {
        "provider": ["gemini", "claude", "aistudio"],
        "autocontext": ["on", "off"],
        "promptstyle": ["auto", "classic", "concise", "strict", "mentor", "pair", "friendly"],
        "transport": ["auto", "file", "paste", "inline", "zip", "base64"],
        "reasoning": ["low", "medium", "high", "off", "default"],
    }

    class VibeCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            if " " not in text:
                for name, desc in COMMANDS.items():
                    if name.startswith(text[1:].lower()):
                        yield Completion("/" + name, start_position=-len(text), display_meta=desc)
                return
            cmd, _, rest = text[1:].partition(" ")
            cmd = cmd.lower()
            if cmd in static_args:
                word = rest.lower()
                for a in static_args[cmd]:
                    if a.startswith(word):
                        yield Completion(a, start_position=-len(rest))
            elif cmd == "model":
                done = rest.split()
                if done and done[-1].lower() in LEVEL_WORDS and rest.endswith(" ") is False:
                    return
                has_model = bool(done) and (rest.endswith(" ") or len(done) > 1)
                if has_model:  # модель уже введена — предлагаем уровень
                    word = "" if rest.endswith(" ") else done[-1].lower()
                    for lv in ("low", "medium", "high"):
                        if lv.startswith(word):
                            yield Completion(lv, start_position=-len(word))
                else:
                    word = rest.lower()
                    for m in get_models():
                        if m.lower().startswith(word) or word in m.lower():
                            yield Completion(m, start_position=-len(rest))

    return PromptSession(history=FileHistory(history_path), completer=VibeCompleter(), complete_while_typing=True)
