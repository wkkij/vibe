"""Профили веб-чатов (Gemini / Claude / Google AI Studio): селекторы интерфейса и ключевые слова для уровней рассуждений.

Интерфейсы сайтов меняются — любой параметр можно переопределить в .vibe.json:
  "selector_overrides": {"claude": {"editor": "div.ProseMirror"}}
"""
from dataclasses import dataclass, field, replace
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Provider:
    key: str
    title: str
    url: str
    host: str
    editor: str
    send: str
    stop: str
    plus: str
    chip: str
    model_btn: List[str]
    model_item: str
    response: str            # контейнер ответа ассистента
    response_inner: str      # внутренний узел с текстом (если есть)
    file_input: bool         # есть ли смысл пробовать скрытый input[type=file]
    default_cdp: str
    chrome_profile: str
    reasoning_keywords: Dict[str, List[str]] = field(default_factory=dict)
    # --- необязательные возможности ---
    model_param: str = ""            # имя query-параметра для выбора модели в URL нового чата (?model=…)
    auto_chain: Tuple[str, ...] = ("file", "paste", "inline")  # порядок способов передачи файлов в режиме auto
    response_all: bool = False       # ответ собирается из ВСЕХ узлов response_inner (а не из первого)
    response_exclude: str = ""       # узлы внутри ответа, которые не относятся к тексту (блоки «мыслей» и т.п.)
    thinking: str = ""               # селектор блока «модель думает» (для индикатора состояния)
    static_models: bool = False      # список моделей берётся из каталога, а не из меню на странице

    @property
    def input(self) -> str:
        return self.editor + ", textarea"


GEMINI = Provider(
    key="gemini",
    title="Gemini",
    url="https://gemini.google.com/app",
    host="gemini.google.com",
    editor='div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"]',
    send='button.send-button, button[aria-label*="Send" i], button[aria-label*="Отправить" i]',
    stop='button[aria-label*="Stop" i], button[aria-label*="Остановить" i]',
    plus=(
        'button[aria-label*="upload" i], button[aria-label*="загруз" i], button[aria-label*="Add files" i], '
        'button[aria-label*="Добавить файл" i], button.upload-card-button, [data-test-id="uploader-button"], '
        'button[aria-label*="attach" i]'
    ),
    chip=(
        "uploader-file-preview, uploader-file-preview-container, [data-test-id*=\"file-preview\"], "
        "[class*=\"file-preview\"], [class*=\"attachment-preview\"]"
    ),
    model_btn=[
        '[data-test-id="bard-mode-menu-button"]',
        "button.input-area-switch",
        'button[aria-label*="mode" i]',
        'button[aria-label*="режим" i]',
        'button[aria-label*="model" i]',
        'button[aria-label*="модел" i]',
    ],
    model_item=(
        '[role="menuitemradio"], [role="menuitem"], button.bard-mode-list-button, '
        '[data-test-id^="bard-mode-option"], [role="option"]'
    ),
    response="model-response",
    response_inner="message-content, .markdown",
    file_input=True,
    default_cdp="http://127.0.0.1:9222",
    chrome_profile=".vibe_chrome_profile",
    reasoning_keywords={
        "low": ["fast", "быстр", "flash", "minimal", "low", "низк"],
        "medium": ["medium", "средн", "thinking", "рассужд", "standard"],
        "high": ["high", "высок", "pro", "deep", "think", "extended", "max", "argon"],
    },
)

CLAUDE = Provider(
    key="claude",
    title="Claude",
    url="https://claude.ai/new",
    host="claude.ai",
    editor='div.ProseMirror[contenteditable="true"], [data-testid="chat-input"] [contenteditable="true"], fieldset div[contenteditable="true"]',
    send='button[aria-label*="Send" i], button[aria-label*="Отправить" i]',
    stop='button[aria-label*="Stop" i], button[aria-label*="Остановить" i]',
    plus='button[aria-label*="Add files" i], button[aria-label*="Attach" i], button[aria-label*="Прикрепить" i], [data-testid="input-menu-plus"]',
    chip='[data-testid="file-thumbnail"], [data-testid*="attachment"], [data-testid*="file-preview"], [class*="file-thumbnail"]',
    model_btn=[
        '[data-testid="model-selector-dropdown"]',
        'button[aria-label*="model" i]',
        'button[aria-label*="модел" i]',
    ],
    model_item='[role="menuitem"], [role="menuitemradio"], [role="option"], [role="menuitemcheckbox"]',
    response='div.font-claude-response, div.font-claude-message, [data-testid="assistant-message"]',
    response_inner="",
    file_input=True,
    default_cdp="http://127.0.0.1:9223",
    chrome_profile=".vibe_chrome_profile_claude",
    # у claude.ai это переключатель Extended thinking: off / on
    reasoning_keywords={
        "off": ["extended thinking", "расширенн", "thinking", "рассужд"],
        "low": ["extended thinking", "расширенн", "thinking", "рассужд"],
        "medium": ["extended thinking", "расширенн", "thinking", "рассужд"],
        "high": ["extended thinking", "расширенн", "thinking", "рассужд"],
    },
)

