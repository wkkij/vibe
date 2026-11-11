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

from core.commands import COMMANDS, parse_model_args, resolve
from core.completion import make_session
from core.config import SYSTEM_PROMPT_PATCHER, SYSTEM_PROMPT_PLANNER, TRANSPORT_INFO, VALID_TRANSPORTS, VibeConfig
from core.context_packer import ContextPacker
from core.context_selector import ContextSelector, parse_need_files
from core.events import GenerationStopped, clear_stop, emit, ide_mode, strip_markup
from core.gemini_bridge import WebChatBridge
from core.patcher import DiffPatcher
from core.prompts import STYLE_TITLES, VALID_STYLES, PromptBook, describe_styles
from core.providers import PROVIDERS, catalog_for
from core.runner import BrowserVerifier, TerminalRunner

console = Console()
IDE = ide_mode()  # Vibe IDE: вместо рамок и таблиц CLI шлёт события (core/events.py), интерфейс рисует IDE
VERSION = "0.01.0"


def say(text: str, level: str = "info") -> None:
    """Строка статуса: в терминале — rich-разметка, в IDE — событие журнала."""
    if IDE:
        emit("log", level=level, text=strip_markup(text))
    else:
        console.print(text)


def show_answer(md: str, title: str, border: str, kind: str = "answer") -> None:
    if IDE:
        emit("answer", text=md, title=title, kind=kind)
    else:
        console.print(Panel(Markdown(md), title=title, border_style=border))

