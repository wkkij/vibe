import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import VibeConfig
from core.context_packer import ContextPacker
from core.patcher import DiffPatcher


def mk():
    d = Path(tempfile.mkdtemp())
    (d / "a.py").write_bytes(b"def f():\r\n    return 1\r\n\r\nprint(f())\r\n")
    (d / "b.txt").write_text("hello\n")
    cfg = VibeConfig(d)
    return d, cfg, DiffPatcher(d, cfg.backup_dir)


def test_crlf_preserved_and_failed_blocks_reported():
    d, cfg, p = mk()
    resp = """```text
<<<FILE: a.py>>>
<<<<<<< SEARCH
def f():
    return 1
=======
def f():
    return 2
>>>>>>> REPLACE
<<<<<<< SEARCH
no such text
=======
x
>>>>>>> REPLACE
<<<END_FILE>>>
```"""
    res, _ = p.parse_and_apply(resp)
    assert res[0].action == "MODIFIED" and res[0].blocks_applied == 1
    assert res[0].failed_blocks == ["no such text"]
    raw = (d / "a.py").read_bytes()
    assert b"return 2" in raw and b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_path_traversal_blocked():
    d, cfg, p = mk()
    res, _ = p.parse_and_apply("<<<CREATE: ../evil.txt>>>\nx\n<<<END_CREATE>>>")
    assert res[0].action == "FAILED"
    assert not (d.parent / "evil.txt").exists()


def test_undo_roundtrip():
    d, cfg, p = mk()
    p.parse_and_apply("<<<CREATE: new.txt>>>\nx\n<<<END_CREATE>>>\n<<<DELETE: b.txt>>>")
    assert (d / "new.txt").exists() and not (d / "b.txt").exists()
    ok, _ = p.undo_last_snapshot()
    assert ok and not (d / "new.txt").exists() and (d / "b.txt").read_text() == "hello\n"


def test_packer_and_pack_files_and_canary():
    d, cfg, p = mk()
    pk = ContextPacker(cfg)
    path, n, _ = pk.write_context_bundle_file(canary="abc123")
    txt = path.read_text()
    assert n == 2 and "VIBE_CANARY=abc123" in txt and "=== FILE: b.txt ===" in txt
    assert "hello" in pk.pack_files(["b.txt"])
    from core import i18n
    try:
        i18n.set_lang("ru")
        assert "(удалён)" in pk.pack_files(["gone.txt"])
        i18n.set_lang("en")
        assert "(deleted)" in pk.pack_files(["gone.txt"])
    finally:
        i18n.set_lang("en")


def test_config_model_transport_persist():
    d, cfg, _ = mk()
    cfg.model, cfg.transport = "pro", "paste"
    cfg.save_project_config()
    c2 = VibeConfig(d)
    assert c2.model == "pro" and c2.transport == "paste"
    assert json.loads((d / ".vibe.json").read_text())["models"]["gemini"] == "pro"


def test_providers_independent_settings_and_overrides():
    from core.providers import get_provider
    d, cfg, _ = mk()
    cfg.model = "3.1 pro"; cfg.reasoning = "high"
    cfg.provider = "claude"
    assert cfg.model == "" and cfg.cdp_url.endswith("9223")
    cfg.model = "sonnet"; cfg.save_project_config()
    c2 = VibeConfig(d)
    assert c2.provider == "claude" and c2.model == "sonnet"
    c2.provider = "gemini"
    assert c2.model == "3.1 pro" and c2.reasoning == "high"
    assert get_provider("claude", {"claude": {"editor": "X"}}).editor == "X"


def test_model_matching():
    import sys, types
    sys.modules.setdefault("httpx", types.ModuleType("httpx"))
    from core.gemini_bridge import WebChatBridge
    b = WebChatBridge.__new__(WebChatBridge)
    E = [{"name": n, "full": n + " | desc"} for n in ["4 Argon", "3.1 Pro", "3.8 Flash", "Pro"]]
    assert b._match(E, "3.1pro")["name"] == "3.1 Pro"
    assert b._match(E, "argon")["name"] == "4 Argon"
    assert b._match(E, "pro")["name"] == "Pro"      # точное имя важнее вхождения
    assert b._match(E, "2")["name"] == "3.1 Pro"    # номер
    assert b._match(E, "flash")["name"] == "3.8 Flash"
    assert b._match(E, "nope") is None


def test_command_resolution():
    from core.commands import resolve, parse_model_args
    assert resolve("исправь баг")[0] == "task"
    assert resolve("/model")[:2] == ("command", "model")
    assert resolve("/model 2 high")[2] == "2 high"
    assert resolve("/mod")[:2] == ("command", "model")  # однозначный префикс
    k, _, _, hints = resolve("/re")            # reset, reasoning -> неоднозначно, никуда не уходит
    assert k == "ambiguous" and {"reset", "reasoning"} <= set(hints)
    assert resolve("/und")[:2] == ("command", "undo")   # однозначный префикс
    from core.commands import COMMANDS
    assert "mode" not in COMMANDS                       # cookie/mode-режим удалён
    k, _, _, hints = resolve("/modle")
    assert k == "unknown" and "model" in hints
    assert resolve("/new")[:2] == ("command", "reset")
    assert parse_model_args("2 high") == ("2", "high")
    assert parse_model_args("3.1 pro medium") == ("3.1 pro", "medium")
    assert parse_model_args("4 argon") == ("4 argon", "")
    assert parse_model_args("thinking") == ("thinking", "")


def test_match_ignores_settings():
    import sys, types
    sys.modules.setdefault("httpx", types.ModuleType("httpx"))
    from core.gemini_bridge import WebChatBridge, SETTING_RE
    b = WebChatBridge.__new__(WebChatBridge)
    E = [{"name": n, "full": n, "kind": "setting" if SETTING_RE.search(n) else "model"}
         for n in ["3.5 Flash-Lite", "3.8 Flash", "3.1 Pro", "4 Argon", "Thinking level"]]
    assert E[4]["kind"] == "setting"
    assert b._match(E, "5") is None                 # номер 5 — не модель
    assert b._match(E, "4")["name"] == "4 Argon"
    assert b._match(E, "3.1pro")["name"] == "3.1 Pro"
    assert b._match(E, "3.8")["name"] == "3.8 Flash"

