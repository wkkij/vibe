import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .i18n import t


@dataclass
class PatchResult:
    file_path: str
    action: str  # "MODIFIED", "CREATED", "DELETED", "FAILED"
    message: str
    blocks_applied: int = 0
    failed_blocks: List[str] = field(default_factory=list)  # SEARCH-блоки, которые не совпали


class DiffPatcher:
    def __init__(self, project_root: Path, backup_root: Path):
        self.root = project_root.resolve()
        self.backup_root = backup_root.resolve()

    def _inside_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root)
            return True
        except ValueError:
            return False

    def _create_backup_snapshot(self, affected_rel_paths: List[str]) -> Optional[Path]:
        if not affected_rel_paths:
            return None
        timestamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        snap_dir = self.backup_root / timestamp
        snap_dir.mkdir(parents=True, exist_ok=True)

        manifest = []
        for rel_path in set(affected_rel_paths):
            clean_rel = rel_path.strip().lstrip("/\\")
            src = (self.root / clean_rel).resolve()
            if not self._inside_root(src):
                continue
            if src.exists() and src.is_file():
                dst = snap_dir / clean_rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                manifest.append({"path": clean_rel, "existed": True})
            else:
                manifest.append({"path": clean_rel, "existed": False})

        (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return snap_dir

    def undo_last_snapshot(self) -> Tuple[bool, str]:
        if not self.backup_root.exists():
            return False, t("Бэкапы не найдены (.vibe_backups пуст).")
        snapshots = sorted([d for d in self.backup_root.iterdir() if d.is_dir()], reverse=True)
        if not snapshots:
            return False, t("Нет доступных точек отката.")

        latest = snapshots[0]
        manifest_file = latest / "manifest.json"
        if not manifest_file.exists():
            shutil.rmtree(latest, ignore_errors=True)
            return False, t("Манифест бэкапа поврежден.")

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        restored = []
        for item in manifest:
            rel_path = item["path"]
            existed = item["existed"]
            target = self.root / rel_path
            if existed:
                backup_copy = latest / rel_path
                if backup_copy.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_copy, target)
                    restored.append(t("Восстановлен: {path}", path=rel_path))
            else:
                if target.exists():
                    target.unlink()
                    restored.append(t("Удален (был создан): {path}", path=rel_path))

        shutil.rmtree(latest, ignore_errors=True)
        return True, t("Откат снапшота {name} выполнен:", name=latest.name) + "\n" + "\n".join(restored)

    def _apply_search_replace_block(self, content: str, search_block: str, replace_block: str) -> Tuple[Optional[str], str]:
        if search_block in content:
            return content.replace(search_block, replace_block, 1), "exact"

        norm_content = content.replace("\r\n", "\n")
        norm_search = search_block.replace("\r\n", "\n").strip("\n")
        norm_replace = replace_block.replace("\r\n", "\n").strip("\n")

        if norm_search in norm_content:
            return norm_content.replace(norm_search, norm_replace, 1), "normalized_lf"

        content_lines = norm_content.split("\n")
        search_lines = [line.rstrip() for line in norm_search.split("\n")]
        n_search = len(search_lines)

        if n_search > 0:
            for i in range(len(content_lines) - n_search + 1):
                window = [line.rstrip() for line in content_lines[i : i + n_search]]
                if window == search_lines:
                    new_lines = content_lines[:i] + norm_replace.split("\n") + content_lines[i + n_search :]
                    return "\n".join(new_lines), "line_trimmed"

        stripped_search = [line.strip() for line in norm_search.split("\n") if line.strip()]
        if len(stripped_search) >= 2:
            for i in range(len(content_lines) - len(search_lines) + 1):
                window_stripped = [line.strip() for line in content_lines[i : i + len(search_lines)] if line.strip()]
                if window_stripped == stripped_search:
                    new_lines = content_lines[:i] + norm_replace.split("\n") + content_lines[i + len(search_lines) :]
                    return "\n".join(new_lines), "indent_fuzzy"

        return None, "not_found"

    def parse_and_apply(self, response_text: str) -> Tuple[List[PatchResult], List[str]]:
        results: List[PatchResult] = []
        commands: List[str] = []

        cmd_pattern = re.compile(r"<<<RUN_CMD>>>\s*(.*?)\s*<<<END_CMD>>>", re.DOTALL)
        for match in cmd_pattern.finditer(response_text):
            cmd = match.group(1).strip()
            cmd = re.sub(r"^```[a-zA-Z]*\n", "", cmd)
            cmd = re.sub(r"\n```$", "", cmd).strip()
            if cmd:
                commands.append(cmd)

        create_pattern = re.compile(r"<<<CREATE:\s*([^>]+?)>>>\n?(.*?)<<<END_CREATE>>>", re.DOTALL)
        delete_pattern = re.compile(r"<<<DELETE:\s*([^>]+?)>>>")
        file_pattern = re.compile(r"<<<FILE:\s*([^>]+?)>>>\n?(.*?)<<<END_FILE>>>", re.DOTALL)
        sr_pattern = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE", re.DOTALL)

        affected_paths = []
        for m in create_pattern.finditer(response_text):
            affected_paths.append(m.group(1).strip())
        for m in delete_pattern.finditer(response_text):
            affected_paths.append(m.group(1).strip())
        for m in file_pattern.finditer(response_text):
            affected_paths.append(m.group(1).strip())

        if affected_paths:
            self._create_backup_snapshot(affected_paths)

        for match in create_pattern.finditer(response_text):
            rel_path = match.group(1).strip().lstrip("/\\")
            raw_body = match.group(2)
            raw_body = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", raw_body.strip())
            raw_body = re.sub(r"\n```$", "", raw_body)

            target_path = (self.root / rel_path).resolve()
            if not self._inside_root(target_path):
                results.append(PatchResult(rel_path, "FAILED", t("Попытка записи за пределы корня проекта")))
                continue

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(raw_body + "\n", encoding="utf-8")
                results.append(PatchResult(rel_path, "CREATED", t("Файл успешно создан"), 1))
            except Exception as e:
                results.append(PatchResult(rel_path, "FAILED", t("Ошибка создания: {e}", e=e)))

        for match in delete_pattern.finditer(response_text):
            rel_path = match.group(1).strip().lstrip("/\\")
            target_path = (self.root / rel_path).resolve()
            if target_path.exists() and self._inside_root(target_path):
                try:
                    target_path.unlink()
                    results.append(PatchResult(rel_path, "DELETED", t("Файл удален"), 1))
                except Exception as e:
                    results.append(PatchResult(rel_path, "FAILED", t("Ошибка удаления: {e}", e=e)))

        for match in file_pattern.finditer(response_text):
            rel_path = match.group(1).strip().lstrip("/\\")
            body = match.group(2)
            target_path = (self.root / rel_path).resolve()

            if not self._inside_root(target_path):
                results.append(PatchResult(rel_path, "FAILED", t("Путь вне корня проекта")))
                continue

            if not target_path.exists():
                results.append(PatchResult(rel_path, "FAILED", t("Файл для патча не найден на диске")))
                continue

            raw = target_path.read_bytes().decode("utf-8", errors="replace")
            eol = "\r\n" if "\r\n" in raw else "\n"
            content = raw.replace("\r\n", "\n")
            sr_blocks = list(sr_pattern.finditer(body))
            if not sr_blocks:
                results.append(PatchResult(rel_path, "FAILED", t("Не найдены блоки SEARCH/REPLACE внутри <<<FILE>>>")))
                continue

            applied_count = 0
            failed_blocks = 0
            failed_texts: List[str] = []
            for sr in sr_blocks:
                search_part = sr.group(1)
                replace_part = sr.group(2)
                updated_content, _ = self._apply_search_replace_block(content, search_part, replace_part)
                if updated_content is not None:
                    content = updated_content
                    applied_count += 1
                else:
                    failed_blocks += 1
                    failed_texts.append(search_part)

            if applied_count > 0:
                out = content.replace("\n", eol) if eol == "\r\n" else content
                target_path.write_bytes(out.encode("utf-8"))
                msg = t("Применено блоков: {applied}/{total}", applied=applied_count, total=len(sr_blocks))
                if failed_blocks > 0:
                    msg += t(" (Не совпало блоков: {n})", n=failed_blocks)
                results.append(PatchResult(rel_path, "MODIFIED", msg, applied_count, failed_texts))
            else:
                results.append(PatchResult(rel_path, "FAILED", t("Ни один из {n} блоков SEARCH не совпал с файлом", n=len(sr_blocks)), 0, failed_texts))

        return results, commands

