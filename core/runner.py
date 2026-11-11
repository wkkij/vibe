import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .i18n import t


@dataclass
class CommandExecResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    def combined_output(self, max_chars: int = 12000) -> str:
        out = f"$ {self.command}\nExit code: {self.returncode}\n"
        if self.stdout.strip():
            out += f"--- STDOUT ---\n{self.stdout.strip()}\n"
        if self.stderr.strip():
            out += f"--- STDERR ---\n{self.stderr.strip()}\n"
        if len(out) > max_chars:
            half = max_chars // 2
            out = out[:half] + "\n..." + t("[ОБРЕЗАНО]") + "...\n" + out[-half:]
        return out


class TerminalRunner:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()

    def run_cmd(self, command: str, timeout_sec: int = 180) -> CommandExecResult:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
            )
            return CommandExecResult(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired as e:
            return CommandExecResult(
                command=command,
                returncode=124,
                stdout=e.stdout or "",
                stderr=t("Команда превысила таймаут ({sec} сек).", sec=timeout_sec),
            )
        except Exception as e:
            return CommandExecResult(
                command=command,
                returncode=1,
                stdout="",
                stderr=t("Ошибка запуска процесса: {e}", e=e),
            )


class BrowserVerifier:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()

    async def inspect_url(self, url: str) -> Tuple[Optional[Path], List[str], str]:
        from playwright.async_api import async_playwright

        console_errors: List[str] = []
        page_title = ""
        screenshot_path = self.root / ".vibe_last_screenshot.png"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})

            page.on(
                "console",
                lambda msg: console_errors.append(f"[console.{msg.type}] {msg.text}")
                if msg.type in ("error", "warning")
                else None,
            )
            page.on("pageerror", lambda err: console_errors.append(f"[Uncaught PageError] {err}"))

            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(1.0)
                page_title = await page.title()
                await page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception as e:
                console_errors.append(f"[Navigation Error] {e}")
            finally:
                await browser.close()

        return (screenshot_path if screenshot_path.exists() else None), console_errors, page_title