# Google AI Studio (aistudio.google.com) — тот же Google-аккаунт, что и у Gemini, поэтому по умолчанию
# используется тот же Chrome (порт 9222). Проверенные по открытым проектам (AIstudioProxyAPI и др.) селекторы:
# editor, send, stop (спиннер на кнопке Run), response. Остальные (plus, chip, model_btn, model_item, thinking)
# не проверялись на живой странице: при расхождении переопределите их в .vibe.json -> selector_overrides.aistudio.
# Список моделей и уровней рассуждений читается из интерфейса страницы (не из памяти); после проверки по списку
# ID модели подставляется в ?model=<id> адреса нового чата.
AISTUDIO = Provider(
    key="aistudio",
    title="AI Studio",
    url="https://aistudio.google.com/prompts/new_chat",
    host="aistudio.google.com",
    editor="ms-prompt-input-wrapper ms-autosize-textarea textarea",
    send='ms-run-button button[aria-label="Run"], button.run-button[aria-label="Run"]',
    stop='button.run-button:has(.stoppable-spinner), button.run-button[aria-label="Stop" i]',
    plus='button[aria-label*="Insert" i], button[aria-label*="Add" i], button[aria-label*="upload" i]',
    chip="ms-file-chunk, ms-prompt-chunk [class*=\"file\"], [class*=\"file-chunk\"]",
    model_btn=["ms-model-selector button", "ms-model-selector", 'button[aria-label*="model" i]'],
    model_item='ms-model-selector-v3 button, mat-dialog-container button.content-button, [role="option"], [role="menuitem"]',
    response="ms-chat-turn .chat-turn-container.model",
    response_inner="ms-cmark-node.cmark-node",
    file_input=True,
    default_cdp="http://127.0.0.1:9222",
    chrome_profile=".vibe_chrome_profile",
    reasoning_keywords={},
    model_param="model",
    auto_chain=("inline", "file", "paste"),
    response_all=True,
    response_exclude="ms-thought-chunk",
    thinking="ms-thought-chunk",
    static_models=False,
)

PROVIDERS: Dict[str, Provider] = {"gemini": GEMINI, "claude": CLAUDE, "aistudio": AISTUDIO}

# Каталог моделей для списка в IDE и команды /models, пока нет живого списка с сайта.
# AI Studio: ID для параметра ?model= (источник — справочник ID Gemini на 2026-07, можно ввести любой свой ID).
MODEL_CATALOG: Dict[str, List[dict]] = {
    "gemini": [
        {"id": "Fast", "name": "Fast", "desc": "Быстрые ответы"},
        {"id": "Thinking", "name": "Thinking", "desc": "С рассуждением"},
        {"id": "Pro", "name": "Pro", "desc": "Самая мощная"},
    ],
    "claude": [
        {"id": "Opus", "name": "Opus", "desc": "Максимальное качество"},
        {"id": "Sonnet", "name": "Sonnet", "desc": "Баланс скорости и качества"},
        {"id": "Haiku", "name": "Haiku", "desc": "Самая быстрая"},
    ],
    "aistudio": [],  # список моделей AI Studio читается только из интерфейса страницы
}


def catalog_for(key: str) -> List[dict]:
    return [dict(m) for m in MODEL_CATALOG.get(key, [])]


def get_provider(key: str, overrides: Dict[str, Dict[str, str]] = None) -> Provider:
    base = PROVIDERS.get(key, GEMINI)
    ov = (overrides or {}).get(base.key, {})
    valid = {k: v for k, v in ov.items() if k in base.__dataclass_fields__}
    return replace(base, **valid) if valid else base
