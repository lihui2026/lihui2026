"""Core configuration loading.

所有运行参数都集中在 ``config.ini`` 中；文件不存在时可通过
:func:`ensure_config` 自动生成一份带注释的完整模板。
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


DEFAULTS: Dict[str, Dict[str, str]] = {
    "LLM": {
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "your-model-name",
        "api_key": "sk-REPLACE-ME",
        "context_window": "0",
        "timeout": "120",
        "models_timeout": "8",
        "default_context_window": "128000",
        "compact_threshold": "0.6",
        "summary_target_tokens": "5000",
        "compaction_message_char_limit": "20000",
        "max_tool_rounds": "5",
        "mcp_tool_description_limit": "300",
        "agents_md_enabled": "true",
        "agents_md_filename": "AGENT.md",
        "agents_md_max_chars": "8000",
    },
    "MCP": {
        "connect_timeout": "30",
        "call_timeout": "120",
        "output_limit": "20000",
    },
    "TOOLS": {
        "tool_timeout": "10",
        "cli_timeout": "30",
        "cli_output_limit": "6000",
        "fetch_connect_timeout": "10",
        "fetch_max_timeout": "30",
        "fetch_timeout": "40",
        "search_timeout": "30",
        "recall_max_hits": "8",
        "recall_snippet_chars": "400",
        "recall_total_chars": "6000",
        "skill_description_limit": "200",
        "skill_content_limit": "20000",
        "tool_workspace_root": "",
    },
    "search": {
        "baidu_qianfan_api_key": "",
    },
    "SESSION": {
        "dir": ".agents/sessions",
        "auto_save": "true",
        "list_limit": "50",
    },
    "UI": {
        "sidebar_width": "34",
        "command_palette_max": "8",
    },
}


CONFIG_TEMPLATE = """; xAgent 配置文件
; 首次运行会自动生成此文件；请根据实际情况修改后重启 xAgent。

[LLM]
; OpenAI 兼容接口地址（不要以 / 结尾）
base_url = http://127.0.0.1:1234/v1
model = your-model-name
api_key = sk-REPLACE-ME
; 可选：手动指定模型上下文窗口大小（Token）。0 表示自动探测，探测失败时使用 default_context_window。
context_window = 0
; 请求超时（秒）
timeout = 120
; /models 探测超时（秒）
models_timeout = 8
; 无法探测上下文窗口时使用的默认值（Token）
default_context_window = 128000
; 上下文占用比例达到该值时暂停接收新提示词（0.6 = 60%）
compact_threshold = 0.6
; 压缩摘要的目标 Token 数
summary_target_tokens = 5000
; 压缩时单条消息内容的最大字符数
compaction_message_char_limit = 20000
; 单次请求最多允许的工具调用轮次
max_tool_rounds = 5
; System Prompt 中 MCP 工具描述的截断长度
mcp_tool_description_limit = 300
; 是否注入项目根目录的 AGENT.md（/agents 可查看状态）
agents_md_enabled = true
; 长期规则文件名；找不到时依次回退 AGENT.md / AGENTS.md / agents.md / agent.md
agents_md_filename = AGENT.md
; 注入 System Prompt 的最大字符数，超出部分截断（避免 AGENTS.md 挤占上下文）
agents_md_max_chars = 8000

[MCP]
; 单个 MCP Server 连接超时（秒）
connect_timeout = 30
; MCP 工具调用超时（秒）
call_timeout = 120
; MCP 工具输出最大字符数
output_limit = 20000

[TOOLS]
; 普通工具执行超时（秒）
tool_timeout = 10
; RunCli 命令执行超时（秒）
cli_timeout = 30
; RunCli 输出最大字符数
cli_output_limit = 6000
; fetchWeb 的 curl 连接超时 / 最大耗时 / 进程超时（秒）
fetch_connect_timeout = 10
fetch_max_timeout = 30
fetch_timeout = 40
; searchWeb 请求超时（秒）
search_timeout = 30
; recallContext 检索结果控制
recall_max_hits = 8
recall_snippet_chars = 400
recall_total_chars = 6000
; 自动生成 Skill 描述时的截断长度
skill_description_limit = 200
; loadSkill 单次返回内容的最大字符数（超出截断，避免一次读入过大文件）
skill_content_limit = 20000
; 文件操作工具的路径根目录：留空表示不限制；填写后所有写/删/改操作必须位于该目录内
tool_workspace_root =

[search]
; 百度千帆搜索 API Key（searchWeb 工具使用）
baidu_qianfan_api_key = REPLACE_WITH_YOUR_KEY

[SESSION]
; 会话事件日志目录（相对于启动目录）
dir = .agents/sessions
; 每条消息是否立即写入会话文件
auto_save = true
; /resume 列表最多显示的会话数
list_limit = 50

