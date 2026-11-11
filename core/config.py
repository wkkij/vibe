import json
import os
from pathlib import Path
from dotenv import load_dotenv

from .i18n import LANGS, resolve_language, set_lang, t
from .prompts import VALID_STYLES, PromptBook
from .providers import PROVIDERS

load_dotenv()
_classic = PromptBook("classic", lang="ru")  # константы SYSTEM_PROMPT_* — русский «классический» вариант (обратная совместимость)

DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    ".svn/",
    ".hg/",
    "node_modules/",
    "venv/",
    ".venv/",
    "env/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".DS_Store",
    "dist/",
    "build/",
    ".next/",
    ".nuxt/",
    "target/",
    "out/",
    "coverage/",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.webp",
    "*.mp4",
    "*.mp3",
    "*.wav",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    ".vibe_backups/",
    ".vibe_context_bundle.txt",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
]

VALID_TRANSPORTS = ("auto", "file", "paste", "inline", "zip", "base64")

# Форматы отправки контекста: id -> (название, описание). Показываются в IDE и в /transport.
# Сами строки — ключи переводов (core/locale_en.py); на языке интерфейса их отдаёт transport_info().
TRANSPORT_INFO = {
    "auto": ("Авто", "Пробует по очереди: файл → вставка → ZIP → base64-файл → текст, пока чат не увидит контекст"),
    "file": ("Файл .txt", "Контекст — обычным файлом через кнопку «+» в чате"),
    "paste": ("Файл вставкой", "Тот же .txt, но вставляется как из буфера обмена (paste/drop) — если кнопка «+» недоступна"),
    "inline": ("Текстом в сообщении", "Весь контекст — прямо в тексте сообщения, без вложений"),
    "zip": ("ZIP-архив", "Контекст упаковывается в .zip и прикрепляется файлом (меньше размер)"),
    "base64": ("Base64-файл", "Контекст кодируется в base64 и прикрепляется отдельным .txt-файлом"),
}

def transport_info(key: str):
    """(название, описание) способа передачи контекста на языке интерфейса."""
    title, desc = TRANSPORT_INFO[key]
    return t(title), t(desc)


# Тексты промптов (в нескольких вариациях) лежат в core/prompts.py. Константы ниже — «классический» вариант,
# оставлены для обратной совместимости.
SYSTEM_PROMPT_PATCHER = _classic.system_patcher()
SYSTEM_PROMPT_PLANNER = _classic.system_planner()


