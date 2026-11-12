import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from core import mascot, ui
from core.commands import COMMANDS, describe, help_groups, parse_model_args, resolve
from core.completion import make_session
from core.config import VALID_TRANSPORTS, VibeConfig, transport_info
from core.context_packer import ContextPacker
from core.context_selector import ContextSelector, parse_need_files
from core.events import GenerationStopped, clear_stop, emit, ide_mode, strip_markup
from core.gemini_bridge import WebChatBridge
from core.i18n import LANG_TITLES, LANGS, get_lang, resolve_language, set_lang, t
from core.patcher import DiffPatcher
from core.prompts import VALID_STYLES, PromptBook, describe_styles, style_title
from core.providers import PROVIDERS, catalog_for
from core.runner import BrowserVerifier, TerminalRunner

console = Console()
IDE = ide_mode()  # Vibe IDE: вместо рамок и таблиц CLI шлёт события (core/events.py), интерфейс рисует IDE
VERSION = "0.01.4"


def say(text: str, level: str = "info") -> None:
    """Строка статуса: в терминале — rich-разметка, в IDE — событие журнала."""
    if IDE:
        emit("log", level=level, text=strip_markup(text))
    else:
        console.print(text)


def show_answer(md: str, title: str, kind: str = "answer") -> None:
    if IDE:
        emit("answer", text=md, title=title, kind=kind)
    else:
        console.print(ui.answer_panel(Markdown(md), title, kind))


def show_help() -> None:
    """Экран /help: команды по группам, описания на языке интерфейса."""
    console.print(ui.help_panel(help_groups(), describe))
    console.print(ui.dim(t("Примеры: `/model 3.1 pro high`, `/provider claude`, `/lang en`")), highlight=False)


