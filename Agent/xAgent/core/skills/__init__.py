"""Skill discovery, loading and creation following the Agent Skills specification."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None



def normalize_skill_name(name: Any) -> Optional[str]:
    if not isinstance(name, str):
        return None
    value = name.strip().lower()
    if not value:
        return None
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or None


class SkillManager:
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root if project_root is not None else os.getcwd()).resolve()
        self.skills_dir = self.project_root / ".agents" / "skills"
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.discover()

    def discover(self) -> None:
        self.skills = {}
        try:
            if not self.skills_dir.is_dir():
                return
            entries = sorted(
                (entry for entry in self.skills_dir.iterdir() if entry.is_dir()),
                key=lambda entry: entry.name.lower(),
            )
        except OSError:
            return

        for entry in entries:
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            content = self._read_text(skill_md)
            if content is None:
                continue
            name, description = self._parse_frontmatter(content)
            if not name or not description:
                continue
            if name in self.skills:
                continue
            try:
                skill_dir = entry.resolve()
                skill_md_path = skill_md.resolve()
            except OSError:
                continue
            self.skills[name] = {
                "name": name,
                "description": description,
                "dir": str(skill_dir),
                "skill_md": str(skill_md_path),
            }

    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        for encoding in ("utf-8-sig", "gbk"):
            try:
                return path.read_text(encoding=encoding)
            except (UnicodeDecodeError, LookupError):
                continue
            except OSError:
                return None
        return None

    def _parse_frontmatter(self, content: str) -> Tuple[Optional[str], Optional[str]]:
        text = content.lstrip("\ufeff")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return None, None

        end_idx = -1
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                end_idx = index
                break
        if end_idx == -1:
            return None, None

        block = "\n".join(lines[1:end_idx])
        data: Any = None
        if yaml is not None:
            try:
                data = yaml.safe_load(block)
            except Exception:
                data = None
        if not isinstance(data, dict) or "name" not in data or "description" not in data:
            fallback = self._parse_simple_yaml(block)
            if not isinstance(data, dict) or fallback:
                data = fallback
        if not isinstance(data, dict):
            return None, None

        name = data.get("name")
        description = data.get("description")
        if not isinstance(name, str) or not name.strip():
            return None, None
        if not isinstance(description, str) or not description.strip():
            return None, None
        return name.strip(), description.strip()

    @staticmethod
    def _parse_simple_yaml(text: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in line:
                index += 1
                continue

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                separator = "\n" if value.startswith("|") else " "
                block: List[str] = []
                index += 1
                while index < len(lines):
                    next_line = lines[index]
                    if next_line.strip() and not next_line[:1].isspace():
                        break
                    block.append(next_line.strip())
                    index += 1
                data[key] = separator.join(block).strip()
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            data[key] = value
            index += 1
        return data

    def get_skills_info(self) -> List[Dict[str, str]]:
        result = [
            {"name": name, "description": info["description"]}
            for name, info in self.skills.items()
        ]
        result.sort(key=lambda item: item["name"])
        return result

    def create_skill(self, name: Any, skill_context: Any) -> str:
        slug = normalize_skill_name(name)
        if not slug:
            return (
                "创建 Skill 失败：name 必须包含英文字母或数字，且只能使用小写字母、数字和连字符"
                "（例如 my-skill）。"
            )
        if not isinstance(skill_context, str) or not skill_context.strip():
            return "创建 Skill 失败：skillContext 不能为空。"

        skill_dir = self.skills_dir / slug
        if skill_dir.exists() or slug in self.skills:
            return f"Skill '{slug}' 已存在，未做任何修改：{skill_dir}"

        frontmatter, body = self._split_frontmatter(skill_context)
        description = frontmatter.get("description")
        if not isinstance(description, str) or not description.strip():
            description = self._derive_description(body)
        description = description.strip() or slug.replace("-", " ")

        content = self._render_skill_content(slug, description, frontmatter, body)
        try:
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            skill_dir.mkdir(exist_ok=False)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        except FileExistsError:
            return f"Skill '{slug}' 已存在，未做任何修改：{skill_dir}"
        except OSError as exc:
            return f"创建 Skill 失败：{exc}"

        self.discover()
        return f"已创建 Skill：{slug}\n目录：{skill_dir}\n文件：{skill_dir / 'SKILL.md'}"

    @staticmethod
    def _split_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
        text = content.lstrip("\ufeff")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, text

        end_idx = -1
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                end_idx = index
                break
        if end_idx == -1:
            return {}, text

        block = "\n".join(lines[1:end_idx])
        data: Dict[str, Any] = {}
        if yaml is not None:
            try:
                loaded = yaml.safe_load(block)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        if not data:
            data = SkillManager._parse_simple_yaml(block)
        body = "\n".join(lines[end_idx + 1:])
        return data, body

    @staticmethod
    def _derive_description(body: str) -> str:
        for line in body.splitlines():
            text = line.strip()
            if not text:
                continue
            text = re.sub(r"^(?:#{1,6}\s*|[-*+]\s+|>\s*|\d+\.\s+)", "", text).strip()
            if text:
                return text[:200]
        return ""

    @staticmethod
    def _render_skill_content(
        name: str,
        description: str,
        frontmatter: Dict[str, Any],
        body: str,
    ) -> str:
        data: Dict[str, Any] = {"name": name, "description": description}
        if isinstance(frontmatter, dict):
            for key, value in frontmatter.items():
                if not isinstance(key, str) or key in ("name", "description"):
                    continue
                if key not in data:
                    data[key] = value

        if yaml is not None:
            try:
                frontmatter_text = yaml.safe_dump(
                    data,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                ).strip()
            except Exception:
                frontmatter_text = SkillManager._manual_frontmatter(data)
        else:
            frontmatter_text = SkillManager._manual_frontmatter(data)

        content = f"---\n{frontmatter_text}\n---\n"
        body_text = body.lstrip("\r\n")
        if body_text.strip():
            content += "\n" + body_text.rstrip() + "\n"
        return content

    @staticmethod
    def _manual_frontmatter(data: Dict[str, Any]) -> str:
        lines: List[str] = []
        for key, value in data.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif value is None:
                rendered = "null"
            elif isinstance(value, (int, float)):
                rendered = str(value)
            elif isinstance(value, (dict, list)):
                continue
            else:
                rendered = json.dumps(str(value), ensure_ascii=False)
            lines.append(f"{key}: {rendered}")
        return "\n".join(lines)

    def load_skill(self, name: str, filename: Optional[str] = None) -> str:
        if isinstance(name, str):
            name = name.strip()
        info = self.skills.get(name) if isinstance(name, str) else None
        if info is None:
            available = ", ".join(sorted(self.skills.keys())) or "无"
            return f"未找到名为 '{name}' 的 Skill。可用的 Skills：{available}"

        skill_dir = Path(info["dir"]).resolve()
        if filename is None or (isinstance(filename, str) and not filename.strip()):
            return self._read_skill_file(Path(info["skill_md"]).resolve(), skill_dir)

        filename = str(filename).strip()
        candidates = self._find_candidates(skill_dir, filename)
        if not candidates:
            return f"在 Skill '{name}' 的目录中未找到文件 '{filename}'。"
        if len(candidates) > 1:
            candidate_list = "\n".join(f"- {path}" for path in candidates)
            return f"找到多个同名文件，请指定更明确的路径：\n{candidate_list}"
        return self._read_skill_file(candidates[0], skill_dir)

    @staticmethod
    def _read_skill_file(path: Path, skill_dir: Path) -> str:
        try:
            target = path.resolve()
            target.relative_to(skill_dir)
        except (OSError, ValueError):
            return "文件路径不在指定 Skill 目录内，已拒绝读取。"
        if not target.is_file():
            return f"文件不存在或不是普通文件：{target}"
        content = SkillManager._read_text(target)
        if content is None:
            return f"读取文件失败：{target}"
        return content

    def _find_candidates(self, skill_dir: Path, filename: str) -> List[Path]:
        candidates: List[Path] = []
        seen = set()

        def add(path: Path) -> None:
            try:
                resolved = path.resolve()
                resolved.relative_to(skill_dir)
            except (OSError, ValueError):
                return
            if not resolved.is_file():
                return
            key = os.path.normcase(os.path.abspath(str(resolved)))
            if key in seen:
                return
            seen.add(key)
            candidates.append(resolved)

        raw = Path(filename)
        if raw.is_absolute():
            add(raw)
        else:
            add(skill_dir / raw)
            add(self.project_root / raw)

        if candidates:
            return candidates

        if raw.name == filename and raw.name not in ("", ".", ".."):
            try:
                found = list(skill_dir.rglob(raw.name))
            except OSError:
                found = []
            for path in found:
                add(path)
        return candidates


_startup_cwd = os.getcwd()
skill_manager = SkillManager(project_root=_startup_cwd)