[UI]
; MCP 侧栏宽度（字符数）
sidebar_width = 34
; 命令补全面板最多显示的命令数
command_palette_max = 8
"""


def default_base_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_config_path() -> Path:
    return Path(default_base_dir()) / "config.ini"


class Config:
    def __init__(self, path: str | Path | None = None):
        self.base_dir = default_base_dir()
        self.path = Path(path) if path is not None else default_config_path()
        self.cfg = configparser.ConfigParser(interpolation=None)
        try:
            self.cfg.read(str(self.path), encoding="utf-8-sig")
        except OSError:
            pass

        self.llm = self.cfg["LLM"] if self.cfg.has_section("LLM") else {}

        self.base_url = self._get_str("LLM", "base_url").rstrip("/")
        self.model = self._get_str("LLM", "model")
        self.api_key = self._get_str("LLM", "api_key")

        self.context_window = self._get_int("LLM", "context_window")
        self.llm_timeout = self._get_int("LLM", "timeout")
        self.models_timeout = self._get_int("LLM", "models_timeout")
        self.default_context_window = self._get_int("LLM", "default_context_window")
        self.compact_threshold = self._get_float("LLM", "compact_threshold")
        self.summary_target_tokens = self._get_int("LLM", "summary_target_tokens")
        self.compaction_message_char_limit = self._get_int(
            "LLM", "compaction_message_char_limit"
        )
        self.max_tool_rounds = self._get_int("LLM", "max_tool_rounds")
        self.mcp_tool_description_limit = self._get_int(
            "LLM", "mcp_tool_description_limit"
        )
        self.agents_md_enabled = self._get_bool("LLM", "agents_md_enabled")
        self.agents_md_filename = self._get_str("LLM", "agents_md_filename")
        self.agents_md_max_chars = self._get_int("LLM", "agents_md_max_chars")

        self.mcp_connect_timeout = self._get_float("MCP", "connect_timeout")
        self.mcp_call_timeout = self._get_float("MCP", "call_timeout")
        self.mcp_output_limit = self._get_int("MCP", "output_limit")

        self.tool_timeout = self._get_int("TOOLS", "tool_timeout")
        self.cli_timeout = self._get_int("TOOLS", "cli_timeout")
        self.cli_output_limit = self._get_int("TOOLS", "cli_output_limit")
        self.fetch_connect_timeout = self._get_int("TOOLS", "fetch_connect_timeout")
        self.fetch_max_timeout = self._get_int("TOOLS", "fetch_max_timeout")
        self.fetch_timeout = self._get_int("TOOLS", "fetch_timeout")
        self.search_timeout = self._get_int("TOOLS", "search_timeout")
        self.recall_max_hits = self._get_int("TOOLS", "recall_max_hits")
        self.recall_snippet_chars = self._get_int("TOOLS", "recall_snippet_chars")
        self.recall_total_chars = self._get_int("TOOLS", "recall_total_chars")
        self.skill_description_limit = self._get_int("TOOLS", "skill_description_limit")
        self.skill_content_limit = self._get_int("TOOLS", "skill_content_limit")
        self.tool_workspace_root = self._get_str("TOOLS", "tool_workspace_root")

        self.search_api_key = self._get_str("search", "baidu_qianfan_api_key")

        self.session_dir = self._get_str("SESSION", "dir") or ".agents/sessions"
        self.session_auto_save = self._get_bool("SESSION", "auto_save")
        self.session_list_limit = self._get_int("SESSION", "list_limit")

        self.sidebar_width = self._get_int("UI", "sidebar_width")
        self.command_palette_max = self._get_int("UI", "command_palette_max")

    # ---------- typed getters ----------

    def _raw(self, section: str, key: str) -> str:
        default = DEFAULTS.get(section, {}).get(key, "")
        try:
            value = self.cfg.get(section, key, fallback=default)
        except (configparser.Error, ValueError):
            value = default
        return str(value).strip()

    def _get_str(self, section: str, key: str) -> str:
        return self._raw(section, key)

    def _get_int(self, section: str, key: str) -> int:
        value = self._raw(section, key)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(float(DEFAULTS.get(section, {}).get(key, "0")))

    def _get_float(self, section: str, key: str) -> float:
        value = self._raw(section, key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(DEFAULTS.get(section, {}).get(key, "0"))

    def _get_bool(self, section: str, key: str) -> bool:
        value = self._raw(section, key).lower()
        if value in ("1", "true", "yes", "on"):
            return True
        if value in ("0", "false", "no", "off"):
            return False
        return str(DEFAULTS.get(section, {}).get(key, "")).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )


_config_cache: Optional[Config] = None
_config_cache_path: Optional[str] = None


def load_config(path: str | Path | None = None) -> Config:
    return Config(path)


def get_config() -> Config:
    """返回默认配置文件的缓存实例（供各核心模块读取运行参数）。"""
    global _config_cache, _config_cache_path
    path = default_config_path()
    key = str(path)
    if _config_cache is None or _config_cache_path != key:
        _config_cache = Config(path)
        _config_cache_path = key
    return _config_cache


def reload_config() -> Config:
    global _config_cache
    _config_cache = None
    return get_config()


def ensure_config(path: str | Path | None = None) -> Tuple[Path, bool]:
    """确保配置文件存在；不存在时写入完整模板并返回 ``(路径, 是否新建)``。"""
    target = Path(path) if path is not None else default_config_path()
    if target.is_file():
        return target, False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    reload_config()
    return target, True


def get_config_value(
    section: str, key: str, fallback: Any = None, path: str | Path | None = None
) -> Any:
    parser = configparser.ConfigParser(interpolation=None)
    target = Path(path) if path is not None else default_config_path()
    parser.read(str(target), encoding="utf-8-sig")
    return parser.get(section, key, fallback=fallback)


def set_config(
    section: str, key: str, value: Any, path: str | Path | None = None
) -> Path:
    target = Path(path) if path is not None else default_config_path()
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(str(target), encoding="utf-8-sig")
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, key, str(value))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        parser.write(f)
    reload_config()
    return target