HELP_TEXT = """[bold]Команды:[/bold]
  <текст>              задача: упаковать проект → модель → патчи → проверка
  /plan <задача>       сначала план, потом код
  /provider gemini|claude|aistudio   переключить ИИ-провайдера (Gemini и AI Studio делят один Chrome и аккаунт)
  /model [имя|№] [low|medium|high]  список / выбор модели и уровня (`/model 3.1 pro high`)
  /reasoning [low|medium|high|off|имя]  уровень рассуждений
  /transport [способ]  как передавать контекст: auto, file, paste, inline, base64, zip
  /verify_cmd <cmd>    команда проверки после патчей
  /fix [cmd]           прогнать проверку и починить ошибки
  /check_ui [url]      проверить фронтенд в headless-браузере
  /undo                откатить последний патч
  /context             что попадёт в контекст
  /reset               новый чат
  /init                создать .vibe.json и VIBE.md
  /exit                выход"""


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
            prompt_style=c.prompt_style, styles=describe_styles(), transport=c.transport, yolo=self.yolo_mode, transports=[{"id": k, "title": TRANSPORT_INFO[k][0], "desc": TRANSPORT_INFO[k][1]} for k in VALID_TRANSPORTS], verify_cmd=c.verify_cmd,
            root=str(self.root),
        )

    def ask_confirm(self, text: str, default: bool = True) -> bool:
        if self.yolo_mode:
            say("[dim]⚡ Без подтверждений: выполняю автоматически[/dim]")
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
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column(style="white")
        table.add_row("Проект:", str(self.root))
        table.add_row("Подключение:", "[bold green]Chrome (CDP)[/bold green] (без платного API)")
        table.add_row(
            "Команда авто-проверки:",
            f"[yellow]{self.config.verify_cmd}[/yellow]" if self.config.verify_cmd else "[dim]не задана (укажите через /verify_cmd)[/dim]",
        )
        table.add_row("Провайдер:", f"[bold magenta]{self.title}[/bold magenta]  [dim](/provider)[/dim]")
        table.add_row("Модель:", f"[bold]{self.config.model or 'по умолчанию'}[/bold]  [dim](/model)[/dim]")
        table.add_row("Рассуждения:", f"[bold]{self.config.reasoning or 'по умолчанию'}[/bold]  [dim](/reasoning)[/dim]")
        table.add_row("Передача контекста:", f"{self.config.transport}  [dim](/transport)[/dim]")
        table.add_row("Auto-Heal итераций:", str(self.config.max_heal_retries))

        console.print(
            Panel(
                table,
                title="[bold magenta]⚡ Vibe CLI — Персональный локальный вайбкодер (Google AI Pro)[/bold magenta]",
                subtitle="[dim]Команды: /plan, /fix, /undo, /context, /provider, /model, /reasoning, /transport, /check_ui, /init, /help, /exit[/dim]",
                border_style="bright_blue",
            )
        )

    def show_context_stats(self):
        files = self.packer.collect_files()
        _, count, approx_tokens = self.packer.pack_repository()
        console.print(
            Panel(
                f"Найдено исходных файлов: [bold cyan]{count}[/bold cyan]\n"
                f"Примерный объем контекста: [bold green]~{approx_tokens:,} токенов[/bold green] "
                f"(Окно Google AI Pro вмещает до 1,000,000+ токенов)\n\n"
                f"[dim]{self.packer.build_tree_string(files[:35])}"
                + (f"\n  ... и еще {len(files) - 35} файлов[/dim]" if len(files) > 35 else "[/dim]"),
                title="📦 Контекст репозитория",
                border_style="cyan",
            )
        )

    # --- вложения (zip / изображения) и формат отправки zip ---
    ATTACH_EXT = (".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

    def _emit_attachments(self):
        emit("attachments", files=[{"name": p.name, "size": p.stat().st_size if p.exists() else 0} for p in self.attachments])

    def add_attachment(self, raw: str):
        path = Path(raw.strip().strip('"')).expanduser()
        if not path.is_file():
            say(f"[red]Файл не найден: {path}[/red]", "err")
            return
        if path.suffix.lower() not in self.ATTACH_EXT:
            say(f"[red]Тип {path.suffix or '?'} не поддерживается. Можно: zip, png, jpg, webp, gif[/red]", "err")
            return
        if path.stat().st_size > 25 * 1024 * 1024:
            say("[red]Файл больше 25 МБ — чат его не примет.[/red]", "err")
            return
        if not any(p == path for p in self.attachments):
            self.attachments.append(path)
        self._emit_attachments()
        say(f"[green]📎 Прикреплено: {path.name} (уйдёт со следующим сообщением)[/green]", "ok")

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
                note = (
                    f"Включены {len(sel.items)} из {sel.total_files} файлов проекта, выбранные по описанию задачи. "
                    "Остальные перечислены только в <project_overview>. Нужен другой файл — ответь строкой NEED_FILES: путь1, путь2."
                )
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
            say(f"[dim]📦 Упаковано файлов: {file_count} (~{tokens:,} токенов) -> {bundle_path.name}[/dim]")
        user_task = self._with_dirty_sync(user_task)
        attach = bundle_path if not self.session_initialized else None
        sys_patch = self.prompts.system_patcher(self.scope_partial)

        if two_phase_plan:
            say(f"[bold yellow]🧠 Фаза 1: Составление архитектурного плана ({self.title})...[/bold yellow]")
            plan_response = await self.bridge.send_prompt(
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

            show_answer(plan_response, "📋 План реализации", "yellow", kind="plan")

            if not self.yolo_mode:
                user_decision = self.ask_text(
                    "[bold cyan]Утвердить план?[/bold cyan] (y — кодить / n — отмена / или введите уточнения к плану)",
                    default="y",
                )
                if user_decision.strip().lower() in ("n", "no", "нет", "отмена"):
                    say("[red]Задача отменена пользователем.[/red]", "err")
                    return
                elif user_decision.strip().lower() not in ("y", "yes", "да", "ok", "ок"):
                    user_task = self.prompts.plan_revise(user_decision)
                else:
                    user_task = self.prompts.plan_approved()
            else:
                user_task = self.prompts.plan_approved()
            code_prompt = user_task
        else:
            code_prompt = self.prompts.task(user_task)

        say("[bold green]🚀 Генерация кода и SEARCH/REPLACE патчей...[/bold green]")
        response = await self.bridge.send_prompt(
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
                say(f"[yellow]Модель запросила файлы, которых нет в проекте или они исключены: {', '.join(wanted)}[/yellow]", "warn")
                return response
            say(f"[cyan]📎 Модель запросила файлы: {', '.join(ok)}[/cyan]")
            emit("context", mode="extra", extra=ok)
            self.sent_files.update(ok)
            emit("phase", phase="sending")
            response = await self.bridge.send_prompt(
                prompt=self.prompts.need_files(self.packer.pack_files(ok)),
                system_instruction=self.prompts.system_patcher(True),
                new_chat=False,
            )
        return response

    def _report_transport(self):
        self._emit_attachments()
        t = self.bridge.last_transport
        if t not in ("-", "none"):
            say(f"[dim]📎 Контекст передан способом: {t}[/dim]")

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
            say(f"  -> {r.file_path}: {r.action} ({r.message})")

    async def _repair_failed_blocks(self, results, rounds: int = 2):
        """Если SEARCH-блоки не совпали — отправляем модели реальный файл и просим переделать только их."""
        for attempt in range(1, rounds + 1):
            bad = [r for r in results if r.failed_blocks]
            if not bad:
                return
            say(f"[yellow]🩹 Не совпали SEARCH-блоки в {len(bad)} файл(ах) — прошу модель переписать (попытка {attempt}/{rounds})...[/yellow]", "warn")
            emit("phase", phase="healing")
            parts = []
            for r in bad:
                fp = self.root / r.file_path
                actual = fp.read_text(encoding="utf-8", errors="replace") if fp.exists() else ""
                blocks = "\n---\n".join(r.failed_blocks)
                parts.append(f"ФАЙЛ {r.file_path} (текущее содержимое):\n```\n{actual}\n```\nНЕ СОВПАВШИЕ SEARCH-блоки:\n```\n{blocks}\n```")
            resp = await self.bridge.send_prompt(
                prompt=self.prompts.repair("\n\n".join(parts)),
                system_instruction=self.prompts.system_patcher(self.scope_partial),
                new_chat=False,
            )
            show_answer(resp, f"🩹 Исправленные патчи #{attempt}", "yellow", kind="repair")
            results, _ = self.patcher.parse_and_apply(resp)
            self._track(results)
            self._report_results(results)

    async def _apply_and_auto_heal(self, model_response: str):
        show_answer(model_response, f"🤖 Ответ {self.title}", "green")
        emit("phase", phase="applying")

        results, suggested_cmds = self.patcher.parse_and_apply(model_response)
        self._track(results)

        if results:
            self._report_results(results)
            if not IDE:
                res_table = Table(title="Примененные изменения файлов", show_lines=True)
                res_table.add_column("Файл", style="cyan")
                res_table.add_column("Действие", style="bold")
                res_table.add_column("Статус")
                for r in results:
                    color = "green" if r.action != "FAILED" else "bold red"
                    res_table.add_row(r.file_path, f"[{color}]{r.action}[/{color}]", r.message)
                console.print(res_table)
        else:
            say("[dim]В ответе не обнаружено блоков модификации файлов.[/dim]")

        await self._repair_failed_blocks(results)

        for cmd in suggested_cmds:
            run_it = self.yolo_mode or self.ask_confirm(f"Выполнить предложенную команду `[bold yellow]{cmd}[/bold yellow]`?", default=True)
            if run_it:
                say(f"[cyan]$ {cmd}[/cyan]")
                emit("cmd", command=cmd, status="run")
                exec_res = self.runner.run_cmd(cmd)
                if exec_res.succeeded:
                    emit("cmd", command=cmd, status="ok", code=0)
                    say("[green]✓ Команда выполнена успешно.[/green]", "ok")
                else:
                    emit("cmd", command=cmd, status="fail", code=exec_res.returncode, output=exec_res.combined_output(2000))
                    say(f"[red]✗ Команда завершилась с ошибкой (код {exec_res.returncode}):[/red]\n{exec_res.stderr}", "err")
            else:
                emit("cmd", command=cmd, status="skipped")

        if self.config.verify_cmd and results:
            await self.run_auto_healing_loop(self.config.verify_cmd)

    async def run_auto_healing_loop(self, verify_cmd: str):
        total = self.config.max_heal_retries
        for attempt in range(1, total + 1):
            emit("phase", phase="verifying")
            say(f"\n[bold cyan]🔍 Проверка сборки/тестов (Попытка {attempt}/{total}): `{verify_cmd}`[/bold cyan]")
            exec_res = self.runner.run_cmd(verify_cmd)

            if exec_res.succeeded:
                emit("verify", command=verify_cmd, attempt=attempt, total=total, ok=True)
                say(f"[bold green]✅ Сборка и тесты (`{verify_cmd}`) прошли без единой ошибки![/bold green]", "ok")
                return

            emit("verify", command=verify_cmd, attempt=attempt, total=total, ok=False, output=exec_res.combined_output(max_chars=3000))
            if not IDE:
                console.print(
                    Panel(
                        exec_res.combined_output(max_chars=3000),
                        title=f"[bold red]❌ Ошибка верификации (Exit code {exec_res.returncode}) — Запускаю Auto-Heal[/bold red]",
                        border_style="red",
                    )
                )

            say("[yellow]🛠 Отправляю лог ошибки обратно в модель для автоматического исправления...[/yellow]", "warn")
            emit("phase", phase="healing")
            fix_response = await self.bridge.send_prompt(
                prompt=self.prompts.heal(verify_cmd, exec_res.combined_output()),
                system_instruction=self.prompts.system_patcher(self.scope_partial),
                new_chat=False,
            )

            show_answer(fix_response, f"🤖 Патч авто-исправления #{attempt}", "yellow", kind="heal")
            results, _ = self.patcher.parse_and_apply(fix_response)
            self._track(results)
            self._report_results(results)
            await self._repair_failed_blocks(results)

        say("[bold red]⚠️ Достигнут лимит попыток авто-исправления. Проверьте вывод выше или используйте /undo.[/bold red]", "err")

    async def continue_stopped(self):
        """Продолжает ответ, остановленный пользователем (тот же чат)."""
        if not self.session_initialized:
            say("[red]Нечего продолжать: в этом чате ещё не было запроса.[/red]", "err")
            return
        clear_stop()
        resp = await self.bridge.send_prompt(
            prompt=self.prompts.continue_after_stop(),
            system_instruction=self.prompts.system_patcher(self.scope_partial),
            new_chat=False,
        )
        await self._apply_and_auto_heal(await self._fulfil_need_files(resp))

    def on_stopped(self, partial: str):
        self.last_partial = partial or ""
        if partial:
            self.session_initialized = True  # сообщение с контекстом уже ушло в чат
            show_answer(partial, "⏹ Ответ остановлен", "yellow", kind="partial")
        emit("stopped")
        say("[yellow]⏹ Остановлено. Патчи не применялись. /continue — продолжить ответ.[/yellow]", "warn")

    async def check_ui_and_heal(self, url: str):
        console.print(f"[cyan]🌐 Запуск Playwright-субагента для проверки интерфейса: {url}[/cyan]")
        screenshot_path, errors, title = await self.verifier.inspect_url(url)
        if errors:
            err_text = "\n".join(errors)
            if IDE:
                emit("verify", command=f"check_ui {url}", attempt=1, total=1, ok=False, output=err_text)
            else:
                console.print(Panel(err_text, title="🚨 Обнаружены ошибки в консоли браузера", border_style="red"))
            if self.ask_confirm("Отправить ошибки браузера и скриншот в модель для авто-починки?", default=True):
                prompt = (
                    f"При открытии {url} (Title: {title}) в браузере обнаружены следующие ошибки консоли:\n"
                    f"```\n{err_text}\n```\n"
                    f"Исправь код проекта с помощью блоков SEARCH/REPLACE."
                )
                resp = await self.bridge.send_prompt(
                    prompt=prompt,
                    system_instruction=self.prompts.system_patcher(self.scope_partial),
                    attachment_path=screenshot_path,
                )
                await self._apply_and_auto_heal(resp)
        else:
            console.print(f"[bold green]✅ Страница '{title}' открылась чисто, ошибок в консоли браузера нет![/bold green]")
            if screenshot_path:
                console.print(f"[dim]Скриншот сохранен в: {screenshot_path.name}[/dim]")

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
            desc = e["full"][len(e["name"]):].lstrip(" |")
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
                    console.print("[red]Не удалось получить список моделей (переключатель не найден на странице).[/red]")
                    return
                models = [e for e in entries if e.get("kind", "model") == "model"]
                self.model_names = [e["name"] for e in models]
                table = Table(title=f"Модели {self.title} (из интерфейса)", show_lines=False)
                table.add_column("#", style="cyan")
                table.add_column("Название", style="bold")
                table.add_column("Описание", style="dim")
                table.add_column("", style="green")
                for i, e in enumerate(models, 1):
                    desc = e["full"][len(e["name"]):].lstrip(" |")
                    chosen = self.config.model and self.bridge._norm(self.config.model) == self.bridge._norm(e["name"])
                    table.add_row(str(i), e["name"], desc, "◀ выбрана" if chosen else ("✓" if e["checked"] else ""))
                console.print(table)
                locked = [e["name"] for e in entries if e.get("kind") == "locked"]
                if locked:
                    console.print(f"[dim]Недоступны в вашем плане: {', '.join(locked)}[/dim]")
                if current:
                    console.print(f"[dim]Сейчас в интерфейсе: {current}[/dim]")
                if levels:
                    console.print(f"Уровни рассуждений: [bold]{', '.join(levels)}[/bold]  [dim](текущий: {self.config.reasoning or 'по умолчанию'})[/dim]")
                console.print("[dim]Примеры: `/model 2`, `/model 3.1 pro high`, `/model 4 argon medium`; сброс: `/model default`[/dim]")
                return
            if arg.lower() in ("default", "auto", "reset"):
                self.config.model = ""
                self.config.reasoning = ""
                self.config.save_project_config()
                console.print("[green]✓ Выбор модели и рассуждений сброшен.[/green]")
                return
            wanted, level = parse_model_args(arg)
            ok, info, lvl_res = await self.bridge.choose_model(wanted, level)
            if not ok:
                console.print(f"[red]{info}[/red]")
                return
            self.config.model = info  # храним название, а не номер: номера в меню меняются
            msg = f"[green]✓ Модель: {info}"
            if level:
                if lvl_res and lvl_res[0]:
                    self.config.reasoning = level
                    msg += f" · рассуждения: {lvl_res[1]}"
                else:
                    msg += f"[/green]\n[yellow]⚠ Уровень '{level}' не установлен: {lvl_res[1] if lvl_res else '—'}[/yellow][green]"
            self.config.save_project_config()
            self._new_session()
            console.print(msg + ". Следующий запрос откроет новый чат с контекстом проекта.[/green]")
        except Exception as e:
            console.print(f"[bold red]Ошибка /model:[/bold red] {e}")

    async def handle_reasoning_command(self, arg: str):
        try:
            if not arg:
                cur = self.config.reasoning or "по умолчанию"
                console.print(
                    f"Рассуждения ({self.title}): [bold]{cur}[/bold]\n"
                    "Уровни: `/reasoning low|medium|high|off` — подбираются по пунктам меню модели "
                    "(Fast/Thinking/Pro и т.п.; у Claude — переключатель Extended thinking). "
                    "Точное название пункта тоже подходит: `/reasoning extended`. Сброс: `/reasoning default`.\n"
                    "[dim]Посмотреть доступные пункты: `/model`.[/dim]"
                )
                return
            if arg.lower() in ("default", "reset"):
                self.config.reasoning = ""
                self.config.save_project_config()
                console.print("[green]✓ Уровень рассуждений сброшен.[/green]")
                return
            ok, info = await self.bridge.choose_reasoning(arg)
            if ok:
                self.config.reasoning = arg
                self.config.save_project_config()
                self._new_session()
                console.print(f"[green]✓ Рассуждения: {arg} → пункт «{info}». Применится в новом чате.[/green]")
            else:
                console.print(f"[red]{info}[/red]")
        except Exception as e:
            console.print(f"[bold red]Ошибка /reasoning:[/bold red] {e}")

    def _new_session(self):
        self.bridge.reset_conversation()
        self.session_initialized = False
        self.dirty_files.clear()
        self.sent_files.clear()
        self.scope_partial = False

    def handle_provider_command(self, arg: str):
        arg = arg.lower()
        if arg not in PROVIDERS:
            lines = [f"Сейчас: [bold]{self.title}[/bold]. Использование: `/provider gemini`, `/provider claude` или `/provider aistudio`"]
            for k, pv in PROVIDERS.items():
                lines.append(f"  {k}: {pv.url}  (Chrome: {self.config.cdp_urls[k]})")
            console.print("\n".join(lines))
            return
        self.config.provider = arg
        self.config.save_project_config()
        self._new_session()
        emit("setting", key="provider", value=arg)
        pv = PROVIDERS[arg]
        console.print(
            f"[green]✓ Провайдер: {pv.title}[/green] (модель: {self.config.model or 'по умолчанию'}, "
            f"рассуждения: {self.config.reasoning or 'по умолчанию'}).\n"
            f"[dim]Нужен запущенный Chrome с отладкой на {self.config.cdp_url} и выполненный вход на {pv.url} "
            f"(scripts/start_chrome_{arg}_*).[/dim]"
        )

    def init_project_files(self):
        self.config.save_project_config()
        if not self.config.vibe_rules_file.exists():
            default_rules = (
                "# Правила и конвенции проекта (VIBE.md)\n\n"
                "- Пиши чистый, модульный и самодокументируемый код.\n"
                "- Сохраняй существующий стиль именования и структуру папок.\n"
                "- Не удаляй существующую бизнес-логику без явного запроса.\n"
            )
            self.config.vibe_rules_file.write_text(default_rules, encoding="utf-8")
        console.print("[green]✓ Созданы файлы конфигурации `.vibe.json` и `VIBE.md`.[/green]")

    async def read_input(self) -> str:
        if IDE:
            emit("phase", phase="idle")
            line = sys.stdin.readline()
            if line == "":
                raise EOFError
            return line.rstrip("\r\n").replace(" ⏎ ", "\n").strip()
        if self.session is not None:
            from prompt_toolkit.formatted_text import HTML

            return (await self.session.prompt_async(HTML("\n<ansibrightmagenta><b>vibe&gt;</b></ansibrightmagenta> "))).strip()
        return Prompt.ask("\n[bold bright_magenta]vibe>[/bold bright_magenta]").strip()

    async def run_command(self, name: str, arg: str) -> bool:
        """Выполняет команду. Возвращает False, если нужно выйти."""
        if name == "exit":
            return False
        if name == "context":
            self.show_context_stats()
        elif name == "undo":
            ok, msg = self.patcher.undo_last_snapshot()
            console.print(f"[{'green' if ok else 'red'}]{msg}[/{'green' if ok else 'red'}]")
        elif name == "init":
            self.init_project_files()
        elif name == "reset":
            self._new_session()
            console.print("[green]✓ Сессия чата сброшена. Следующий запрос создаст новый диалог с актуальным контекстом.[/green]")
        elif name == "help":
            console.print(HELP_TEXT)
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
                console.print(f"[green]✓ Способ передачи контекста: {arg}[/green]")
            else:
                console.print(f"Сейчас: [bold]{self.config.transport}[/bold]. Варианты:\n" + "\n".join(f"  [cyan]{k}[/cyan] — {TRANSPORT_INFO[k][1]}" for k in VALID_TRANSPORTS))
        elif name == "attach":
            if not arg:
                say("Использование: /attach <путь к zip или изображению>")
            else:
                self.add_attachment(arg)
        elif name == "attach_clear":
            self.attachments.clear()
            self._emit_attachments()
            say("[green]✓ Вложения убраны[/green]", "ok")
        elif name == "yolo":
            a = arg.lower()
            if a in ("on", "off", "вкл", "выкл", "1", "0"):
                self.yolo_mode = a in ("on", "вкл", "1")
                emit("setting", key="yolo", value=self.yolo_mode)
                say(f"[green]✓ Без подтверждений: {'включено' if self.yolo_mode else 'выключено'}[/green]", "ok")
            else:
                say(f"Без подтверждений: [bold]{'вкл' if self.yolo_mode else 'выкл'}[/bold]. /yolo on|off")
        elif name == "verify_cmd":
            self.config.verify_cmd = arg
            self.config.save_project_config()
            console.print(f"[green]✓ Команда авто-проверки установлена: `{arg}`[/green]")
        elif name == "fix":
            cmd = arg or self.config.verify_cmd
            if not cmd:
                console.print("[red]Укажите команду для проверки, например: `/fix npm run build` или `/fix pytest`[/red]")
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
                say(f"[green]✓ Автоподбор контекста: {'включён' if self.config.auto_context else 'выключен'}. Применится в новом чате.[/green]", "ok")
            else:
                say(f"Автоподбор контекста: [bold]{'вкл' if self.config.auto_context else 'выкл'}[/bold] "
                    f"(до {self.config.auto_context_max_files} файлов, ~{self.config.auto_context_budget:,} токенов). `/autocontext on|off`")
        elif name == "promptstyle":
            a = arg.lower()
            if a in VALID_STYLES:
                self.config.prompt_style = a
                self.prompts.set_style(a)
                self.config.save_project_config()
                emit("setting", key="prompt_style", value=a)
                say(f"[green]✓ Стиль промпта: {STYLE_TITLES[a]}[/green]", "ok")
            else:
                say("Стили: " + ", ".join(VALID_STYLES) + f". Сейчас: [bold]{self.config.prompt_style}[/bold]")
        elif name == "autocontext_set":
            try:
                mf, _, bud = arg.partition(" ")
                self.config.auto_context_max_files = max(1, int(mf))
                if bud:
                    self.config.auto_context_budget = max(2000, int(bud))
                self.config.save_project_config()
                emit("setting", key="auto_context_limits", value=[self.config.auto_context_max_files, self.config.auto_context_budget])
            except ValueError:
                say("[red]Формат: /autocontext_set <макс. файлов> [токенов][/red]", "err")
        elif name == "continue":
            await self.continue_stopped()
        elif name == "list_models":
            await self.emit_models()
        elif name == "plan":
            if not arg:
                console.print("[red]Укажите задачу: `/plan <что сделать>`[/red]")
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
                console.print("\n[dim]Выход из Vibe CLI.[/dim]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            kind, name, arg, hints = resolve(user_input)

            # команды никогда не уходят в модель как задача
            if kind == "ambiguous":
                console.print(f"[yellow]Команда неоднозначна: {', '.join('/' + h for h in hints)}[/yellow]")
                continue
            if kind == "unknown":
                tip = f" Возможно: {', '.join('/' + h for h in hints)}." if hints else ""
                console.print(f"[red]Неизвестная команда.[/red]{tip} Список: /help")
                continue

            try:
                if kind == "command":
                    if not await self.run_command(name, arg):
                        break
                else:
                    await self.execute_vibe_task(arg, two_phase_plan=False)
            except GenerationStopped as e:
                self.on_stopped(e.partial)
            except Exception as e:
                emit("error", text=str(e))
                say(f"[bold red]Ошибка выполнения:[/bold red] {e}", "err")


def main():
    parser = argparse.ArgumentParser(description="Vibe CLI — локальный вайбкодер на вашей подписке (Gemini / Claude / AI Studio)")
    parser.add_argument("prompt", nargs="*", help="Одноразовая задача (если не указана — запускается интерактивный режим)")
    parser.add_argument("--dir", "-d", default=".", help="Путь к папке проекта (по умолчанию текущая)")
    parser.add_argument("--plan", "-p", action="store_true", help="Запустить в двухфазном режиме (Сначала План -> Затем Код)")
    parser.add_argument("--yolo", "-y", action="store_true", help="Автоматически подтверждать все планы и команды без вопросов")
    parser.add_argument("--provider", choices=list(PROVIDERS), help="ИИ-провайдер: gemini, claude или aistudio")
    parser.add_argument("--reasoning", help="Уровень рассуждений: low|medium|high|off или название пункта")
    parser.add_argument("--model", help="Модель (номер или часть названия, например: pro)")
    parser.add_argument("--transport", choices=list(VALID_TRANSPORTS), help="Способ передачи файлов в чат")
    parser.add_argument("--auto-context", choices=["on", "off"], help="Автоподбор контекста по описанию задачи")
    parser.add_argument("--prompt-style", choices=list(VALID_STYLES), help="Стиль промпта, вставляемого в чат")
    parser.add_argument("--list-models-json", action="store_true", help="Вывести список моделей событием models и выйти (для IDE)")
    args = parser.parse_args()

    orchestrator = VibeOrchestrator(Path(args.dir), yolo_mode=args.yolo)
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
        try:
            asyncio.run(orchestrator.execute_vibe_task(task_text, two_phase_plan=args.plan))
        except GenerationStopped as e:
            orchestrator.on_stopped(e.partial)
    else:
        asyncio.run(orchestrator.interactive_loop())


if __name__ == "__main__":
    main()