class VibeOrchestrator:
    def __init__(self, project_root: Path, yolo_mode: bool = False):
        self.root = project_root.resolve()
        self.config = VibeConfig(self.root)
        self.packer = ContextPacker(self.config)
        self.patcher = DiffPatcher(self.root, self.config.backup_dir)
        self.bridge = WebChatBridge(self.config)
        self.runner = TerminalRunner(self.root)
        self.verifier = BrowserVerifier(self.root)
        self.yolo_mode = yolo_mode
        self.session_initialized = False
        self.model_names: list = []  # кэш для автодополнения /model
        # Vibe IDE запускает CLI через pipe (не TTY) — prompt_toolkit там не нужен
        self.session = None if os.environ.get("VIBE_IDE") else make_session(os.path.join(os.path.expanduser("~"), ".vibe_history"), lambda: self.model_names)
        self.dirty_files: set = set()  # файлы, изменённые после отправки контекста в чат
        self.prompts = PromptBook(self.config.prompt_style)
        self.bridge.prompts = self.prompts
        self.sent_files: set = set()   # файлы, уже отправленные в текущий чат (для автоподбора контекста)
        self.scope_partial = False     # в чат ушла только часть файлов -> модель может просить NEED_FILES
        self.last_partial = ""         # текст остановленного ответа
        self._selector = None
        self.attachments: list = []    # файлы, прикреплённые пользователем к следующему сообщению
        self.bridge.pending_files = self.attachments
        self.mood = "idle"             # настроение Vibi в строке ввода: idle | happy | error | sleep

    @property
    def title(self) -> str:
        return PROVIDERS[self.config.provider].title

    def selector(self) -> ContextSelector:
        c = self.config
        if self._selector is None or (self._selector.max_files, self._selector.token_budget) != (c.auto_context_max_files, max(2000, c.auto_context_budget)):
            self._selector = ContextSelector(self.packer, c.auto_context_max_files, c.auto_context_budget, c.context_synonyms)
        return self._selector

    def emit_hello(self):
        c = self.config
        emit(
            "hello", version=VERSION, provider=c.provider, title=self.title, model=c.model, reasoning=c.reasoning,
            auto_context=c.auto_context, max_files=c.auto_context_max_files, budget=c.auto_context_budget,
            prompt_style=c.prompt_style, styles=describe_styles(), transport=c.transport, yolo=self.yolo_mode, transports=[{"id": k, "title": transport_info(k)[0], "desc": transport_info(k)[1]} for k in VALID_TRANSPORTS], verify_cmd=c.verify_cmd,
            root=str(self.root), lang=get_lang(),
        )

    def ask_confirm(self, text: str, default: bool = True) -> bool:
        if self.yolo_mode:
            say(ui.dim("⚡ " + t("Без подтверждений: выполняю автоматически")))
            return True
        if IDE:
            emit("ask", kind="confirm", text=strip_markup(text), default="y" if default else "n")
            line = sys.stdin.readline()
            if line == "":
                raise EOFError
            v = line.strip().lower()
            return default if not v else v in ("y", "yes", "да", "ok", "ок")
        return Confirm.ask(text, default=default)

    def ask_text(self, text: str, default: str = "y") -> str:
        if self.yolo_mode:
            return default
        if IDE:
            emit("ask", kind="input", text=strip_markup(text), default=default)
            line = sys.stdin.readline()
            if line == "":
                raise EOFError
            return line.strip() or default
        return Prompt.ask(text, default=default)

    def print_banner(self):
        ui.show_banner(console, self, VERSION)

    def show_context_stats(self):
        files = self.packer.collect_files()
        _, count, approx_tokens = self.packer.pack_repository()
        body = (
            t("Найдено исходных файлов: [bold cyan]{n}[/bold cyan]", n=count) + "\n"
            + t("Примерный объем контекста: [bold green]~{tokens} токенов[/bold green] (Окно Google AI Pro вмещает до 1,000,000+ токенов)", tokens=f"{approx_tokens:,}")
            + f"\n\n[dim]{self.packer.build_tree_string(files[:35])}"
            + (t("\n  ... и еще {n} файлов", n=len(files) - 35) + "[/dim]" if len(files) > 35 else "[/dim]")
        )
        console.print(ui.info_panel(body, t("Контекст репозитория")))

    async def ask_model(self, status: str, **kwargs) -> str:
        """send_prompt с живой анимацией Vibi в терминале (в IDE анимацию рисует сама IDE)."""
        with ui.working(console, status, enabled=not IDE):
            return await self.bridge.send_prompt(**kwargs)

    # --- вложения (zip / изображения) и формат отправки zip ---
    ATTACH_EXT = (".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

    def _emit_attachments(self):
        emit("attachments", files=[{"name": p.name, "size": p.stat().st_size if p.exists() else 0} for p in self.attachments])

    def add_attachment(self, raw: str):
        path = Path(raw.strip().strip('"')).expanduser()
        if not path.is_file():
            say(ui.err(t("Файл не найден: {path}", path=path)), "err")
            return
        if path.suffix.lower() not in self.ATTACH_EXT:
            say(ui.err(t("Тип {ext} не поддерживается. Можно: zip, png, jpg, webp, gif", ext=path.suffix or "?")), "err")
            return
        if path.stat().st_size > 25 * 1024 * 1024:
            say(ui.err(t("Файл больше 25 МБ — чат его не примет.")), "err")
            return
        if not any(p == path for p in self.attachments):
            self.attachments.append(path)
        self._emit_attachments()
        say(ui.ok(t("Прикреплено: {name} (уйдёт со следующим сообщением)", name=path.name)), "ok")

    def _pack_for_task(self, user_task: str, canary: str):
        """Собирает контекст: весь проект или (автоподбор) только файлы под задачу. -> (bundle|None, task_text, files, tokens)."""
        first = not self.session_initialized
        if not self.config.auto_context:
            if not first:
                return None, user_task, 0, 0
            bundle, n, tokens = self.packer.write_context_bundle_file(canary=canary)
            self.sent_files = set()
            self.scope_partial = False
            emit("context", mode="all", files=n, tokens=tokens, total_files=n, total_tokens=tokens, selected=[])
            return bundle, user_task, n, tokens

        emit("phase", phase="selecting")
        sel = self.selector().select(user_task)
        emit("context", **sel.to_event())
        if first:
            partial = sel.mode == "auto"
            note = ""
            if partial:
                note = self.prompts.pack.SCOPE_NOTE.format(n=len(sel.items), total=sel.total_files)
            bundle, n, tokens = self.packer.write_context_bundle_file(canary=canary, selected=sel.paths, scope_note=note)
            self.sent_files = set(sel.rels)
            self.scope_partial = partial
            return bundle, user_task, n, tokens
        # тот же чат: дошлём только новые нужные файлы (и изменённые патчами)
        new = sorted((sel.rels - self.sent_files) | (self.dirty_files & sel.rels))
        if new and sel.mode == "auto":
            self.sent_files.update(new)
            fresh = self.packer.pack_files(new)
            user_task = self.prompts.dirty_sync(fresh, user_task)
            self.dirty_files -= set(new)
        return None, user_task, len(new), 0

    async def execute_vibe_task(self, user_task: str, two_phase_plan: bool = False):
        clear_stop()
        self.prompts.begin_task(user_task)
        canary = uuid.uuid4().hex[:6]
        emit("phase", phase="packing")
        bundle_path, user_task, file_count, tokens = self._pack_for_task(user_task, canary)
        if bundle_path:
            say(ui.dim(t("Упаковано файлов: {n} (~{tokens} токенов) -> {name}", n=file_count, tokens=f"{tokens:,}", name=bundle_path.name)))
        user_task = self._with_dirty_sync(user_task)
        attach = bundle_path if not self.session_initialized else None
        sys_patch = self.prompts.system_patcher(self.scope_partial)

        if two_phase_plan:
            say(ui.step(t("Фаза 1: составление архитектурного плана ({title})", title=self.title)))
            plan_response = await self.ask_model(
                t("Vibi думает над планом…"),
                prompt=self.prompts.plan_task(user_task),
                system_instruction=self.prompts.system_planner(),
                attachment_path=attach,
                new_chat=not self.session_initialized,
                canary=canary,
            )
            self.session_initialized = True
            self.dirty_files.clear()
            self._report_transport()
            attach = None
            plan_response = await self._fulfil_need_files(plan_response)

            show_answer(plan_response, t("План реализации"), kind="plan")

            if not self.yolo_mode:
                user_decision = self.ask_text(
                    t("[bold cyan]Утвердить план?[/bold cyan] (y — кодить / n — отмена / или введите уточнения к плану)"),
                    default="y",
                )
                if user_decision.strip().lower() in ("n", "no", "нет", "отмена", "cancel"):
                    say(ui.err(t("Задача отменена пользователем.")), "err")
                    return
                elif user_decision.strip().lower() not in ("y", "yes", "да", "ok", "ок", "go"):
                    user_task = self.prompts.plan_revise(user_decision)
                else:
                    user_task = self.prompts.plan_approved()
            else:
                user_task = self.prompts.plan_approved()
            code_prompt = user_task
        else:
            code_prompt = self.prompts.task(user_task)

        say(ui.step(t("Генерация кода и SEARCH/REPLACE патчей…")))
        response = await self.ask_model(
            t("Vibi пишет код…"),
            prompt=code_prompt,
            system_instruction=sys_patch,
            attachment_path=attach,
            new_chat=not self.session_initialized,
            canary=canary,
        )
        self.session_initialized = True
        self.dirty_files.clear()
        self._report_transport()
        response = await self._fulfil_need_files(response)
        await self._apply_and_auto_heal(response)

    async def _fulfil_need_files(self, response: str) -> str:
        """Модель просит файлы, которых нет в автоподобранном контексте (NEED_FILES) — досылаем и продолжаем (до 2 раз)."""
        for _ in range(2):
            wanted = parse_need_files(response)
            if not wanted:
                return response
            allowed = {f.relative_to(self.root).as_posix() for f in self.packer.collect_files()}
            ok = [w for w in wanted if w in allowed]
            if not ok:
                say(ui.warn(t("Модель запросила файлы, которых нет в проекте или они исключены: {files}", files=", ".join(wanted))), "warn")
                return response
            say(ui.info(t("Модель запросила файлы: {files}", files=", ".join(ok))))
            emit("context", mode="extra", extra=ok)
            self.sent_files.update(ok)
            emit("phase", phase="sending")
            response = await self.ask_model(
                t("Vibi досылает файлы…"),
                prompt=self.prompts.need_files(self.packer.pack_files(ok)),
                system_instruction=self.prompts.system_patcher(True),
                new_chat=False,
            )
        return response

    def _report_transport(self):
        self._emit_attachments()
        tr = self.bridge.last_transport
        if tr not in ("-", "none"):
            say(ui.dim(t("Контекст передан способом: {mode}", mode=tr)))

    def _with_dirty_sync(self, task: str) -> str:
        """Если после отправки контекста файлы менялись, дописываем их актуальное содержимое в запрос."""
        if not (self.session_initialized and self.dirty_files):
            return task
        fresh = self.packer.pack_files(sorted(self.dirty_files))
        return self.prompts.dirty_sync(fresh, task)

    def _track(self, results):
        for r in results:
            if r.action != "FAILED":
                self.dirty_files.add(r.file_path)
                self.sent_files.add(r.file_path)

    def _report_results(self, results):
        for r in results:
            emit("patch", file=r.file_path, action=r.action, message=r.message, blocks=r.blocks_applied)
        if IDE:
            return
        for r in results:
            say(f"  {ui.icon('arrow')} {r.file_path}: {r.action} ({r.message})")

    async def _repair_failed_blocks(self, results, rounds: int = 2):
        """Если SEARCH-блоки не совпали — отправляем модели реальный файл и просим переделать только их."""
        for attempt in range(1, rounds + 1):
            bad = [r for r in results if r.failed_blocks]
            if not bad:
                return
            say(ui.warn(t("Не совпали SEARCH-блоки в {n} файл(ах) — прошу модель переписать (попытка {attempt}/{rounds})…", n=len(bad), attempt=attempt, rounds=rounds)), "warn")
            emit("phase", phase="healing")
            parts = []
            for r in bad:
                fp = self.root / r.file_path
                actual = fp.read_text(encoding="utf-8", errors="replace") if fp.exists() else ""
                blocks = "\n---\n".join(r.failed_blocks)
                parts.append(self.prompts.pack.REPAIR_PART.format(path=r.file_path, actual=actual, blocks=blocks))
            resp = await self.ask_model(
                t("Vibi чинит патчи…"),
                prompt=self.prompts.repair("\n\n".join(parts)),
                system_instruction=self.prompts.system_patcher(self.scope_partial),
                new_chat=False,
            )
            show_answer(resp, t("Исправленные патчи #{n}", n=attempt), kind="repair")
            results, _ = self.patcher.parse_and_apply(resp)
            self._track(results)
            self._report_results(results)

    async def _apply_and_auto_heal(self, model_response: str):
        show_answer(model_response, t("Ответ {title}", title=self.title), kind="answer")
        emit("phase", phase="applying")

        results, suggested_cmds = self.patcher.parse_and_apply(model_response)
        self._track(results)

        if results:
            self._report_results(results)
            if any(r.action == "FAILED" for r in results):
                self.mood = "error"
            if not IDE:
                res_table = ui.new_table(t("Примененные изменения файлов"), show_lines=True)
                res_table.add_column(t("Файл"), style=ui.BRAND2)
                res_table.add_column(t("Действие"), style="bold")
                res_table.add_column(t("Статус"))
                for r in results:
                    color = ui.OK if r.action != "FAILED" else f"bold {ui.ERR}"
                    res_table.add_row(r.file_path, f"[{color}]{r.action}[/{color}]", r.message)
                console.print(res_table)
        else:
            say(ui.dim(t("В ответе не обнаружено блоков модификации файлов.")))

        await self._repair_failed_blocks(results)

        for cmd in suggested_cmds:
            run_it = self.yolo_mode or self.ask_confirm(t("Выполнить предложенную команду `[bold yellow]{cmd}[/bold yellow]`?", cmd=cmd), default=True)
            if run_it:
                say(f"[{ui.BRAND2}]$ {cmd}[/]")
                emit("cmd", command=cmd, status="run")
                exec_res = self.runner.run_cmd(cmd)
                if exec_res.succeeded:
                    emit("cmd", command=cmd, status="ok", code=0)
                    say(ui.ok(t("Команда выполнена успешно.")), "ok")
                else:
                    emit("cmd", command=cmd, status="fail", code=exec_res.returncode, output=exec_res.combined_output(2000))
                    say(ui.err(t("Команда завершилась с ошибкой (код {code}):", code=exec_res.returncode)) + f"\n{exec_res.stderr}", "err")
            else:
                emit("cmd", command=cmd, status="skipped")

        if self.config.verify_cmd and results:
            await self.run_auto_healing_loop(self.config.verify_cmd)

    async def run_auto_healing_loop(self, verify_cmd: str):
        total = self.config.max_heal_retries
        for attempt in range(1, total + 1):
            emit("phase", phase="verifying")
            say("\n" + ui.step(t("Проверка сборки/тестов (попытка {attempt}/{total}): `{cmd}`", attempt=attempt, total=total, cmd=verify_cmd)))
            exec_res = self.runner.run_cmd(verify_cmd)

            if exec_res.succeeded:
                emit("verify", command=verify_cmd, attempt=attempt, total=total, ok=True)
                self.mood = "happy"
                say(ui.ok(t("Сборка и тесты (`{cmd}`) прошли без единой ошибки!", cmd=verify_cmd)), "ok")
                return

            emit("verify", command=verify_cmd, attempt=attempt, total=total, ok=False, output=exec_res.combined_output(max_chars=3000))
            if not IDE:
                console.print(ui.error_panel(exec_res.combined_output(max_chars=3000), t("Ошибка верификации (код {code}) — запускаю авто-исправление", code=exec_res.returncode)))

            say(ui.warn(t("Отправляю лог ошибки обратно в модель для автоматического исправления…")), "warn")
            emit("phase", phase="healing")
            fix_response = await self.ask_model(
                t("Vibi исправляет ошибки…"),
                prompt=self.prompts.heal(verify_cmd, exec_res.combined_output()),
                system_instruction=self.prompts.system_patcher(self.scope_partial),
                new_chat=False,
            )

            show_answer(fix_response, t("Патч авто-исправления #{n}", n=attempt), kind="heal")
            results, _ = self.patcher.parse_and_apply(fix_response)
            self._track(results)
            self._report_results(results)
            await self._repair_failed_blocks(results)

        self.mood = "error"
        say(ui.err(t("Достигнут лимит попыток авто-исправления. Проверьте вывод выше или используйте /undo.")), "err")

    async def continue_stopped(self):
        """Продолжает ответ, остановленный пользователем (тот же чат)."""
        if not self.session_initialized:
            say(ui.err(t("Нечего продолжать: в этом чате ещё не было запроса.")), "err")
            return
        clear_stop()
        resp = await self.ask_model(
            t("Vibi продолжает ответ…"),
            prompt=self.prompts.continue_after_stop(),
            system_instruction=self.prompts.system_patcher(self.scope_partial),
            new_chat=False,
        )
        await self._apply_and_auto_heal(await self._fulfil_need_files(resp))

    def on_stopped(self, partial: str):
        self.last_partial = partial or ""
        if partial:
            self.session_initialized = True  # сообщение с контекстом уже ушло в чат
            show_answer(partial, t("Ответ остановлен"), kind="partial")
        emit("stopped")
        self.mood = "sleep"
        say(ui.warn(t("Остановлено. Патчи не применялись. /continue — продолжить ответ.")), "warn")

    async def check_ui_and_heal(self, url: str):
        console.print(ui.info(t("Запуск Playwright-субагента для проверки интерфейса: {url}", url=url)))
        screenshot_path, errors, title = await self.verifier.inspect_url(url)
        if errors:
            err_text = "\n".join(errors)
            if IDE:
                emit("verify", command=f"check_ui {url}", attempt=1, total=1, ok=False, output=err_text)
            else:
                console.print(ui.error_panel(err_text, t("Обнаружены ошибки в консоли браузера")))
            if self.ask_confirm(t("Отправить ошибки браузера и скриншот в модель для авто-починки?"), default=True):
                prompt = self.prompts.pack.CHECK_UI.format(url=url, title=title, errors=err_text)
                resp = await self.ask_model(
                    t("Vibi разбирает ошибки браузера…"),
                    prompt=prompt,
                    system_instruction=self.prompts.system_patcher(self.scope_partial),
                    attachment_path=screenshot_path,
                )
                await self._apply_and_auto_heal(resp)
        else:
            self.mood = "happy"
            console.print(ui.ok(t("Страница '{title}' открылась чисто, ошибок в консоли браузера нет!", title=title)))
            if screenshot_path:
                console.print(ui.dim(t("Скриншот сохранен в: {name}", name=screenshot_path.name)))

    async def emit_models(self):
        """Список моделей для IDE (событие models). Для AI Studio — каталог ID, для Gemini/Claude — меню на странице."""
        try:
            entries, current, levels = await self.bridge.list_models()
        except Exception as e:
            emit("models", provider=self.config.provider, current=self.config.model, entries=[], levels=[], error=str(e))
            return
        out = []
        for e in entries:
            if e.get("kind", "model") != "model":
                continue
            desc = e.get("desc") if "desc" in e else e["full"][len(e["name"]):].lstrip(" |")
            out.append({"name": e["name"], "desc": desc, "checked": bool(e.get("checked"))})
        emit("models", provider=self.config.provider, current=self.config.model or current, entries=out, levels=levels,
             catalog=catalog_for(self.config.provider) if self.bridge.prov.static_models else [])

    async def handle_model_command(self, arg: str):
        try:
            if not arg:
                if IDE:
                    await self.emit_models()
                    return
                entries, current, levels = await self.bridge.list_models()
                if not entries:
                    console.print(ui.err(t("Не удалось получить список моделей (переключатель не найден на странице).")))
                    return
                models = [e for e in entries if e.get("kind", "model") == "model"]
                self.model_names = [e["name"] for e in models]
                table = ui.new_table(t("Модели {title} (из интерфейса)", title=self.title))
                table.add_column("#", style=ui.BRAND2)
                table.add_column(t("Название"), style="bold")
                table.add_column(t("Описание"), style="dim")
                table.add_column("", style=ui.OK)
                for i, e in enumerate(models, 1):
                    desc = e.get("desc") if "desc" in e else e["full"][len(e["name"]):].lstrip(" |")
                    chosen = self.config.model and self.bridge._norm(self.config.model) == self.bridge._norm(e["name"])
                    table.add_row(str(i), e["name"], desc, t("◀ выбрана") if chosen else (ui.icon("ok") if e["checked"] else ""))
                console.print(table)
                locked = [e["name"] for e in entries if e.get("kind") == "locked"]
                if locked:
                    console.print(ui.dim(t("Недоступны в вашем плане: {names}", names=", ".join(locked))))
                if current:
                    console.print(ui.dim(t("Сейчас в интерфейсе: {name}", name=current)))
                if levels:
                    console.print(t("Уровни рассуждений: [bold]{levels}[/bold]  [dim](текущий: {cur})[/dim]", levels=", ".join(levels), cur=self.config.reasoning or t("по умолчанию")))
                console.print(ui.dim(t("Примеры: `/model 2`, `/model 3.1 pro high`, `/model 4 argon medium`; сброс: `/model default`")))
                return
            if arg.lower() in ("default", "auto", "reset"):
                self.config.model = ""
                self.config.reasoning = ""
                self.config.save_project_config()
                console.print(ui.ok(t("Выбор модели и рассуждений сброшен.")))
                return
            wanted, level = parse_model_args(arg)
            ok, info, lvl_res = await self.bridge.choose_model(wanted, level)
            if not ok:
                console.print(ui.err(info))
                return
            self.config.model = info  # храним название, а не номер: номера в меню меняются
            msg = ui.ok(t("Модель: {name}", name=info))
            if level:
                if lvl_res and lvl_res[0]:
                    self.config.reasoning = level
                    msg += t(" · рассуждения: {level}", level=lvl_res[1])
                else:
                    msg += "\n" + ui.warn(t("Уровень '{level}' не установлен: {why}", level=level, why=lvl_res[1] if lvl_res else "—"))
            self.config.save_project_config()
            self._new_session()
            console.print(msg + t(". Следующий запрос откроет новый чат с контекстом проекта."))
        except Exception as e:
            console.print(ui.err(t("Ошибка /model: {e}", e=e)))

    async def handle_reasoning_command(self, arg: str):
        try:
            if not arg:
                cur = self.config.reasoning or t("по умолчанию")
                console.print(
                    t("Рассуждения ({title}): [bold]{cur}[/bold]", title=self.title, cur=cur) + "\n"
                    + t("Уровни: `/reasoning low|medium|high|off` — подбираются по пунктам меню модели (Fast/Thinking/Pro и т.п.; у Claude — переключатель Extended thinking). Точное название пункта тоже подходит: `/reasoning extended`. Сброс: `/reasoning default`.") + "\n"
                    + ui.dim(t("Посмотреть доступные пункты: `/model`."))
                )
                return
            if arg.lower() in ("default", "reset"):
                self.config.reasoning = ""
                self.config.save_project_config()
                console.print(ui.ok(t("Уровень рассуждений сброшен.")))
                return
            ok, info = await self.bridge.choose_reasoning(arg)
            if ok:
                self.config.reasoning = arg
                self.config.save_project_config()
                self._new_session()
                console.print(ui.ok(t("Рассуждения: {arg} → пункт «{item}». Применится в новом чате.", arg=arg, item=info)))
            else:
                console.print(ui.err(info))
        except Exception as e:
            console.print(ui.err(t("Ошибка /reasoning: {e}", e=e)))

    def _new_session(self):
        self.bridge.reset_conversation()
        self.session_initialized = False
        self.dirty_files.clear()
        self.sent_files.clear()
        self.scope_partial = False

    def handle_provider_command(self, arg: str):
        arg = arg.lower()
        if arg not in PROVIDERS:
            lines = [t("Сейчас: [bold]{title}[/bold]. Использование: `/provider gemini`, `/provider claude` или `/provider aistudio`", title=self.title)]
            for k, pv in PROVIDERS.items():
                lines.append(f"  [{ui.BRAND2}]{k}[/]: {pv.url}  (Chrome: {self.config.cdp_urls[k]})")
            console.print("\n".join(lines))
            return
        self.config.provider = arg
        self.config.save_project_config()
        self._new_session()
        emit("setting", key="provider", value=arg)
        pv = PROVIDERS[arg]
        default = t("по умолчанию")
        console.print(
            ui.ok(t("Провайдер: {title} (модель: {model}, рассуждения: {reasoning}).", title=pv.title, model=self.config.model or default, reasoning=self.config.reasoning or default)) + "\n"
            + ui.dim(t("Нужен запущенный Chrome с отладкой на {cdp} и выполненный вход на {url} (scripts/start_chrome_{key}_*).", cdp=self.config.cdp_url, url=pv.url, key=arg))
        )

    def init_project_files(self):
        self.config.save_project_config()
        if not self.config.vibe_rules_file.exists():
            default_rules = (
                t("# Правила и конвенции проекта (VIBE.md)") + "\n\n"
                + t("- Пиши чистый, модульный и самодокументируемый код.") + "\n"
                + t("- Сохраняй существующий стиль именования и структуру папок.") + "\n"
                + t("- Не удаляй существующую бизнес-логику без явного запроса.") + "\n"
            )
            self.config.vibe_rules_file.write_text(default_rules, encoding="utf-8")
        console.print(ui.ok(t("Созданы файлы конфигурации `.vibe.json` и `VIBE.md`.")))

    def handle_lang_command(self, arg: str):
        """/lang en|ru|auto — язык интерфейса CLI, IDE-событий и промптов."""
        a = arg.strip().lower()
        if a not in LANGS + ("auto",):
            names = ", ".join(f"[{ui.BRAND2}]{k}[/] — {v}" for k, v in LANG_TITLES.items())
            say(t("Язык: [bold]{cur}[/bold]. Варианты: {names}, [{c}]auto[/] — по языку системы. `/lang en`", cur=LANG_TITLES[get_lang()], names=names, c=ui.BRAND2))
            return
        self.config.language = a
        cur = set_lang(a)
        self.config.save_project_config()
        emit("setting", key="language", value=cur)
        say(ui.ok(t("Язык интерфейса: {name}", name=LANG_TITLES[cur])), "ok")

    async def read_input(self) -> str:
        if IDE:
            emit("phase", phase="idle")
            line = sys.stdin.readline()
            if line == "":
                raise EOFError
            return line.rstrip("\r\n").replace(" ⏎ ", "\n").strip()
        if self.session is not None:
            from prompt_toolkit.formatted_text import HTML

            return (await self.session.prompt_async(HTML(ui.prompt_html(self.mood)))).strip()
        return console.input(ui.prompt_markup(self.mood) + " ").strip()

    async def run_command(self, name: str, arg: str) -> bool:
        """Выполняет команду. Возвращает False, если нужно выйти."""
        if name == "exit":
            return False
        if name == "context":
            self.show_context_stats()
        elif name == "undo":
            ok, msg = self.patcher.undo_last_snapshot()
            console.print(ui.ok(msg) if ok else ui.err(msg))
        elif name == "init":
            self.init_project_files()
        elif name == "reset":
            self._new_session()
            console.print(ui.ok(t("Сессия чата сброшена. Следующий запрос создаст новый диалог с актуальным контекстом.")))
        elif name == "help":
            show_help()
        elif name == "lang":
            self.handle_lang_command(arg)
        elif name == "provider":
            self.handle_provider_command(arg)
        elif name == "reasoning":
            await self.handle_reasoning_command(arg)
        elif name == "model":
            await self.handle_model_command(arg)
        elif name == "transport":
            arg = arg.lower()
            if arg in VALID_TRANSPORTS:
                self.config.transport = arg
                self.config.save_project_config()
                emit("setting", key="transport", value=arg)
                console.print(ui.ok(t("Способ передачи контекста: {mode}", mode=arg)))
            else:
                console.print(t("Сейчас: [bold]{cur}[/bold]. Варианты:", cur=self.config.transport) + "\n" + "\n".join(f"  [{ui.BRAND2}]{k}[/] — {transport_info(k)[1]}" for k in VALID_TRANSPORTS))
        elif name == "attach":
            if not arg:
                say(t("Использование: /attach <путь к zip или изображению>"))
            else:
                self.add_attachment(arg)
        elif name == "attach_clear":
            self.attachments.clear()
            self._emit_attachments()
            say(ui.ok(t("Вложения убраны")), "ok")
        elif name == "yolo":
            a = arg.lower()
            if a in ("on", "off", "вкл", "выкл", "1", "0"):
                self.yolo_mode = a in ("on", "вкл", "1")
                emit("setting", key="yolo", value=self.yolo_mode)
                say(ui.ok(t("Без подтверждений: {state}", state=t("включено") if self.yolo_mode else t("выключено"))), "ok")
            else:
                say(t("Без подтверждений: [bold]{state}[/bold]. /yolo on|off", state=t("вкл") if self.yolo_mode else t("выкл")))
        elif name == "human":
            a = arg.lower()
            if a in ("on", "off", "old", "вкл", "выкл", "старый", "1", "0"):
                if a in ("old", "старый"):
                    self.config.human_mode = "old"
                    self.config.human_input = True
                    state_str = "old"
                elif a in ("on", "вкл", "1"):
                    self.config.human_mode = "on"
                    self.config.human_input = True
                    state_str = t("включено")
                else:
                    self.config.human_mode = "off"
                    self.config.human_input = False
                    state_str = t("выключено")
                self.config.save_project_config()
                emit("setting", key="human", value=self.config.human_mode if self.config.human_input else False)
                say(ui.ok(t("Человекоподобный ввод: {state}", state=state_str)), "ok")
            else:
                cur_state = "old" if (self.config.human_input and self.config.human_mode == "old") else (t("вкл") if self.config.human_input else t("выкл"))
                say(t("Человекоподобный ввод: [bold]{state}[/bold]. /human on|off", state=cur_state))
        elif name == "verify_cmd":
            self.config.verify_cmd = arg
            self.config.save_project_config()
            console.print(ui.ok(t("Команда авто-проверки установлена: `{cmd}`", cmd=arg)))
        elif name == "fix":
            cmd = arg or self.config.verify_cmd
            if not cmd:
                console.print(ui.err(t("Укажите команду для проверки, например: `/fix npm run build` или `/fix pytest`")))
            else:
                await self.run_auto_healing_loop(cmd)
        elif name == "check_ui":
            await self.check_ui_and_heal(arg or "http://localhost:3000")
        elif name == "autocontext":
            a = arg.lower()
            if a in ("on", "off", "вкл", "выкл", "1", "0"):
                self.config.auto_context = a in ("on", "вкл", "1")
                self.config.save_project_config()
                self._new_session()
                emit("setting", key="auto_context", value=self.config.auto_context)
                say(ui.ok(t("Автоподбор контекста: {state}. Применится в новом чате.", state=t("включён") if self.config.auto_context else t("выключен"))), "ok")
            else:
                say(t("Автоподбор контекста: [bold]{state}[/bold] (до {files} файлов, ~{budget} токенов). `/autocontext on|off`",
                      state=t("вкл") if self.config.auto_context else t("выкл"), files=self.config.auto_context_max_files, budget=f"{self.config.auto_context_budget:,}"))
        elif name == "promptstyle":
            a = arg.lower()
            if a in VALID_STYLES:
                self.config.prompt_style = a
                self.prompts.set_style(a)
                self.config.save_project_config()
                emit("setting", key="prompt_style", value=a)
                say(ui.ok(t("Стиль промпта: {name}", name=style_title(a))), "ok")
            else:
                say(t("Стили: {styles}. Сейчас: [bold]{cur}[/bold]", styles=", ".join(VALID_STYLES), cur=self.config.prompt_style))
        elif name == "autocontext_set":
            try:
                mf, _, bud = arg.partition(" ")
                self.config.auto_context_max_files = max(1, int(mf))
                if bud:
                    self.config.auto_context_budget = max(2000, int(bud))
                self.config.save_project_config()
                emit("setting", key="auto_context_limits", value=[self.config.auto_context_max_files, self.config.auto_context_budget])
            except ValueError:
                say(ui.err(t("Формат: /autocontext_set <макс. файлов> \\[токенов]")), "err")
        elif name == "continue":
            await self.continue_stopped()
        elif name == "list_models":
            await self.emit_models()
        elif name == "plan":
            if not arg:
                console.print(ui.err(t("Укажите задачу: `/plan <что сделать>`")))
            else:
                await self.execute_vibe_task(arg, two_phase_plan=True)
        return True

    async def interactive_loop(self):
        if IDE:
            self.emit_hello()
        else:
            self.print_banner()

        while True:
            try:
                user_input = await self.read_input()
            except (KeyboardInterrupt, EOFError):
                console.print("\n" + ui.vibi_says(t("До встречи!"), "sleep"))
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            kind, name, arg, hints = resolve(user_input)

            # команды никогда не уходят в модель как задача
            if kind == "ambiguous":
                console.print(ui.warn(t("Команда неоднозначна: {names}", names=", ".join("/" + h for h in hints))))
                continue
            if kind == "unknown":
                tip = " " + t("Возможно: {names}.", names=", ".join("/" + h for h in hints)) if hints else ""
                console.print(ui.err(t("Неизвестная команда.")) + f"{tip} " + t("Список: /help"))
                continue

            try:
                if kind == "command":
                    if not await self.run_command(name, arg):
                        break
                else:
                    self.mood = "idle"
                    await self.execute_vibe_task(arg, two_phase_plan=False)
                    if self.mood == "idle":
                        self.mood = "happy"
            except GenerationStopped as e:
                self.on_stopped(e.partial)
            except Exception as e:
                self.mood = "error"
                emit("error", text=str(e))
                say(ui.err(t("Ошибка выполнения:") + f" {e}"), "err")


def _pre_language() -> None:
    """--lang нужен до разбора остальных аргументов, чтобы --help уже был на нужном языке."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang")
    known, _ = pre.parse_known_args()
    set_lang(known.lang)


def main():
    _pre_language()
    parser = argparse.ArgumentParser(description=t("Vibe CLI — локальный вайбкодер на вашей подписке (Gemini / Claude / AI Studio)"))
    parser.add_argument("prompt", nargs="*", help=t("Одноразовая задача (если не указана — запускается интерактивный режим)"))
    parser.add_argument("--dir", "-d", default=".", help=t("Путь к папке проекта (по умолчанию текущая)"))
    parser.add_argument("--plan", "-p", action="store_true", help=t("Запустить в двухфазном режиме (Сначала План -> Затем Код)"))
    parser.add_argument("--yolo", "-y", action="store_true", help=t("Автоматически подтверждать все планы и команды без вопросов"))
    parser.add_argument("--provider", choices=list(PROVIDERS), help=t("ИИ-провайдер: gemini, claude или aistudio"))
    parser.add_argument("--reasoning", help=t("Уровень рассуждений: low|medium|high|off или название пункта"))
    parser.add_argument("--model", help=t("Модель (номер или часть названия, например: pro)"))
    parser.add_argument("--transport", choices=list(VALID_TRANSPORTS), help=t("Способ передачи файлов в чат"))
    parser.add_argument("--auto-context", choices=["on", "off"], help=t("Автоподбор контекста по описанию задачи"))
    parser.add_argument("--prompt-style", choices=list(VALID_STYLES), help=t("Стиль промпта, вставляемого в чат"))
    parser.add_argument("--lang", choices=list(LANGS) + ["auto"], help=t("Язык интерфейса и промптов: en, ru или auto (по языку системы)"))
    parser.add_argument("--list-models-json", action="store_true", help=t("Вывести список моделей событием models и выйти (для IDE)"))
    args = parser.parse_args()

    orchestrator = VibeOrchestrator(Path(args.dir), yolo_mode=args.yolo)
    if args.lang:
        orchestrator.config.language = args.lang
        set_lang(args.lang)
    if args.provider:
        orchestrator.config.provider = args.provider
    if args.reasoning:
        orchestrator.config.reasoning = args.reasoning
    if args.model:
        orchestrator.config.model = args.model
    if args.transport:
        orchestrator.config.transport = args.transport
    if args.auto_context:
        orchestrator.config.auto_context = args.auto_context == "on"
    if args.prompt_style:
        orchestrator.config.prompt_style = args.prompt_style
        orchestrator.prompts.set_style(args.prompt_style)

    if args.list_models_json:
        asyncio.run(orchestrator.emit_models())
        return

    if args.prompt:
        task_text = " ".join(args.prompt)
        if not IDE:
            console.print(ui.vibi_says(t("Беру задачу в работу ({title})…", title=orchestrator.title), "work"))
        try:
            asyncio.run(orchestrator.execute_vibe_task(task_text, two_phase_plan=args.plan))
        except GenerationStopped as e:
            orchestrator.on_stopped(e.partial)
    else:
        asyncio.run(orchestrator.interactive_loop())


if __name__ == "__main__":
    main()

