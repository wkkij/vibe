"""Автоподбор контекста по описанию задачи.

Вместо отправки в чат всего репозитория выбираются только файлы, нужные для правки:

1. Файлы, названные в задаче прямо (`renderer.js`, `core/config.py`), берутся всегда.
2. Остальные ранжируются локально (без обращения к ИИ): совпадения с путём и именем файла,
   частота слов в коде (вариант BM25), определения функций/классов с нужными словами.
   Описание на русском сопоставляется с англоязычным кодом через словарь основ (настройки → settings, тема → theme …).
3. К лучшим файлам добавляются их прямые локальные импорты.
4. Если проект маленький — отправляется всё. Если ничего не нашлось — «ключевые» файлы (точки входа, конфиги).

Недостающие файлы модель может запросить строкой `NEED_FILES: путь1, путь2` — см. vibe.py.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .context_packer import ContextPacker
from .i18n import t

SMALL_PROJECT_TOKENS = 15_000     # ниже этого порога подбор не нужен — отправляем всё
DEFAULT_MAX_FILES = 24
DEFAULT_TOKEN_BUDGET = 30_000
MIN_SCORE = 2.0

STOP_WORDS = set(
    """и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще ещё
нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего
ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот
того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при
наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо свою
этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между также например который которые весь новый
новая новые новое удобный удобнее красивый красивые
добавь добавить сделай сделать исправь исправить измени изменить поменяй поменять нужно нужна нужен нужны хочу пожалуйста
помоги проект проекте проекту код коде кода файлы файле
the a an and or to of in on for with add make fix change update please need want should can it is are be this that use using new
from into your our all any also just like then when what how why not but""".split()
)
SHORT_OK = {"ui", "db", "ai", "io", "id", "js", "ts", "py", "css", "api", "cli", "fx", "ux"}

# Основы русских слов → английские слова из кода. Ключ — начало основы (после отбрасывания окончания).
RU_EN: Dict[str, List[str]] = {
    "настройк": ["setting", "config", "option", "preference", "setup"],
    "оформлен": ["theme", "style", "appearance", "design", "css"],
    "тем": ["theme", "dark", "light"],
    "темн": ["dark", "theme"],
    "светл": ["light", "theme"],
    "дизайн": ["style", "design", "css", "ui", "theme"],
    "стил": ["style", "css"],
    "интерфейс": ["ui", "interface", "renderer", "view", "frontend"],
    "логотип": ["logo", "icon", "brand", "svg"],
    "лого": ["logo", "icon"],
    "иконк": ["icon", "svg"],
    "кнопк": ["button", "btn"],
    "тумблер": ["toggle", "switch", "checkbox"],
    "переключател": ["toggle", "switch", "checkbox"],
    "вкладк": ["tab", "tabs"],
    "меню": ["menu"],
    "окн": ["window", "modal", "dialog"],
    "список": ["list"],
    "цвет": ["color", "colour", "theme"],
    "шрифт": ["font"],
    "провайдер": ["provider", "providers"],
    "модел": ["model", "models"],
    "контекст": ["context", "bundle", "packer"],
    "чат": ["chat", "message", "feed"],
    "ответ": ["response", "answer", "reply"],
    "сообщен": ["message", "msg"],
    "промпт": ["prompt", "prompts"],
    "файл": ["file", "files"],
    "папк": ["dir", "directory", "folder"],
    "тест": ["test", "tests", "spec", "pytest"],
    "ошибк": ["error", "exception", "bug", "fail"],
    "баг": ["bug", "error", "fix"],
    "авториз": ["auth", "login", "session"],
    "пользовател": ["user", "account"],
    "баз": ["db", "database", "sql"],
    "запрос": ["request", "query", "fetch"],
    "сервер": ["server", "backend", "api"],
    "клиент": ["client", "frontend"],
    "страниц": ["page", "view", "route"],
    "отправ": ["send", "submit", "post"],
    "остан": ["stop", "abort", "cancel", "kill"],
    "пауз": ["pause", "stop", "resume"],
    "приостанов": ["pause", "stop", "abort"],
    "запуск": ["start", "launch", "run", "boot"],
    "запуст": ["start", "launch", "run"],
    "сборк": ["build", "compile", "bundle"],
    "пакет": ["package", "dependency", "install"],
    "зависимост": ["dependency", "requirements", "package"],
    "конфиг": ["config", "settings"],
    "документ": ["docs", "readme", "documentation"],
    "перевод": ["i18n", "locale", "translate"],
    "журнал": ["log", "logger"],
    "логирован": ["log", "logger", "logging"],
    "консол": ["console", "terminal", "cli"],
    "терминал": ["terminal", "shell", "cli", "command"],
    "команд": ["command", "cmd", "commands"],
    "откат": ["undo", "rollback", "restore", "revert"],
    "патч": ["patch", "diff", "patcher", "apply"],
    "применен": ["apply", "patch"],
    "проверк": ["verify", "check", "validate", "lint", "test"],
    "исправ": ["fix", "repair", "heal"],
    "хранен": ["storage", "store", "persist", "cache", "localstorage"],
    "сохран": ["save", "store", "persist"],
    "загрузк": ["load", "loading", "upload", "download"],
    "анимац": ["animation", "transition", "keyframes", "css"],
    "частиц": ["particles", "canvas", "fx"],
    "эффект": ["effect", "fx", "animation"],
    "подсказк": ["hint", "tooltip", "suggest"],
    "уведомлен": ["notification", "toast", "notify"],
    "статус": ["status", "state", "phase"],
    "состоян": ["state", "status", "phase"],
    "прогресс": ["progress", "status", "spinner", "loader"],
    "индикатор": ["indicator", "status", "spinner", "progress"],
    "размышл": ["thinking", "reasoning"],
    "рассужд": ["reasoning", "thinking"],
    "режим": ["mode", "theme"],
    "язык": ["language", "locale", "i18n"],
    "размер": ["size", "width", "height"],
    "ширин": ["width", "size"],
    "боков": ["sidebar", "side", "panel"],
    "панел": ["panel", "sidebar", "toolbar"],
    "заголов": ["title", "header", "titlebar"],
    "оптимиз": ["optimize", "performance", "cache"],
    "производительн": ["performance", "optimize"],
    "безопасн": ["security", "auth", "sanitize"],
    "парол": ["password", "auth", "secret"],
    "токен": ["token", "auth", "key"],
    "ключ": ["key", "token", "secret"],
    "стоп": ["stop", "abort"],
    "функци": ["feature", "function", "setting"],
    "выбор": ["select", "picker", "choose"],
}

_RU_ENDINGS = sorted(
    [
        "ированию", "ировани", "ениями", "ениях", "ениям", "ование", "ования", "ованию", "ыми", "ими", "ого", "его",
        "ому", "ему", "ами", "ями", "ах", "ях", "ов", "ев", "ей", "ой", "ий", "ый", "ая", "яя", "ое", "ее", "ие",
        "ые", "ую", "юю", "ом", "ем", "ым", "им", "ть", "ти", "ся", "сь", "ет", "ут", "ют", "ит", "ат", "ят", "ла",
        "ло", "ли", "ну", "ю", "я", "а", "у", "ы", "и", "е", "о",
    ],
    key=len,
    reverse=True,
)
_CYR = re.compile(r"[А-Яа-яЁё]")
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")
_DEF = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|const|let|var|interface|type|struct|fn)\s+([A-Za-z_][\w]*)", re.M)
_MENTION_BOUNDARY = r"(?<![\w./\\-]){}(?![\w])"


def clean_path(p: str) -> str:
    p = p.strip().strip("`'\"").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def is_mentioned(task_low: str, rel_low: str, name: str) -> bool:
    """Файл назван в задаче по имени или относительному пути."""
    if re.search(_MENTION_BOUNDARY.format(re.escape(rel_low)), task_low):
        return True
    return len(name) >= 4 and bool(re.search(_MENTION_BOUNDARY.format(re.escape(name)), task_low))


def split_identifier(s: str) -> List[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return [p.lower() for p in re.split(r"[_\-\s]+", s) if p]


def stem_ru(w: str) -> str:
    for end in _RU_ENDINGS:
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[: -len(end)]
    return w


def norm(token: str) -> str:
    """Приводит слово к основе (русские окончания и простые английские суффиксы)."""
    w = token.lower().replace("ё", "е")
    if _CYR.search(w):
        return stem_ru(w)
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def content_terms(text: str) -> Counter:
    c: Counter = Counter()
    for m in _WORD.finditer(text):
        w = m.group(0)
        if len(w) < 3:
            continue
        parts = split_identifier(w) if not _CYR.search(w) else [w]
        c[norm(w)] += 1
        if len(parts) > 1:
            for p in parts:
                if len(p) >= 3:
                    c[norm(p)] += 1
    return c


def build_query(task: str, extra: Optional[Dict[str, List[str]]] = None) -> Dict[str, float]:
    """Слова задачи → {основа: вес}. Включает английские аналоги русских слов."""
    terms: Dict[str, float] = {}
    table = dict(RU_EN)
    if extra:
        table.update({str(k).lower(): list(v) for k, v in extra.items()})

    def add(term: str, w: float):
        if term and (term not in terms or terms[term] < w):
            terms[term] = w

    for m in _WORD.finditer(task):
        raw = m.group(0)
        low = raw.lower().replace("ё", "е")
        if low in STOP_WORDS or raw.isdigit():
            continue
        if len(low) < 3 and low not in SHORT_OK:
            continue
        stem = norm(low)
        if stem in STOP_WORDS:
            continue
        add(stem, 1.0)
        if not _CYR.search(low):
            for p in split_identifier(raw):
                if len(p) >= 3 and p not in STOP_WORDS:
                    add(norm(p), 0.7)
        for key, vals in table.items():
            if stem.startswith(key):
                for v in vals:
                    add(norm(v), 0.8)
    return terms


@dataclass
class Picked:
    rel: str
    path: Path
    score: float
    tokens: int
    reason: str


@dataclass
class Selection:
    mode: str  # "all" | "auto"
    items: List[Picked]
    total_files: int
    total_tokens: int
    selected_tokens: int
    fallback: bool = False
    note: str = ""

    @property
    def paths(self) -> List[Path]:
        return [i.path for i in self.items]

    @property
    def rels(self) -> Set[str]:
        return {i.rel for i in self.items}

    def to_event(self, limit: int = 60) -> dict:
        return {
            "mode": self.mode,
            "files": len(self.items),
            "tokens": self.selected_tokens,
            "total_files": self.total_files,
            "total_tokens": self.total_tokens,
            "fallback": self.fallback,
            "note": self.note,
            "selected": [
                {"path": i.rel, "score": round(i.score, 1), "tokens": i.tokens, "reason": i.reason}
                for i in self.items[:limit]
            ],
        }


@dataclass
class _Doc:
    rel: str
    path: Path
    tokens: int
    terms: Counter
    defs: Set[str]
    imports: Set[str]
    length: int


class ContextSelector:
    def __init__(
        self,
        packer: ContextPacker,
        max_files: int = DEFAULT_MAX_FILES,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        synonyms: Optional[Dict[str, List[str]]] = None,
    ):
        self.packer = packer
        self.root = packer.root
        self.max_files = max(1, int(max_files))
        self.token_budget = max(2000, int(token_budget))
        self.synonyms = synonyms or {}
        self._cache: Dict[str, Tuple[Tuple[float, int], _Doc]] = {}

    # ---------------------------------------------------------------- индекс

    def _doc(self, path: Path) -> Optional[_Doc]:
        rel = path.relative_to(self.root).as_posix()
        try:
            st = path.stat()
            key = (st.st_mtime, st.st_size)
        except OSError:
            return None
        hit = self._cache.get(rel)
        if hit and hit[0] == key:
            return hit[1]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        defs: Set[str] = set()
        for m in _DEF.finditer(text):
            for p in split_identifier(m.group(1)) + [m.group(1).lower()]:
                if len(p) >= 3:
                    defs.add(norm(p))
        doc = _Doc(rel, path, max(1, len(text) // 4), content_terms(text), defs, self._imports(rel, text), len(text))
        self._cache[rel] = (key, doc)
        return doc

    def _imports(self, rel: str, text: str) -> Set[str]:
        """Относительные пути локальных файлов, на которые ссылается файл (кандидаты, существование проверяется позже)."""
        out: Set[str] = set()
        base = Path(rel).parent
        suffix = Path(rel).suffix.lower()
        if suffix == ".py":
            for m in re.finditer(r"^\s*from\s+(\.*)([\w.]*)\s+import\s+([\w, ()]*)", text, re.M):
                dots, mod, names = len(m.group(1)), m.group(2), m.group(3)
                anchor = base
                if dots:
                    for _ in range(dots - 1):
                        anchor = anchor.parent
                parts = [p for p in mod.split(".") if p]
                target = anchor.joinpath(*parts) if parts else anchor
                if not dots:
                    target = Path(*parts) if parts else Path(".")
                out.add((target.as_posix() + ".py"))
                out.add((target / "__init__.py").as_posix())
                for n in [x.strip("() ") for x in names.split(",") if x.strip("() ")]:
                    out.add((target / (n + ".py")).as_posix())
            for m in re.finditer(r"^\s*import\s+([\w., ]+)", text, re.M):
                for mod in m.group(1).split(","):
                    mod = mod.strip().split(" as ")[0].strip()
                    if mod:
                        p = Path(*mod.split("."))
                        out.add(p.as_posix() + ".py")
                        out.add((p / "__init__.py").as_posix())
        elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"):
            for m in re.finditer(r"""(?:from\s+|require\(\s*|import\(\s*|import\s+)['"](\.{1,2}/[^'"]+)['"]""", text):
                target = (base / m.group(1)).as_posix()
                target = re.sub(r"/\./", "/", target)
                parts: List[str] = []
                for seg in target.split("/"):
                    if seg == "..":
                        if parts:
                            parts.pop()
                    elif seg and seg != ".":
                        parts.append(seg)
                mod = "/".join(parts)
                out.add(mod)
                for ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".json", ".vue"):
                    out.add(mod + ext)
                    out.add(mod + "/index" + ext)
        return out

    # ---------------------------------------------------------------- подбор

    def select(self, task: str) -> Selection:
        files = self.packer.collect_files()
        docs = [d for d in (self._doc(f) for f in files) if d is not None]
        total_tokens = sum(d.tokens for d in docs)

        if total_tokens <= SMALL_PROJECT_TOKENS:
            return Selection(
                "all",
                [Picked(d.rel, d.path, 0.0, d.tokens, t("небольшой проект — отправляется целиком")) for d in docs],
                len(docs), total_tokens, total_tokens,
                note=t("Проект небольшой: подбор не нужен, отправляются все файлы."),
            )

        terms = build_query(task, self.synonyms)
        n = len(docs)
        df: Counter = Counter()
        for d in docs:
            for w_ in terms:
                if d.terms.get(w_):
                    df[w_] += 1
        idf = {w_: math.log(1 + n / (df[w_] + 0.5)) for w_ in terms}

        task_low = task.lower().replace("\\", "/")
        scored: List[Picked] = []
        for d in docs:
            rel_low = d.rel.lower()
            name = Path(d.rel).name.lower()
            stem_tokens = {norm(p) for p in split_identifier(Path(d.rel).stem)}
            dir_tokens = {norm(p) for part in Path(d.rel).parts[:-1] for p in split_identifier(part)}
            score = 0.0
            why_name: List[str] = []
            why_code: List[str] = []
            mentioned = False
            if is_mentioned(task_low, rel_low, name):
                score += 100.0
                mentioned = True
            lenf = 1.0 / (1.0 + math.log(1 + d.length / 4000.0))
            for w_, w in terms.items():
                if w_ in stem_tokens:
                    score += 8.0 * w
                    why_name.append(w_)
                elif w_ in dir_tokens:
                    score += 3.0 * w
                    why_name.append(w_)
                tf = d.terms.get(w_, 0)
                if tf:
                    score += w * (1.0 + math.log(tf)) * idf[w_] * lenf * 2.0
                    why_code.append(w_)
                if w_ in d.defs:
                    score += 3.0 * w
            if score <= 0:
                continue
            reasons = []
            if mentioned:
                reasons.append(t("назван в задаче"))
            if why_name:
                reasons.append(t("имя/путь: ") + ", ".join(dict.fromkeys(why_name)))
            if why_code:
                reasons.append(t("в коде: ") + ", ".join(list(dict.fromkeys(why_code))[:5]))
            scored.append(Picked(d.rel, d.path, score, d.tokens, "; ".join(reasons)))

        scored.sort(key=lambda p: -p.score)
        by_rel = {d.rel: d for d in docs}
        picked: List[Picked] = []
        used = 0
        fallback = False
        note = ""

        if not scored or scored[0].score < MIN_SCORE:
            fallback = True
            note = t("В описании не нашлось опорных слов — отправлены ключевые файлы проекта.")
            picked, used = self._key_files(docs)
        else:
            threshold = max(MIN_SCORE, scored[0].score * 0.12)
            for it in scored:
                if len(picked) >= self.max_files:
                    break
                if it.score < threshold and it.score < 100:
                    break
                if used + it.tokens > self.token_budget and picked and it.score < 100:
                    continue
                picked.append(it)
                used += it.tokens

            # прямые локальные импорты лучших файлов
            have = {p.rel for p in picked}
            for head in list(picked[:6]):
                doc = by_rel.get(head.rel)
                if not doc:
                    continue
                for cand in sorted(doc.imports):
                    d2 = by_rel.get(clean_path(cand))
                    if d2 is None or d2.rel in have:
                        continue
                    if len(picked) >= self.max_files or used + d2.tokens > self.token_budget:
                        continue
                    picked.append(Picked(d2.rel, d2.path, 1.0, d2.tokens, t("импортируется из {name}", name=head.rel)))
                    have.add(d2.rel)
                    used += d2.tokens

        if used >= total_tokens * 0.85:
            note = note or t("Подобранные файлы покрывают почти весь проект.")
        return Selection("auto", picked, len(docs), total_tokens, used, fallback, note)

    def _key_files(self, docs: List[_Doc]) -> Tuple[List[Picked], int]:
        key_names = {
            "main", "index", "app", "vibe", "server", "cli", "manage", "package.json", "pyproject.toml",
            "requirements.txt", "readme.md", "config", "settings", "renderer", "preload",
        }
        ranked = sorted(
            docs,
            key=lambda d: (0 if (Path(d.rel).stem.lower() in key_names or Path(d.rel).name.lower() in key_names) else 1, d.tokens),
        )
        picked: List[Picked] = []
        used = 0
        cap = int(self.token_budget * 0.6)
        for d in ranked:
            if len(picked) >= self.max_files or used + d.tokens > cap:
                continue
            picked.append(Picked(d.rel, d.path, 0.5, d.tokens, t("ключевой файл проекта")))
            used += d.tokens
        return picked, used


NEED_FILES_RE = re.compile(r"^\s*NEED_FILES\s*:\s*(.+)$", re.I | re.M)


def parse_need_files(text: str, limit: int = 8) -> List[str]:
    """Пути из строки `NEED_FILES: a, b` в ответе модели."""
    m = NEED_FILES_RE.search(text or "")
    if not m:
        return []
    raw = re.split(r"[,\s;]+", m.group(1).strip().strip("`"))
    out: List[str] = []
    for p in raw:
        p = clean_path(p)
        if p and p not in out:
            out.append(p)
    return out[:limit]

