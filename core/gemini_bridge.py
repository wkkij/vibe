import asyncio
import base64
import mimetypes
import os
import random
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import osinput
from .config import VibeConfig
from .events import GenerationStopped, clear_stop, emit, stop_requested
from .humanize import HumanInput
from .i18n import t
from .prompts import PromptBook
from .providers import Provider, catalog_for, get_provider
from .screen_driver import ScreenSession

# Пункты меню выбора модели бывают не только моделями. Всё, что не модель, в список и в выбор не попадает.
PROMO_RE = re.compile(
    r"(подробнее|learn more|входит в план|включен\w* в план|included in|на ограниченное время|for a limited time|limited[- ]time|"
    r"попробуйте|try .{0,30}free|upgrade to|перейти на)", re.I)
LOCKED_RE = re.compile(
    r"(улучшить план|улучшите план|upgrade( your)?( plan)?\b|обновить(ся)? до|get (pro|max|plus|ultra)|"
    r"требуется (подписка|план)|requires (a )?(pro|max|plus|ultra)|только (для|в) (pro|max|plus|ultra))", re.I)
SUBMENU_RE = re.compile(r"^(другие модели|more models|other models|legacy models|прежние модели|старые модели)$", re.I)
OPTION_RE = re.compile(r"(уровень усили|effort|reasoning effort)", re.I)
ICON_RE = re.compile(r"[\ue000-\uf8ff\u200b-\u200f\u2060\ufeff]")  # символы иконок и невидимые знаки
MAX_MODEL_NAME = 60  # название модели длиннее — это рекламный текст, а не модель

SETTING_RE = re.compile(r"(thinking level|reasoning level|уровень (рассужд|мышлен)|extended thinking|расширенн\w+ (рассужд|мышлен))", re.I)
LEVEL_WORDS_UI = {
    "off": ["off", "none", "выкл"],
    "min": ["minimal", "min", "мин"],
    "minimal": ["minimal", "min", "мин"],
    "low": ["low", "низк"],
    "medium": ["medium", "mid", "средн", "standard"],
    "standard": ["standard", "medium", "средн"],
    "high": ["high", "высок"],
    "max": ["max", "extended", "высок"],
    "extended": ["extended", "max"],
}
UPLOAD_ITEM_RE = re.compile(r"(upload|загруз|from computer|с компьютера|files|файл)", re.I)

BLIND_RE = re.compile(
    r"(не передан|не вижу|не получил|не прикреп|не приложен|отсутству\w+ (файл|вложен)|"
    r"(no|not|didn'?t|did not|don'?t) (see|receive|have|find)[^.\n]{0,40}(file|attach|content|project)|"
    r"attachment (is )?(missing|empty)|без (содержимого|вложени))",
    re.I,
)

CHUNK = 600_000  # символов base64 за один evaluate


class BlindModelError(RuntimeError):
    """Модель ответила, что не видит файлы проекта."""