class VibeConfig:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.config_file = self.project_root / ".vibe.json"
        self.vibe_rules_file = self.project_root / "VIBE.md"
        self.backup_dir = self.project_root / ".vibe_backups"

        self.provider = os.getenv("VIBE_PROVIDER", "gemini").lower()
        self.cdp_urls = {
            "gemini": os.getenv("VIBE_CHROME_CDP_URL", "http://127.0.0.1:9222"),
            "claude": os.getenv("VIBE_CLAUDE_CDP_URL", "http://127.0.0.1:9223"),
            # AI Studio использует тот же Google-аккаунт, поэтому по умолчанию — тот же Chrome, что и у Gemini
            "aistudio": os.getenv("VIBE_AISTUDIO_CDP_URL", os.getenv("VIBE_CHROME_CDP_URL", "http://127.0.0.1:9222")),
        }
        self.models = {
            "gemini": os.getenv("VIBE_MODEL", ""),
            "claude": os.getenv("VIBE_CLAUDE_MODEL", ""),
            "aistudio": os.getenv("VIBE_AISTUDIO_MODEL", ""),
        }
        self.reasonings = {"gemini": os.getenv("VIBE_REASONING", ""), "claude": "", "aistudio": ""}
        self.selector_overrides = {}
        self.verify_cmd = os.getenv("VIBE_VERIFY_CMD", "")
        self.max_heal_retries = int(os.getenv("VIBE_MAX_HEAL_RETRIES", "4"))
        self.upload_context_as_file = os.getenv("VIBE_UPLOAD_CONTEXT_AS_FILE", "true").lower() == "true"
        self.transport = os.getenv("VIBE_TRANSPORT", "auto").lower()
        self.extra_ignores = []
        # автоподбор контекста по описанию задачи (вместо отправки всех файлов)
        self.auto_context = os.getenv("VIBE_AUTO_CONTEXT", "false").lower() in ("1", "true", "yes", "on")
        self.auto_context_max_files = int(os.getenv("VIBE_AUTO_CONTEXT_MAX_FILES", "24"))
        self.auto_context_budget = int(os.getenv("VIBE_AUTO_CONTEXT_BUDGET", "30000"))  # токенов
        self.context_synonyms = {}  # свои пары «русская основа» -> [английские слова из кода]
        # вариации промпта, вставляемого в чат: auto | classic | concise | strict | mentor | pair | friendly
        self.prompt_style = os.getenv("VIBE_PROMPT_STYLE", "auto").lower()
        # язык интерфейса и промптов: en | ru | auto (по языку системы). Переопределяется VIBE_LANG, --lang и /lang
        self.language = os.getenv("VIBE_LANG", "auto").lower()

        self.load_project_config()
        if self.provider not in PROVIDERS:
            self.provider = "gemini"
        if self.prompt_style not in VALID_STYLES:
            self.prompt_style = "auto"
        if self.transport not in VALID_TRANSPORTS:
            self.transport = "auto"
        if self.language not in LANGS + ("auto",):
            self.language = "auto"
        set_lang(self.language)

    # --- значения для текущего провайдера (чтобы остальной код не знал про словари) ---
    @property
    def cdp_url(self) -> str:
        return self.cdp_urls[self.provider]

    @cdp_url.setter
    def cdp_url(self, v: str):
        self.cdp_urls[self.provider] = v

    @property
    def model(self) -> str:
        return self.models.get(self.provider, "")

    @model.setter
    def model(self, v: str):
        self.models[self.provider] = v

    @property
    def reasoning(self) -> str:
        return self.reasonings.get(self.provider, "")

    @reasoning.setter
    def reasoning(self, v: str):
        self.reasonings[self.provider] = v

    def load_project_config(self):
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                if "cdp_url" in data:  # старый формат
                    self.cdp_urls["gemini"] = data["cdp_url"]
                self.provider = data.get("provider", self.provider)
                self.cdp_urls.update(data.get("cdp_urls", {}))
                self.models.update(data.get("models", {}))
                if "model" in data and "models" not in data:
                    self.models["gemini"] = data["model"]
                self.reasonings.update(data.get("reasonings", {}))
                self.selector_overrides = data.get("selector_overrides", {})
                self.verify_cmd = data.get("verify_cmd", self.verify_cmd)
                self.max_heal_retries = int(data.get("max_heal_retries", self.max_heal_retries))
                self.upload_context_as_file = data.get("upload_context_as_file", self.upload_context_as_file)
                self.extra_ignores = data.get("ignore", [])
                self.transport = data.get("transport", self.transport)
                self.auto_context = bool(data.get("auto_context", self.auto_context))
                self.auto_context_max_files = int(data.get("auto_context_max_files", self.auto_context_max_files))
                self.auto_context_budget = int(data.get("auto_context_budget", self.auto_context_budget))
                self.context_synonyms = data.get("context_synonyms", self.context_synonyms)
                self.prompt_style = data.get("prompt_style", self.prompt_style)
                if not os.getenv("VIBE_LANG"):  # переменная окружения важнее файла
                    self.language = str(data.get("language", self.language)).lower()
            except Exception:
                pass

    def save_project_config(self):
        data = {
            "provider": self.provider,
            "cdp_urls": self.cdp_urls,
            "models": self.models,
            "reasonings": self.reasonings,
            "selector_overrides": self.selector_overrides,
            "verify_cmd": self.verify_cmd,
            "max_heal_retries": self.max_heal_retries,
            "upload_context_as_file": self.upload_context_as_file,
            "ignore": self.extra_ignores,
            "transport": self.transport,
            "auto_context": self.auto_context,
            "auto_context_max_files": self.auto_context_max_files,
            "auto_context_budget": self.auto_context_budget,
            "context_synonyms": self.context_synonyms,
            "prompt_style": self.prompt_style,
            "language": self.language,
        }
        self.config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_project_rules(self) -> str:
        if self.vibe_rules_file.exists():
            return self.vibe_rules_file.read_text(encoding="utf-8").strip()
        return ""
