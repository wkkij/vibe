import os
from pathlib import Path
from typing import List, Optional, Tuple
import pathspec
from .config import DEFAULT_IGNORE_PATTERNS, VibeConfig

# Служебные папки Vibe: бэкапы патчей и профили Chrome. Папка .vibeide (код IDE) сюда НЕ входит.
SERVICE_DIRS = {".vibe_backups"}
SERVICE_DIR_PREFIXES = (".vibe_chrome_profile",)


class ContextPacker:
    def __init__(self, config: VibeConfig):
        self.config = config
        self.root = config.project_root
        self.spec = self._build_pathspec()

    def _build_pathspec(self) -> pathspec.PathSpec:
        patterns = list(DEFAULT_IGNORE_PATTERNS) + list(self.config.extra_ignores)

        gitignore_path = self.root / ".gitignore"
        if gitignore_path.exists():
            try:
                patterns.extend(gitignore_path.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                pass

        vibeignore_path = self.root / ".vibeignore"
        if vibeignore_path.exists():
            try:
                patterns.extend(vibeignore_path.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                pass

        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def _is_binary(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(2048)
                if b"\x00" in chunk:
                    return True
            return False
        except Exception:
            return True

    def collect_files(self, max_file_size_kb: int = 250) -> List[Path]:
        collected = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = Path(dirpath).relative_to(self.root)
            rel_dir_str = "" if str(rel_dir) == "." else str(rel_dir).replace("\\", "/") + "/"

            # служебные папки CLI скрываем, но .vibeide (исходники Vibe IDE) должна попадать в контекст
            dirnames[:] = [
                d for d in sorted(dirnames)
                if not self.spec.match_file(rel_dir_str + d + "/")
                and d not in SERVICE_DIRS
                and not d.startswith(SERVICE_DIR_PREFIXES)
            ]

            for fname in sorted(filenames):
                rel_file = rel_dir_str + fname
                if self.spec.match_file(rel_file):
                    continue
                full_path = Path(dirpath) / fname
                try:
                    size_kb = full_path.stat().st_size / 1024
                    if size_kb > max_file_size_kb:
                        continue
                    if self._is_binary(full_path):
                        continue
                    collected.append(full_path)
                except Exception:
                    continue
        return collected

    def build_tree_string(self, files: List[Path]) -> str:
        lines = [f"Корень проекта: {self.root.name}/"]
        for f in files:
            rel = f.relative_to(self.root).as_posix()
            lines.append(f"  ├── {rel}")
        return "\n".join(lines)

    def pack_repository(
        self,
        target_files: List[str] = None,
        selected: Optional[List[Path]] = None,
        scope_note: str = "",
    ) -> Tuple[str, int, int]:
        """selected — точный список файлов (автоподбор контекста); дерево проекта при этом остаётся полным."""
        all_files = self.collect_files()
        if selected is not None:
            keep = {Path(p).resolve() for p in selected}
            selected_files = [f for f in all_files if f.resolve() in keep]
        elif target_files:
            normalized_targets = [t.replace("\\", "/").strip("/") for t in target_files]
            selected_files = [
                f for f in all_files
                if any(n in f.relative_to(self.root).as_posix() for n in normalized_targets)
            ]
        else:
            selected_files = all_files

        tree_str = self.build_tree_string(all_files)
        rules_str = self.config.get_project_rules()

        parts = []
        parts.append("<project_overview>")
        parts.append(tree_str)
        parts.append("</project_overview>\n")

        if rules_str:
            parts.append("<project_conventions>")
            parts.append(rules_str)
            parts.append("</project_conventions>\n")

        if scope_note:
            parts.append("<context_scope>")
            parts.append(scope_note)
            parts.append("</context_scope>\n")

        parts.append("<repository_files>")
        for f in selected_files:
            rel = f.relative_to(self.root).as_posix()
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                parts.append(f"\n=== FILE: {rel} ===\n{content}\n=== END FILE: {rel} ===")
            except Exception as e:
                parts.append(f"\n=== FILE: {rel} (Error reading: {e}) ===")
        parts.append("</repository_files>")

        full_text = "\n".join(parts)
        approx_tokens = len(full_text) // 4
        return full_text, len(selected_files), approx_tokens

    def pack_files(self, rel_paths: List[str]) -> str:
        """Актуальное содержимое конкретных файлов (для синхронизации чата после патчей)."""
        parts = []
        for rel in sorted(set(rel_paths)):
            fp = (self.root / rel)
            if fp.is_file():
                try:
                    parts.append(f"=== FILE: {rel} ===\n{fp.read_text(encoding='utf-8', errors='replace')}\n=== END FILE: {rel} ===")
                except Exception:
                    pass
            else:
                parts.append(f"=== FILE: {rel} === (удалён)")
        return "\n".join(parts)

    def write_context_bundle_file(
        self,
        target_files: List[str] = None,
        canary: str = "",
        selected: Optional[List[Path]] = None,
        scope_note: str = "",
    ) -> Tuple[Path, int, int]:
        text, count, tokens = self.pack_repository(target_files, selected=selected, scope_note=scope_note)
        if canary:
            text += f"\nVIBE_CANARY={canary}\n"
        bundle_path = self.root / ".vibe_context_bundle.txt"
        bundle_path.write_text(text, encoding="utf-8")
        return bundle_path, count, tokens