class WebChatBridge:
    def __init__(self, config: VibeConfig):
        self.config = config
        self.last_transport: str = "-"
        self.pending_files: List[Path] = []  # вложения пользователя (zip/изображения) для следующего сообщения
        self.prompts = PromptBook("classic")  # CLI подставляет свой PromptBook со стилем из настроек

    # ------------------------------------------------------------ human-like input (/human on|old|off)
    def _hum(self) -> Optional[HumanInput]:
        """HumanInput when the old (CDP+OS) human mode is on, else None."""
        if not (getattr(self.config, "human_input", False) and getattr(self.config, "human_mode", "on") == "old"):
            return None
        if getattr(self, "_human", None) is None:
            self._human = HumanInput()
        return self._human

    @property
    def _is_screen_human(self) -> bool:
        return bool(getattr(self.config, "human_input", False) and getattr(self.config, "human_mode", "on") != "old")

    async def _nap(self, seconds: float):
        """asyncio.sleep; in the old human mode with natural jitter."""
        await asyncio.sleep(seconds * random.uniform(0.85, 1.5) if self._hum() else seconds)

    async def _click(self, locator, **kw):
        hum = self._hum()
        if hum is not None and not kw:
            await hum.click(locator)
        else:
            await locator.click(**kw)

    @property
    def prov(self) -> Provider:
        return get_provider(self.config.provider, self.config.selector_overrides)

    def reset_conversation(self):
        """Состояния диалога в самом мосте нет: новый чат открывается в браузере при отправке (new_chat)."""
        return None

    # ------------------------------------------------------------------ public

    async def send_prompt(
        self,
        prompt: str,
        system_instruction: str = "",
        attachment_path: Optional[Path] = None,
        new_chat: bool = False,
        canary: Optional[str] = None,
    ) -> str:
        if new_chat:
            self.reset_conversation()

        full_message = f"{system_instruction}\n\n{prompt}".strip() if system_instruction else prompt

        if self._is_screen_human:
            return await self._send_via_screen(full_message, attachment_path, new_chat)

        has_file = bool(attachment_path and attachment_path.exists() and attachment_path.stat().st_size > 0)
        is_text = has_file and attachment_path.suffix.lower() in (".txt", ".md", ".json", ".log")
        chain = (self._transport_chain() if is_text else ["file", "paste"]) if has_file else ["none"]
        last_err: Optional[Exception] = None
        last_text = ""

        for i, transport in enumerate(chain):
            # каждая повторная попытка начинается в чистом чате, чтобы не плодить дубли вложений
            chat_is_new = new_chat or i > 0
            try:
                text = await self._send_via_cdp(full_message, attachment_path, chat_is_new, transport, canary)
                self.last_transport = transport
                self.pending_files.clear()
                return self._strip_canary(text, canary)
            except BlindModelError as e:
                last_err = e
                last_text = str(e)
                continue
        if has_file and not is_text:  # скриншот не прикрепился — отправляем хотя бы текст ошибок
            self.last_transport = "none"
            return self._strip_canary(await self._send_via_cdp(full_message, None, False, "none", None), canary)
        raise RuntimeError(
            t("{title} так и не увидел контекст проекта ни одним способом ({chain}). Последний ответ модели:\n{last}", title=self.prov.title, chain=", ".join(chain), last=last_text[:500])
        ) from last_err

    async def _send_via_screen(
        self,
        message: str,
        attachment_path: Optional[Path],
        new_chat: bool,
    ) -> str:
        if not osinput.available():
            raise RuntimeError(t("Режим Humanize доступен только в Windows."))
        has_file = bool(attachment_path and attachment_path.exists() and attachment_path.stat().st_size > 0)
        if has_file:
            if attachment_path.suffix.lower() in (".txt", ".md", ".json", ".log"):
                body = attachment_path.read_text(encoding="utf-8", errors="replace")
                message = f'<attached_file name=".vibe_context_bundle.txt">\n{body}\n</attached_file>\n\n{message}'
                self.last_transport = "inline"
            else:
                emit("log", level="warn", text=t("В режиме Humanize вложения-файлы ({name}) не отправляются — прикрепите их в браузере вручную.", name=attachment_path.name))
                self.last_transport = "none"
        else:
            self.last_transport = "none"

        if self.pending_files:
            names = ", ".join(p.name for p in self.pending_files)
            emit("log", level="warn", text=t("В режиме Humanize вложения-файлы ({name}) не отправляются — прикрепите их в браузере вручную.", name=names))
            self.pending_files.clear()

        session = ScreenSession(self.config)
        return await session.send_and_read(message, self.prov.key, self.prov.title, new_chat=new_chat)

    def _transport_chain(self) -> List[str]:
        mode = self.config.transport
        if mode == "auto":
            base = list(self.prov.auto_chain)
            extra = [x for x in ("zip", "base64") if x not in base]
            if base and base[-1] == "inline":  # текстом в сообщении — самый последний запасной вариант
                return base[:-1] + extra + ["inline"]
            return base + extra
        return [mode]

    def _materialize(self, bundle: Path, transport: str) -> Tuple[Path, str]:
        """Готовит файл для форматов zip / base64. -> (файл для вложения, пояснение для модели)."""
        if transport == "zip":
            import zipfile

            zp = bundle.with_suffix(".zip")
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(bundle, arcname=bundle.name)
            return zp, self.prompts.pack.BUNDLE_ZIP.format(zip=zp.name, bundle=bundle.name)
        raw = base64.b64encode(bundle.read_bytes()).decode("ascii")
        bp = bundle.with_name(bundle.stem + ".b64.txt")
        bp.write_text("\n".join(raw[i : i + 120] for i in range(0, len(raw), 120)), encoding="utf-8")
        return bp, self.prompts.pack.BUNDLE_B64.format(file=bp.name, bundle=bundle.name)

    @staticmethod
    def _strip_canary(text: str, canary: Optional[str]) -> str:
        if not canary:
            return text
        return re.sub(rf"^\s*CONTEXT_OK[: ]*{re.escape(canary)}\s*\n?", "", text).strip()

    # --------------------------------------------------------------- CDP core

    def _model_via_url(self) -> bool:
        """Провайдер выбирает модель параметром адреса (AI Studio: ?model=id) — меню на странице не нужно."""
        m = self.config.model or ""
        return bool(self.prov.model_param and m and re.fullmatch(r"[A-Za-z0-9._\-]+", m))

    def _chat_url(self) -> str:
        if self._model_via_url():
            sep = "&" if "?" in self.prov.url else "?"
            return f"{self.prov.url}{sep}{self.prov.model_param}={self.config.model}"
        return self.prov.url

    async def _open_page(self, p, new_chat: bool):
        try:
            browser = await p.chromium.connect_over_cdp(self.config.cdp_url)
        except Exception as e:
            raise RuntimeError(
                t("Не удалось подключиться к Chrome по адресу {cdp}.\nЗапустите скрипт scripts/start_chrome_{key}_* (.bat), войдите в аккаунт на {url} и повторите.\nДетали: {e}",
                  cdp=self.config.cdp_url, key=self.prov.key, url=self.prov.url, e=e)
            )
        if self._hum():
            self._hum().reset()
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = next((pg for pg in context.pages if self.prov.host in pg.url), None)
        if page is None:
            page = await context.new_page()
            await page.goto(self._chat_url(), wait_until="domcontentloaded")
            await self._nap(3)
        elif new_chat:
            await page.goto(self._chat_url(), wait_until="domcontentloaded")
            await self._nap(2.5)
        try:
            await page.wait_for_selector(self.prov.input, timeout=20000)
        except Exception:
            raise RuntimeError(
                t("Поле ввода на {host} не найдено. Войдите в аккаунт в открытом окне Chrome.", host=self.prov.host)
            )
        return page

    async def _send_via_cdp(
        self,
        message: str,
        attachment_path: Optional[Path],
        new_chat: bool,
        transport: str,
        canary: Optional[str],
    ) -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            page = await self._open_page(p, new_chat)

            wanted_model = "" if self._model_via_url() else self.config.model
            if wanted_model or self.config.reasoning:
                await self._ensure_model(page, wanted_model, self.config.reasoning, apply_reasoning=new_chat)

            if transport in ("file", "paste"):
                ok = await self._attach_file(page, attachment_path, transport)
                if not ok:
                    raise BlindModelError(t("Не удалось прикрепить файл способом '{mode}'.", mode=transport))
            elif transport in ("zip", "base64"):
                fpath, note = self._materialize(attachment_path, transport)
                if not (await self._attach_file(page, fpath, "file") or await self._attach_file(page, fpath, "paste")):
                    raise BlindModelError(t("Не удалось прикрепить файл способом '{mode}'.", mode=transport))
                message = f"{note}\n\n{message}"
            elif transport == "inline":
                body = attachment_path.read_text(encoding="utf-8", errors="replace")
                message = f"<attached_file name=\".vibe_context_bundle.txt\">\n{body}\n</attached_file>\n\n{message}"

            for extra in list(self.pending_files):
                if not (extra.exists() and (await self._attach_file(page, extra, "file") or await self._attach_file(page, extra, "paste"))):
                    emit("log", level="warn", text=t("Не удалось прикрепить {name} к чату — файл пропущен.", name=extra.name))
                else:
                    await self._nap(0.8)

            if canary and transport != "none":
                message += "\n\n" + self.prompts.canary(canary)

            if not await self._fill_editor(page, message):
                raise RuntimeError(t("Не удалось вставить текст в поле ввода {title}.", title=self.prov.title))

            before = await page.locator(self.prov.response).count()
            emit("phase", phase="sending")
            await self._click_send(page)
            text = await self._wait_response(page, before)

            if transport != "none" and canary and f"CONTEXT_OK" not in text and canary not in text:
                if BLIND_RE.search(text[:1500]):
                    raise BlindModelError(text)
            return text

    # ------------------------------------------------------------ attachments

    async def _attach_file(self, page, path: Path, method: str) -> bool:
        if method == "file":
            if (self.prov.file_input and await self._upload_via_input(page, path)) or await self._upload_via_chooser(page, path):
                return await self._wait_chip(page)
            return False
        if method == "paste":
            if await self._inject_file_base64(page, path, "paste") and await self._wait_chip(page, 8):
                return True
            if await self._inject_file_base64(page, path, "drop") and await self._wait_chip(page, 8):
                return True
        return False

    async def _wait_chip(self, page, timeout: float = 20) -> bool:
        """Возвращает True только если в интерфейсе реально появилась карточка вложения."""
        end = time.time() + timeout
        while time.time() < end:
            if await page.locator(self.prov.chip).count() > 0:
                await self._nap(1.5)
                return True
            await self._nap(0.5)
        return False

    async def _upload_via_input(self, page, path: Path) -> bool:
        try:
            inputs = page.locator('input[type="file"]')
            if await inputs.count() == 0:
                return False
            await inputs.first.set_input_files(str(path))
            return True
        except Exception:
            return False

    async def _upload_via_chooser(self, page, path: Path) -> bool:
        try:
            plus = page.locator(self.prov.plus).first
            if await page.locator(self.prov.plus).count() == 0:
                return False
            await self._click(plus)
            await self._nap(0.8)
            items = page.locator('[role="menuitem"], button, a')
            n = await items.count()
            for i in range(min(n, 60)):
                it = items.nth(i)
                try:
                    label = (await it.inner_text(timeout=300)).strip()
                except Exception:
                    continue
                if label and len(label) < 60 and UPLOAD_ITEM_RE.search(label):
                    try:
                        async with page.expect_file_chooser(timeout=5000) as fc:
                            await self._click(it)
                        chooser = await fc.value
                        await chooser.set_files(str(path))
                        return True
                    except Exception:
                        continue
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False

    async def _inject_file_base64(self, page, path: Path, how: str) -> bool:
        """Передаёт файл в страницу через base64 и собирает из него настоящий File (paste/drop)."""
        try:
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            await page.evaluate("() => { window.__vibeB64 = ''; }")
            for i in range(0, len(b64), CHUNK):
                await page.evaluate("(c) => { window.__vibeB64 += c; }", b64[i : i + CHUNK])
            return bool(
                await page.evaluate(
                    """([sel, name, how, mime]) => {
                        const bin = atob(window.__vibeB64); window.__vibeB64 = '';
                        const bytes = new Uint8Array(bin.length);
                        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                        const file = new File([bytes], name, {type: mime});
                        const dt = new DataTransfer(); dt.items.add(file);
                        const el = document.querySelector(sel);
                        if (!el) return false;
                        el.focus();
                        const target = how === 'drop' ? (el.closest('rich-textarea') || el) : el;
                        const ev = how === 'drop'
                            ? new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})
                            : new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
                        target.dispatchEvent(ev);
                        return true;
                    }""",
                    [self.prov.editor, path.name.lstrip(".") or "context.txt", how, mimetypes.guess_type(path.name)[0] or "text/plain"],
                )
            )
        except Exception:
            return False

    # ----------------------------------------------------------- input/output

    async def _editor_text_len(self, page) -> int:
        return await page.evaluate(
            "(sel) => { const e = document.querySelector(sel); if (!e) return -1; "
            "const v = (typeof e.value === 'string') ? e.value : (e.innerText || ''); return v.trim().length; }",
            self.prov.editor,
        )

    async def _fill_editor(self, page, text: str) -> bool:
        editor = page.locator(self.prov.input).first
        await self._click(editor)
        want = int(len(text.strip()) * 0.9)

        hum = self._hum()
        if hum is not None:
            try:
                if await self._editor_text_len(page) > 0:
                    await hum.clear(page)
                await hum.fill(page, text)
                await self._nap(0.6)
                if await self._editor_text_len(page) >= want:
                    return True
            except Exception:
                pass  # fall back to the quick methods below (they replace whatever was typed)

        # 1) быстрая вставка как из буфера обмена
        await page.evaluate(
            """([sel, text]) => {
                const el = document.querySelector(sel); if (!el) return;
                el.focus(); document.execCommand('selectAll', false, null);
                const dt = new DataTransfer(); dt.setData('text/plain', text);
                el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            [self.prov.editor, text],
        )
        await self._nap(0.8)
        if await self._editor_text_len(page) >= want:
            return True

        # 2) запасной путь: insertText кусками
        await page.evaluate(
            "(sel) => { const e = document.querySelector(sel); e.focus(); document.execCommand('selectAll'); document.execCommand('delete'); }",
            self.prov.editor,
        )
        for i in range(0, len(text), 20000):
            await page.evaluate(
                "([sel, t]) => { const e = document.querySelector(sel); e.focus(); document.execCommand('insertText', false, t); }",
                [self.prov.editor, text[i : i + 20000]],
            )
        await self._nap(0.8)
        if await self._editor_text_len(page) >= want:
            return True

        # 3) textarea-вариант
        try:
            await page.locator("textarea").first.fill(text)
            return True
        except Exception:
            return False

    async def _click_send(self, page):
        # кнопка активна не сразу: пока грузится вложение, она disabled
        end = time.time() + 90
        while time.time() < end:
            if stop_requested():
                clear_stop()
                raise GenerationStopped("")
            btn = page.locator(self.prov.send)
            if await btn.count() > 0:
                b = btn.first
                disabled = await b.get_attribute("aria-disabled")
                if disabled != "true" and await b.is_enabled():
                    hum = self._hum()
                    if hum is not None:
                        await hum.pause(0.6, 1.8)  # a person rereads the message before sending
                    await self._click(b)
                    return
            await self._nap(0.7)
        await page.locator(self.prov.input).first.press("Enter")

    async def _read_response(self, page) -> str:
        p = self.prov
        return await page.evaluate(
            """([rsel, inner, all, excl]) => {
                const r = document.querySelectorAll(rsel);
                if (!r.length) return '';
                const l = r[r.length - 1];
                if (all && inner) {
                    let nodes = [...l.querySelectorAll(inner)];
                    if (excl) nodes = nodes.filter(n => !n.closest(excl));
                    nodes = nodes.filter(n => !nodes.some(o => o !== n && o.contains(n)));
                    if (nodes.length) return nodes.map(n => n.innerText || '').join('\\n\\n');
                }
                const n = (inner && l.querySelector(inner)) || l;
                return n.innerText || '';
            }""",
            [p.response, p.response_inner, p.response_all, p.response_exclude],
        )

    async def _stop_and_collect(self, page) -> str:
        """Нажимает «Stop» на странице провайдера и возвращает то, что модель успела написать."""
        try:
            btn = page.locator(self.prov.stop)
            if await btn.count() > 0:
                await self._click(btn.first)
        except Exception:
            pass
        await self._nap(1.2)
        try:
            partial = (await self._read_response(page)).strip()
        except Exception:
            partial = ""
        clear_stop()
        return partial

    async def _wait_response(self, page, before_count: int) -> str:
        start = time.time()
        emit("phase", phase="waiting")
        while time.time() - start < 60:
            if stop_requested():
                raise GenerationStopped(await self._stop_and_collect(page))
            if await page.locator(self.prov.response).count() > before_count:
                break
            await self._nap(0.8)

        stable, last = 0, ""
        phase = ""
        last_emit = 0.0
        # лимит ожидания ответа: по умолчанию 5 минут, Vibe IDE ставит до 60+ минут
        limit = float(os.environ.get("VIBE_RESPONSE_TIMEOUT", "300") or 300)
        while time.time() - start < limit:
            await self._nap(1.2)
            if stop_requested():
                raise GenerationStopped(await self._stop_and_collect(page))
            hum = self._hum()
            if hum is not None and random.random() < 0.12:
                await hum.drift(page)
            cur = await self._read_response(page)
            stopping = await page.locator(self.prov.stop).count() > 0

            # состояние модели для IDE: думает → отвечает
            new_phase = "answering" if cur.strip() else "thinking"
            if not stopping and cur.strip():
                new_phase = "finishing"
            if new_phase != phase:
                phase = new_phase
                if phase != "finishing":
                    emit("phase", phase=phase)
            now = time.time()
            if cur != last and cur.strip() and now - last_emit >= 1.0:
                last_emit = now
                emit("progress", chars=len(cur), elapsed=int(now - start), text=cur if len(cur) < 150_000 else cur[-150_000:])

            if cur and cur == last and not stopping:
                stable += 1
                if stable >= 3:
                    return cur.strip()
            else:
                stable, last = 0, cur
        if last:
            return last.strip()
        raise TimeoutError(t("Превышено время ожидания ответа от {title}.", title=self.prov.title))

    # ------------------------------------------------------------------ models

    @staticmethod
    def _norm(t: str) -> str:
        return re.sub(r"[^0-9a-zа-я.]+", "", t.lower())

    async def _find_model_btn(self, page):
        """Кнопка выбора модели: сначала селекторы профиля, затем эвристика по шапке страницы."""
        for sel in self.prov.model_btn:
            loc = page.locator(sel)
            if await loc.count() > 0:
                return loc.first
        found = await page.evaluate(
            """() => {
                const cands = [...document.querySelectorAll('button[aria-haspopup], [role="button"][aria-haspopup]')]
                    .filter(b => b.getBoundingClientRect().top < 110 && (b.innerText || '').trim().length > 0);
                const el = cands[0];
                if (!el) return false;
                el.setAttribute('data-vibe-model-btn', '1');
                return true;
            }"""
        )
        return page.locator('[data-vibe-model-btn="1"]').first if found else None

    async def _visible_count(self, page) -> int:
        items = page.locator(self.prov.model_item)
        n = 0
        for i in range(min(await items.count(), 80)):
            try:
                if await items.nth(i).is_visible():
                    n += 1
            except Exception:
                pass
        return n

    async def _close_menu(self, page):
        """Гарантированно закрывает меню (Escape в Gemini иногда его не закрывает)."""
        for _ in range(3):
            if await self._visible_count(page) == 0:
                return
            await page.keyboard.press("Escape")
            await self._nap(0.4)
        if await self._visible_count(page) > 0:
            backdrop = page.locator(".cdk-overlay-backdrop, .mat-mdc-menu-backdrop")
            try:
                if await backdrop.count() > 0:
                    await backdrop.first.click(force=True, timeout=1500)
                else:
                    await page.mouse.click(3, 3)
            except Exception:
                pass
        await self._nap(0.4)

    async def _open_model_menu(self, page) -> bool:
        # меню уже открыто (например, осталось от прошлой команды) — повторный клик его бы закрыл
        if await self._visible_count(page) > 0:
            return True
        btn = await self._find_model_btn(page)
        if btn is None:
            return False
        for _ in range(2):
            await self._click(btn)
            await self._nap(1.0)
            if await self._visible_count(page) > 0:
                return True
        return False

    @staticmethod
    def _is_setting(name: str) -> bool:
        return bool(SETTING_RE.search(name))

    @staticmethod
    def _classify_entry(name: str, full: str, disabled: bool = False) -> str:
        """kind пункта меню: model | setting | option | submenu | promo | locked.

        Выбираются и показываются только model. promo — реклама/баннер («входит в план…», «Подробнее»),
        locked — модель недоступна в вашем плане (нужно улучшить план), setting/option — настройки меню,
        submenu — раскрывающийся список («Другие модели»).
        """
        if PROMO_RE.search(name) or len(name) > MAX_MODEL_NAME:
            return "promo"
        if SETTING_RE.search(name):
            return "setting"
        if OPTION_RE.search(name):
            return "option"
        if SUBMENU_RE.match(name.strip()):
            return "submenu"
        if disabled or LOCKED_RE.search(full):
            return "locked"
        return "model"

    async def _menu_entries(self, page) -> List[dict]:
        """Видимые пункты меню. kind: model — выбор модели, setting — настройка/подменю (Thinking level)."""
        items = page.locator(self.prov.model_item)
        out, seen = [], set()
        for i in range(min(await items.count(), 80)):
            it = items.nth(i)
            try:
                if not await it.is_visible():
                    continue
                raw = ICON_RE.sub("", await it.inner_text(timeout=500))
                full = " | ".join(x.strip() for x in raw.splitlines() if x.strip())
                disabled = (
                    (await it.get_attribute("aria-disabled")) == "true"
                    or (await it.get_attribute("data-disabled")) is not None
                    or (await it.get_attribute("disabled")) is not None
                )
                checked = (
                    (await it.get_attribute("aria-checked")) == "true"
                    or (await it.get_attribute("aria-selected")) == "true"
                    or (await it.get_attribute("data-state")) == "checked"
                )
            except Exception:
                continue
            if not full or full in seen:
                continue
            seen.add(full)
            name = full.split(" | ")[0]
            kind = self._classify_entry(name, full, disabled)
            out.append({"idx": i, "name": name, "full": full, "checked": checked and kind == "model", "kind": kind, "locked": kind == "locked"})
        return out

    async def _current_model_label(self, page) -> str:
        btn = await self._find_model_btn(page)
        if btn is None:
            return ""
        try:
            label = " ".join(ICON_RE.sub("", await btn.inner_text(timeout=800)).split())
        except Exception:
            return ""
        # на кнопке иногда оказывается рекламный текст вместо названия модели — такой подпись не считаем
        return "" if (PROMO_RE.search(label) or len(label) > MAX_MODEL_NAME) else label

    def _match(self, entries: List[dict], wanted: str) -> Optional[dict]:
        models = [e for e in entries if e.get("kind", "model") == "model"]
        if wanted.isdigit():  # чистое число — только номер в списке, без поиска по подстроке
            return models[int(wanted) - 1] if 1 <= int(wanted) <= len(models) else None
        w = self._norm(wanted)
        for e in models:  # точное название важнее вхождения ("pro" -> "Pro", а не "3.1 Pro")
            if self._norm(e["name"]) == w:
                return e
        for e in models:
            if w and w in self._norm(e["full"]):
                return e
        return None

    async def _ensure_model(self, page, wanted: str, reasoning: str = "", apply_reasoning: bool = False):
        current = self._norm(await self._current_model_label(page))
        if wanted and not (current and self._norm(wanted) in current):
            await self._select_model(page, wanted)
        if reasoning and apply_reasoning:
            await self._select_reasoning(page, reasoning)

    _AI_ID_RE = re.compile(r"\b(?:gemini|gemma|imagen|veo|learnlm)[a-z0-9.\-]*", re.I)

    async def _aistudio_levels(self, page) -> Tuple[List[str], object]:
        """Читает варианты «Thinking level» из панели настроек AI Studio. -> (названия, элемент-переключатель или None)."""
        found = await page.evaluate(
            """() => {
                document.querySelectorAll('[data-vibe-think]').forEach(e => e.removeAttribute('data-vibe-think'));
                const cands = [...document.querySelectorAll('mat-select, [role="combobox"], select')];
                for (const c of cands) {
                    let box = c.closest('.settings-item, ms-thinking-level, div') || c;
                    for (let i = 0; i < 3 && box && !/thinking|рассужд/i.test(box.innerText || ''); i++) box = box.parentElement;
                    if (box && /thinking|рассужд/i.test((box.innerText || '').slice(0, 200))) { c.setAttribute('data-vibe-think', '1'); return true; }
                }
                return false;
            }"""
        )
        if not found:
            return [], None
        ctl = page.locator('[data-vibe-think="1"]').first
        try:
            await self._click(ctl)
            await self._nap(0.8)
            opts = page.locator('mat-option, [role="option"]')
            names = []
            for i in range(min(await opts.count(), 12)):
                try:
                    if await opts.nth(i).is_visible():
                        label = " ".join((await opts.nth(i).inner_text(timeout=400)).split())
                        if label:
                            names.append(label)
                except Exception:
                    continue
            return names, ctl
        except Exception:
            return [], None

    async def _select_model(self, page, wanted: str) -> Tuple[bool, str]:
        if not await self._open_model_menu(page):
            return False, t("Переключатель моделей на странице {title} не найден (см. selector_overrides).", title=self.prov.title)
        entries = await self._menu_entries(page)
        hit = self._match(entries, wanted)
        if hit is None:
            await self._close_menu(page)
            w = self._norm(wanted)
            locked = next((e for e in entries if e["kind"] == "locked" and w and w in self._norm(e["name"])), None)
            if locked:
                return False, t("Модель '{name}' недоступна в вашем плане (нужно улучшить подписку).", name=locked["name"])
            names = "; ".join(e["name"] for e in entries if e["kind"] == "model")
            return False, t("Модель '{wanted}' не найдена. Доступно: {names}", wanted=wanted, names=names)
        await self._click(page.locator(self.prov.model_item).nth(hit["idx"]))
        await self._nap(1.0)
        await self._close_menu(page)
        if self.prov.model_param:  # AI Studio: в конфиг кладём ID модели, найденный в интерфейсе
            m = self._AI_ID_RE.search(hit["full"])
            if m:
                return True, m.group(0).lower()
        return True, hit["name"]

    # --- уровни рассуждений -------------------------------------------------

    async def _open_thinking_submenu(self, page) -> Tuple[bool, List[dict], str]:
        """Открывает подменю «Thinking level». -> (ok, пункты подменю, сообщение об ошибке)."""
        if not await self._open_model_menu(page):
            return False, [], t("Меню модели не найдено.")
        entries = await self._menu_entries(page)
        setting = next((e for e in entries if e["kind"] == "setting"), None)
        if setting is None:
            return False, entries, t("В меню нет пункта «Thinking level».")
        before = {e["full"] for e in entries}
        await self._click(page.locator(self.prov.model_item).nth(setting["idx"]))
        await self._nap(1.0)
        after = await self._menu_entries(page)
        new = [e for e in after if e["full"] not in before]
        return True, (new or after), ""

    async def _select_reasoning(self, page, wanted: str) -> Tuple[bool, str]:
        """Ставит уровень рассуждений: через подменю «Thinking level», иначе по ключевым словам / переключателю."""
        lvl = wanted.lower()
        words = LEVEL_WORDS_UI.get(lvl, [])

        if self.prov.key == "aistudio":
            names, ctl = await self._aistudio_levels(page)
            if not names:
                return False, t("В интерфейсе AI Studio не найден переключатель «Thinking level» (у этой модели его может не быть).")
            hit = next((n for n in names if self._norm(wanted) == self._norm(n)), None) or next(
                (n for n in names if any(w in n.lower() for w in words) or self._norm(wanted) in self._norm(n)), None)
            if hit is None:
                await page.keyboard.press("Escape")
                return False, t("Уровень '{wanted}' не найден в интерфейсе. Доступно: ", wanted=wanted) + "; ".join(names)
            await self._click(page.locator("mat-option, [role=option]").filter(has_text=hit).first)
            await self._nap(0.6)
            return True, hit

        if self.prov.key == "gemini":
            ok, sub, err = await self._open_thinking_submenu(page)
            if ok and sub:
                hit = None
                for e in sub:
                    if any(w in e["full"].lower() for w in words) or self._norm(wanted) == self._norm(e["name"]):
                        hit = e
                        break
                if hit is None:
                    hit = next((e for e in sub if self._norm(wanted) in self._norm(e["full"])), None)
                if hit is not None:
                    await self._click(page.locator(self.prov.model_item).nth(hit["idx"]))
                    await self._nap(0.8)
                    await self._close_menu(page)
                    return True, hit["name"]
                names = "; ".join(e["name"] for e in sub)
                await self._close_menu(page)
                return False, t("Уровень '{wanted}' не найден в подменю. Доступно: {names}", wanted=wanted, names=names)
            await self._close_menu(page)

        # запасной путь / Claude: ищем пункт или переключатель по ключевым словам
        if not await self._open_model_menu(page):
            return False, t("Меню модели не найдено.")
        entries = await self._menu_entries(page)
        kw = self._reasoning_words(lvl) or words
        hit = None
        if kw:
            hit = next((e for e in entries if any(w in e["full"].lower() for w in kw)), None)
        if hit is None:
            hit = self._match(entries, wanted)
        if hit is None:
            await self._close_menu(page)
            return False, t("Пункт рассуждений '{wanted}' не найден. Доступно: ", wanted=wanted) + "; ".join(e["name"] for e in entries)

        toggle_like = self.prov.key == "claude"
        want_on = lvl != "off"
        if toggle_like and hit["checked"] == want_on:
            await self._close_menu(page)
        else:
            await self._click(page.locator(self.prov.model_item).nth(hit["idx"]))
            await self._nap(0.8)
            await self._close_menu(page)
        return True, hit["name"] + (t(" (вкл)") if toggle_like and want_on else t(" (выкл)") if toggle_like else "")

    def _reasoning_words(self, wanted: str) -> List[str]:
        return self.prov.reasoning_keywords.get(wanted.lower(), [])

    async def list_models(self) -> Tuple[List[dict], str, List[str]]:
        """-> (пункты меню, текущая модель в интерфейсе, доступные уровни рассуждений)."""
        if self.prov.static_models:
            cur = self.config.model
            return [
                {"name": m["id"], "full": f'{m["id"]} | {m["name"]} — {m["desc"]}', "checked": m["id"] == cur, "kind": "model", "idx": i}
                for i, m in enumerate(catalog_for(self.prov.key))
            ], cur, []
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            page = await self._open_page(p, new_chat=False)
            await self._close_menu(page)
            current = await self._current_model_label(page)
            if not await self._open_model_menu(page):
                return [], current, []
            entries = await self._menu_entries(page)
            levels: List[str] = []
            if any(e["kind"] == "setting" for e in entries):
                try:
                    ok, sub, _ = await self._open_thinking_submenu(page)
                    if ok:
                        levels = [e["name"] for e in sub]
                except Exception:
                    pass
            await self._close_menu(page)
            if not current:
                current = next((e["name"] for e in entries if e["kind"] == "model" and e["checked"]), "")
            if self.prov.key == "aistudio":
                try:
                    levels, _ = await self._aistudio_levels(page)
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
            return entries, current, levels

    async def choose_model(self, wanted: str, level: str = "") -> Tuple[bool, str, Optional[Tuple[bool, str]]]:
        """-> (модель выбрана, имя/ошибка, результат установки уровня или None)."""
        if self.prov.static_models:
            return True, wanted.strip(), None
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            page = await self._open_page(p, new_chat=False)
            await self._close_menu(page)
            ok, info = await self._select_model(page, wanted)
            if not ok:
                return False, info, None
            lvl_res = await self._select_reasoning(page, level) if level else None
            return True, info, lvl_res

    async def choose_reasoning(self, wanted: str) -> Tuple[bool, str]:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            page = await self._open_page(p, new_chat=False)
            await self._close_menu(page)
            return await self._select_reasoning(page, wanted)


GeminiSubscriptionBridge = WebChatBridge  # обратная совместимость

