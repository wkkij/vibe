import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import VibeConfig, SYSTEM_PROMPT_PATCHER
from core.context_packer import ContextPacker
from core.context_selector import ContextSelector, build_query, norm, parse_need_files
from core.prompts import PromptBook, PATCH_FORMAT_RULES


def project(files):
    d = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return d


def test_vibeide_in_context_but_service_dirs_not():
    d = project({".vibeide/main.js": "x", ".vibe_backups/a.txt": "x", ".vibe_chrome_profile/b.txt": "x", "a.py": "x"})
    names = {f.relative_to(d).as_posix() for f in ContextPacker(VibeConfig(d)).collect_files()}
    assert ".vibeide/main.js" in names and "a.py" in names
    assert not any(n.startswith((".vibe_backups", ".vibe_chrome_profile")) for n in names)


def test_aistudio_provider():
    from core.providers import PROVIDERS, get_provider
    d = project({"a.py": "x"})
    cfg = VibeConfig(d)
    cfg.provider = "aistudio"
    assert "aistudio" in PROVIDERS and cfg.cdp_url.endswith("9222")
    p = get_provider("aistudio")
    assert p.host == "aistudio.google.com" and p.model_param == "model" and p.auto_chain[0] == "inline"


def test_prompts_classic_equals_original_and_rotation():
    assert SYSTEM_PROMPT_PATCHER.startswith("Ты — автономный Principal Software Engineer")
    assert PATCH_FORMAT_RULES in SYSTEM_PROMPT_PATCHER
    b = PromptBook("auto", seed=1, lang="ru")
    texts = [b.task("x") for _ in range(10)]
    assert all(a != c for a, c in zip(texts, texts[1:])) and len(set(texts)) > 3  # текст каждый раз новый
    assert b.begin_task("исправь баг в кнопке") == "bug" and b.begin_task("добавь тёмную тему") == "feature"
    for st in ("auto", "classic"):
        pb = PromptBook(st, lang="ru")
        assert PATCH_FORMAT_RULES in pb.system_patcher()
        assert "<<<FILE" in pb.task("x") and "x" in pb.task("x")
        assert "CONTEXT_OK abc123" in pb.canary("abc123") and "VIBE_CANARY=abc123" in pb.canary("abc123")
    assert "NEED_FILES" in PromptBook("auto", lang="ru").system_patcher(True)


def test_selector_ru_task_finds_en_code():
    files = {
        "ui/theme.js": "function applyTheme(name){ document.body.dataset.theme = name }\n" * 40,
        "ui/settings.js": "export function openSettings(){ /* настройки */ }\n" * 40,
        "core/db.py": "def connect_database(): pass\n" * 40,
        "core/net.py": "def fetch_request(): pass\n" * 40,
        "README.md": "docs\n" * 10,
    }
    for i in range(30):
        files[f"core/mod{i}.py"] = "def helper_%d():\n    return %d\n" % (i, i) * 120
    d = project(files)
    sel = ContextSelector(ContextPacker(VibeConfig(d)), max_files=6).select("добавь тёмную тему в настройках")
    assert sel.mode == "auto"
    rels = sel.rels
    assert "ui/theme.js" in rels and "ui/settings.js" in rels and "core/db.py" not in rels


def test_selector_explicit_mention_and_small_project():
    d = project({"a.py": "x = 1\n", "b.py": "y = 2\n"})
    sel = ContextSelector(ContextPacker(VibeConfig(d))).select("поправь a.py")
    assert sel.mode == "all" and len(sel.items) == 2
    files = {f"m{i}.py": ("def f%d(): pass\n" % i) * 400 for i in range(20)}
    d2 = project(files)
    sel2 = ContextSelector(ContextPacker(VibeConfig(d2)), max_files=3).select("исправь ошибку в m7.py")
    assert sel2.mode == "auto" and sel2.items[0].rel == "m7.py"


def test_need_files_and_query():
    assert parse_need_files("CONTEXT_OK\nNEED_FILES: core/a.py, `./.vibeide/main.js`; b.txt") == ["core/a.py", ".vibeide/main.js", "b.txt"]
    assert parse_need_files("обычный ответ") == []
    q = build_query("тумблер в настройках оформления")
    assert norm("toggle") in q and norm("setting") in q and norm("theme") in q


def test_events_off_outside_ide(capsys, monkeypatch):
    from core import events
    monkeypatch.delenv("VIBE_IDE", raising=False)
    events.emit("phase", phase="x")
    assert capsys.readouterr().out == ""
    monkeypatch.setenv("VIBE_IDE", "1")
    events.emit("phase", phase="thinking")
    assert capsys.readouterr().out.startswith('@@VIBE {"t": "phase"')


def test_menu_entry_classification():
    from core.gemini_bridge import WebChatBridge as B
    c = B._classify_entry
    assert c("Sonnet 5.5", "Sonnet 5.5 | Наиболее эффективен для более простых задач") == "model"
    assert c("Opus 5.5", "Opus 5.5 | Pro | Для сложной работы | Улучшить план") == "locked"      # недоступна в free
    assert c("Opus 5.5", "Opus 5.5 | Для сложной работы", disabled=True) == "locked"
    promo = "Fable входит в планы Max и Ultra, а также в план Pro на ограниченное время. Подробнее"
    assert c(promo, promo) == "promo"                                                          # реклама — не модель
    assert c("Другие модели", "Другие модели") == "submenu"
    assert c("Уровень усилий", "Уровень усилий | Низкий") == "option"
    assert c("Thinking level", "Thinking level | High") == "setting"

