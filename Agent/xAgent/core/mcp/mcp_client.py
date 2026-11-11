"""MCP Client manager for xAgent.

- 读取 ``office/.mcp.json`` 配置文件（找不到时回退到其他常见位置的 .mcp.json）；
- 通过官方 MCP Python SDK 连接各 MCP Server，支持 ``streamable-http`` 协议（兼容 stdio）；
- 调用 ``list_tools()`` 发现工具，工具名统一加 ``服务名__原始工具名`` 前缀并维护映射表；
- 工具调用转发到对应 MCP Server；单个服务连不上只告警，不阻塞其他工具；
- 所有日志带 ``[MCP]`` 标记，方便调试。
"""
from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import inspect
import json
import logging
import os
import re
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from core.config import get_config

TOOL_NAME_SEPARATOR = "__"
STREAMABLE_HTTP_TYPE = "streamable-http"
_OPENAI_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

logger = logging.getLogger("xAgent.mcp")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[MCP] %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_XAGENT_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _XAGENT_ROOT.parent


def _find_mcp_config_path() -> Path:
    """定位 MCP 配置文件，优先使用 office/.mcp.json。"""
    override = os.environ.get("XAGENT_MCP_CONFIG")
    if override:
        return Path(override).resolve()
    candidates = [
        Path.cwd() / "office" / ".mcp.json",
        _WORKSPACE_ROOT / "office" / ".mcp.json",
        Path.cwd() / ".mcp.json",
        _XAGENT_ROOT / ".mcp.json",
        _WORKSPACE_ROOT / ".mcp.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    if (_WORKSPACE_ROOT / "office").is_dir():
        return (_WORKSPACE_ROOT / "office" / ".mcp.json").resolve()
    return (Path.cwd() / ".mcp.json").resolve()


@dataclass
class MCPServerConfig:
    name: str
    transport: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


@dataclass
class MCPServerHandle:
    config: MCPServerConfig
    session: Any
    stack: AsyncExitStack
    tools: List[Any]


class _SDK:
    ClientSession: Any
    StdioServerParameters: Any
    stdio_client: Any


_sdk: Optional[_SDK] = None


def _load_sdk() -> _SDK:
    global _sdk
    if _sdk is not None:
        return _sdk
    try:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError as exc:
        raise RuntimeError("缺少 MCP Python SDK，请先安装：pip install mcp") from exc
    bundle = SimpleNamespace(
        ClientSession=ClientSession,
        StdioServerParameters=StdioServerParameters,
        stdio_client=stdio_client,
    )
    _sdk = bundle
    return bundle


def _get_streamable_http_client():
    try:
        from mcp.client.streamable_http import streamablehttp_client as fn
    except ImportError:
        from mcp.client.streamable_http import streamable_http_client as fn
    return fn


def load_mcp_config(
    path: Path | str | None = None,
    project_root: Path | str | None = None,
) -> Tuple[Dict[str, Any], Path, Optional[str]]:
    root = Path(project_root or os.getcwd()).resolve()
    cfg_path = Path(path) if path is not None else root / ".mcp.json"
    if not cfg_path.is_file():
        return {}, cfg_path, None
    try:
        raw = cfg_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {}, cfg_path, f"读取 {cfg_path.name} 失败：{exc}"
    try:
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        return {}, cfg_path, f"解析 {cfg_path.name} 失败：{exc}"
    if not isinstance(data, dict):
        return {}, cfg_path, f"{cfg_path.name} 顶层必须是一个 JSON 对象。"
    servers = data.get("mcpServers")
    if servers is None:
        servers = data.get("servers")
    if servers is None:
        return {}, cfg_path, f"{cfg_path.name} 缺少 mcpServers 配置。"
    if not isinstance(servers, dict):
        return {}, cfg_path, f"{cfg_path.name} 中的 mcpServers 必须是对象。"
    return servers, cfg_path, None


def save_mcp_servers(
    servers: Dict[str, Any],
    path: Path | str | None = None,
    project_root: Path | str | None = None,
) -> Tuple[Path, List[str]]:
    """Merge ``servers`` into the ``mcpServers`` object of the MCP config file.

    Invalid server entries raise ``ValueError`` and nothing is written.
    Returns the config path and the list of saved server names.
    """
    if not isinstance(servers, dict) or not servers:
        raise ValueError("servers 必须是非空对象。")
    root = Path(project_root or os.getcwd()).resolve()
    cfg_path = Path(path) if path is not None else root / ".mcp.json"

    doc: Dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            raw_text = cfg_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ValueError(f"读取 {cfg_path.name} 失败：{exc}") from exc
        if raw_text.strip():
            try:
                doc = json.loads(raw_text)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"现有 {cfg_path.name} 解析失败：{exc}") from exc
            if not isinstance(doc, dict):
                raise ValueError(f"现有 {cfg_path.name} 顶层必须是一个 JSON 对象。")

    existing = doc.get("mcpServers")
    if not isinstance(existing, dict):
        existing = {}

    saved: List[str] = []
    for name, raw in servers.items():
        server_name = str(name).strip()
        if not server_name:
            raise ValueError("MCP Server 名称不能为空。")
        _normalize_server(server_name, raw, root)
        existing[server_name] = raw
        saved.append(server_name)

    doc["mcpServers"] = existing
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cfg_path.with_name(cfg_path.name + ".tmp")
    try:
        tmp_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, cfg_path)
    except OSError as exc:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise ValueError(f"写入 {cfg_path.name} 失败：{exc}") from exc
    logger.info("已保存 MCP Server 配置（%s）：%s", cfg_path, ", ".join(saved))
    return cfg_path, saved


def _normalize_transport(raw: Dict[str, Any]) -> str:
    value = raw.get("type") or raw.get("transport") or ""
    # 注意：配置中的协议 type 写作 streamable-http（横杠），这里统一归一化。
    transport = str(value).strip().lower().replace("-", "_")
    if not transport:
        transport = "streamable_http" if raw.get("url") else "stdio"
    aliases = {
        "stdio": "stdio",
        "command": "stdio",
        "streamable_http": "streamable_http",
        "streamablehttp": "streamable_http",
        "http": "streamable_http",
        "streamable_http_client": "streamable_http",
    }
    return aliases.get(transport, transport)


def _normalize_server(name: str, raw: Any, project_root: Path) -> MCPServerConfig:
    if not isinstance(raw, dict):
        raise ValueError("服务器配置必须是 JSON 对象。")
    transport = _normalize_transport(raw)
    if transport == "stdio":
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("stdio 服务器缺少 command 配置。")
        args = raw.get("args") or []
        if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
            raise ValueError("args 必须是字符串数组。")
        env = raw.get("env")
        if env is not None and not isinstance(env, dict):
            raise ValueError("env 必须是对象。")
        env_map = {str(k): str(v) for k, v in env.items()} if env else None
        cwd = raw.get("cwd")
        if cwd:
            cwd_path = Path(str(cwd))
            if not cwd_path.is_absolute():
                cwd_path = project_root / cwd_path
            cwd = str(cwd_path)
        else:
            cwd = None
        return MCPServerConfig(
            name=name,
            transport="stdio",
            command=command.strip(),
            args=list(args),
            env=env_map,
            cwd=cwd,
        )
    if transport == "streamable_http":
        url = raw.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Streamable HTTP 服务器缺少 url 配置。")
        headers = raw.get("headers")
        if headers is not None and not isinstance(headers, dict):
            raise ValueError("headers 必须是对象。")
        header_map = {str(k): str(v) for k, v in headers.items()} if headers else None
        return MCPServerConfig(
            name=name,
            transport="streamable_http",
            url=url.strip(),
            headers=header_map,
        )
    raise ValueError(f"暂不支持的传输类型：{transport}（仅支持 stdio 和 streamable-http）。")


def _sanitize_tool_name(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return (text or "tool")[:64]


def _unique_tool_name(base: str, used: set) -> str:
    base = (base or "tool")[:64]
    candidate = base
    index = 2
    while candidate.lower() in used:
        suffix = f"_{index}"
        candidate = base[: 64 - len(suffix)] + suffix
        index += 1
    return candidate


def _prefixed_tool_name(server_name: str, original_name: str) -> str:
    """生成 服务名__原始工具名 形式的对外工具名（上限 64 字符）。"""
    server = _sanitize_tool_name(server_name)
    tool = _sanitize_tool_name(original_name)
    max_tool = 64 - len(server) - len(TOOL_NAME_SEPARATOR)
    return f"{server}{TOOL_NAME_SEPARATOR}{tool[:max_tool]}"


def _to_openai_tool(tool: Any, exposed_name: str, server_name: str) -> Dict[str, Any]:
    original_name = str(getattr(tool, "name", "") or "")
    description = str(getattr(tool, "description", "") or "")
    description = (description + f"\n(原始 MCP 工具名：{original_name})").strip()
    description = f"[MCP Server: {server_name}] {description}".strip()

    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if not isinstance(schema, dict) or not schema:
        schema = {"type": "object", "properties": {}}
    else:
        schema = dict(schema)
        schema.setdefault("type", "object")

    return {
        "type": "function",
        "function": {
            "name": exposed_name,
            "description": description or f"来自 MCP Server {server_name} 的工具。",
            "parameters": schema,
        },
    }


def _truncate_output(text: str) -> str:
    limit = get_config().mcp_output_limit
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    head = limit // 2
    tail = limit - head
    return (
        f"{text[:head]}\n"
        f"...（MCP 输出过长，已截断 {omitted} 个字符，保留开头和结尾）...\n"
        f"{text[-tail:]}"
    )


def _get_attr(obj: Any, *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _format_content_block(block: Any) -> str:
    block_type = str(getattr(block, "type", "") or "")
    if block_type == "text":
        return str(getattr(block, "text", "") or "")
    if block_type in ("image", "audio"):
        mime_type = _get_attr(block, "mime_type", "mimeType") or "未知类型"
        data = str(getattr(block, "data", "") or "")
        label = "图片" if block_type == "image" else "音频"
        return f"[{label}内容：{mime_type}，base64 长度 {len(data)}]"
    if block_type == "resource_link":
        name = getattr(block, "name", "") or ""
        uri = getattr(block, "uri", "") or ""
        return f"[资源链接] {name}: {uri}".strip()
    if block_type == "resource":
        resource = getattr(block, "resource", None)
        if resource is None:
            return str(block)
        uri = getattr(resource, "uri", "") or ""
        text = getattr(resource, "text", None)
        if text is not None:
            return f"[嵌入资源 {uri}]\n{text}"
        blob = getattr(resource, "blob", None) or ""
        mime_type = _get_attr(resource, "mime_type", "mimeType") or "未知类型"
        return f"[嵌入资源 {uri}：{mime_type}，base64 长度 {len(str(blob))}]"
    if hasattr(block, "model_dump"):
        try:
            return json.dumps(block.model_dump(), ensure_ascii=False)
        except Exception:
            pass
    return str(block)


def _describe_connect_failure(exc: BaseException) -> str:
    """把连接/调用异常转换成可读的告警信息。

    TCP 连接被拒绝等错误经 anyio TaskGroup 会以 CancelledError 或
    BaseExceptionGroup 的形式传播，这里展开并提取有效信息。
    """
    if isinstance(exc, BaseExceptionGroup):
        parts: List[str] = []
        for sub in exc.exceptions:
            if isinstance(sub, asyncio.CancelledError):
                continue
            parts.append(_describe_connect_failure(sub))
        if parts:
            return "; ".join(parts)
        return "连接被取消（服务不可达）"
    if isinstance(exc, asyncio.CancelledError):
        return "连接被取消（通常为 TCP 连接被拒绝或服务不可达）"
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _format_call_result(result: Any, server_name: str, tool_name: str) -> str:
    parts: List[str] = []
    content = getattr(result, "content", None) or []
    if isinstance(content, list):
        for block in content:
            text = _format_content_block(block)
            if text:
                parts.append(text)
    elif content:
        parts.append(str(content))

    structured = _get_attr(result, "structured_content", "structuredContent")
    if structured is not None:
        try:
            structured_text = json.dumps(structured, ensure_ascii=False, indent=2)
        except Exception:
            structured_text = str(structured)
        parts.append(f"[结构化数据]\n{structured_text}")

    text = "\n".join(parts).strip()
    if not text:
        text = "（MCP 工具未返回文本内容）"
    text = _truncate_output(text)
    is_error = bool(_get_attr(result, "is_error", "isError") or False)
    if is_error:
        return f"MCP 工具返回错误（{server_name}/{tool_name}）：\n{text}"
    return text


class McpClientManager:
    """MCP 客户端管理器。

    读取 office/.mcp.json，连接所有 MCP Server，用 list_tools() 发现工具，
    以 服务名__原始工具名 暴露给 LLM，并把工具调用转发回对应 Server。
    单个服务连不上只记录告警，不影响其他 MCP 工具与本地工具。
    """

    def __init__(self, project_root: str | Path | None = None, config_path: str | Path | None = None):
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path is not None
            else _find_mcp_config_path()
        )
        self._servers: Dict[str, MCPServerConfig] = {}
        self._handles: Dict[str, MCPServerHandle] = {}
        self._tool_defs: List[Dict[str, Any]] = []
        self._tool_map: Dict[str, Tuple[str, str]] = {}
        self._tool_info: List[Dict[str, str]] = []
        self._errors: Dict[str, str] = {}
        self._local_names: set = set()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()
        self._started = False
        self._start_lock = threading.RLock()
        self._shutdown_requested = False

    # ---------- lifecycle ----------

    def start(self, local_tool_names: Any = None) -> None:
        """Load config and connect to all servers. Safe to call more than once."""
        with self._start_lock:
            if self._started:
                return
            self._started = True
            self._local_names = {str(name).lower() for name in (local_tool_names or ())}

        logger.info("MCP Client 启动，配置文件：%s", self.config_path)
        self._load_servers()
        if not self._servers:
            logger.info("未发现 MCP Server 配置，跳过连接。")
            self._build_registry()
            return

        self._thread = threading.Thread(
            target=self._run_loop,
            name="xAgent-MCPClient",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=10):
            self._errors["__client__"] = "MCP 客户端事件循环启动超时。"
            logger.error("MCP 客户端事件循环启动超时。")
            return

        connect_timeout = get_config().mcp_connect_timeout
        future = asyncio.run_coroutine_threadsafe(self._connect_all(), self._loop)
        try:
            future.result(timeout=connect_timeout + 5)
        except concurrent.futures.TimeoutError:
            self._errors["__client__"] = "MCP 服务器连接超时。"
            logger.error("MCP 服务器连接超时。")
        except Exception as exc:
            self._errors["__client__"] = f"MCP 服务器连接失败：{exc}"
            logger.error("MCP 服务器连接失败：%s", exc)
        self._build_registry()
        for line in self.describe():
            logger.info("%s", line)

    def reload(self) -> None:
        """Re-read the MCP config file and reconnect all servers in place."""
        with self._start_lock:
            if not self._started:
                self.start(local_tool_names=self._local_names)
                return
            self._servers = {}
            self._errors = {}
            self.config_path = _find_mcp_config_path()
            self._load_servers()
            loop = self._loop
            if loop is None or loop.is_closed() or self._thread is None or not self._thread.is_alive():
                self._started = False
                self.start(local_tool_names=self._local_names)
                return
            logger.info("重新加载 MCP 配置：%s", self.config_path)
            future = asyncio.run_coroutine_threadsafe(self._reload_async(), loop)
            try:
                future.result(timeout=get_config().mcp_connect_timeout + 5)
            except concurrent.futures.TimeoutError:
                self._errors["__client__"] = "MCP 服务器重新连接超时。"
                logger.error("MCP 服务器重新连接超时。")
            except Exception as exc:
                self._errors["__client__"] = f"MCP 服务器重新连接失败：{exc}"
                logger.error("MCP 服务器重新连接失败：%s", exc)
            self._build_registry()
            for line in self.describe():
                logger.info("%s", line)

    async def _reload_async(self) -> None:
        await self._shutdown_async()
        await self._connect_all()

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                if pending:
                    for task in pending:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.close()

    # ---------- config ----------

    def _load_servers(self) -> None:
        servers, _path, error = load_mcp_config(self.config_path, self.project_root)
        if error:
            self._errors["config"] = error
            logger.warning("读取 MCP 配置失败：%s", error)
            return
        for name, raw in servers.items():
            server_name = str(name)
            try:
                self._servers[server_name] = _normalize_server(
                    server_name, raw, self.project_root
                )
            except Exception as exc:
                self._errors[server_name] = f"配置无效：{exc}"
                logger.warning("MCP Server '%s' 配置无效：%s", server_name, exc)
        logger.info(
            "已加载 %d 个 MCP Server 配置：%s",
            len(self._servers),
            ", ".join(self._servers) or "（无）",
        )

    # ---------- connection ----------

    async def _connect_all(self) -> None:
        if not self._servers:
            return
        await asyncio.gather(
            *(self._connect_server(cfg) for cfg in self._servers.values()),
            return_exceptions=True,
        )

    async def _connect_server(self, cfg: MCPServerConfig) -> None:
        timeout = get_config().mcp_connect_timeout
        try:
            await asyncio.wait_for(self._open_server(cfg), timeout=timeout)
        except asyncio.TimeoutError:
            self._record_connect_failure(cfg, f"连接超时（超过 {timeout:.0f} 秒）。")
        except BaseException as exc:
            # 注意：连接被拒绝等错误经 anyio TaskGroup 会以 CancelledError /
            # BaseExceptionGroup（均不继承 Exception）传播，而
            # gather(return_exceptions=True) 会静默吞掉这类异常，
            # 因此必须在这里显式捕获并记录告警，否则失败会被完全吞没。
            self._record_connect_failure(cfg, _describe_connect_failure(exc))
        else:
            self._errors.pop(cfg.name, None)

    def _record_connect_failure(self, cfg: MCPServerConfig, message: str) -> None:
        self._errors[cfg.name] = f"连接失败：{message}"
        logger.warning(
            "MCP Server '%s' 连接失败：%s（仅告警，不影响其他工具）",
            cfg.name,
            message,
        )

    async def _open_server(self, cfg: MCPServerConfig) -> MCPServerHandle:
        stack = AsyncExitStack()
        try:
            sdk = _load_sdk()
            if cfg.transport == "stdio":
                params = sdk.StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args,
                    env=cfg.env,
                    cwd=cfg.cwd,
                )
                streams = await stack.enter_async_context(sdk.stdio_client(params))
            elif cfg.transport == "streamable_http":
                streams = await self._enter_streamable_http(cfg, stack)
            else:
                raise RuntimeError(f"不支持的传输类型：{cfg.transport}")

            read_stream, write_stream = streams[0], streams[1]
            session = await stack.enter_async_context(
                sdk.ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            tools = await self._list_tools(session)
            handle = MCPServerHandle(
                config=cfg,
                session=session,
                stack=stack,
                tools=tools,
            )
            self._handles[cfg.name] = handle
            logger.info(
                "MCP Server '%s' 连接成功（%s），list_tools() 发现 %d 个工具。",
                cfg.name,
                cfg.url or cfg.command,
                len(tools),
            )
            return handle
        except BaseException:
            # 在进入上下文的同一个任务里清理，避免 anyio cancel scope
            # 跨任务退出导致 "Attempted to exit cancel scope in a different task"。
            await self._close_stack(stack)
            raise

    async def _enter_streamable_http(self, cfg: MCPServerConfig, stack: AsyncExitStack):
        fn = _get_streamable_http_client()
        kwargs: Dict[str, Any] = {}
        try:
            parameters = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            parameters = {}
        if cfg.headers and "headers" in parameters:
            kwargs["headers"] = cfg.headers
        return await stack.enter_async_context(fn(cfg.url, **kwargs))

    async def _list_tools(self, session: Any) -> List[Any]:
        try:
            supports_cursor = "cursor" in inspect.signature(session.list_tools).parameters
        except (TypeError, ValueError):
            supports_cursor = False

        tools: List[Any] = []
        cursor: Optional[str] = None
        while True:
            if cursor and supports_cursor:
                result = await session.list_tools(cursor=cursor)
            else:
                result = await session.list_tools()
            tools.extend(getattr(result, "tools", None) or [])
            cursor = _get_attr(result, "next_cursor", "nextCursor")
            if not cursor or not supports_cursor:
                break
        return tools

    async def _close_stack(self, stack: AsyncExitStack) -> None:
        try:
            await stack.aclose()
        except Exception:
            pass

    # ---------- tool registry ----------

    def _build_registry(self) -> None:
        self._tool_defs = []
        self._tool_map = {}
        self._tool_info = []

        entries: List[Tuple[str, Any, str]] = []
        for server_name, handle in sorted(self._handles.items()):
            for tool in handle.tools:
                original = str(getattr(tool, "name", "") or "")
                if not original:
                    continue
                entries.append((server_name, tool, original))

        used = set(self._local_names)
        for server_name, tool, original in entries:
            # 工具名统一加 服务名__原始工具名 前缀，解决跨服务重名冲突
            exposed = _prefixed_tool_name(server_name, original)
            exposed = _unique_tool_name(exposed, used)
            used.add(exposed.lower())

            self._tool_map[exposed] = (server_name, original)
            self._tool_defs.append(_to_openai_tool(tool, exposed, server_name))
            self._tool_info.append(
                {
                    "name": exposed,
                    "server": server_name,
                    "original": original,
                    "description": str(getattr(tool, "description", "") or ""),
                }
            )

        if self._tool_map:
            logger.info(
                "MCP 工具映射表（%d 个）：%s",
                len(self._tool_map),
                ", ".join(
                    f"{exposed} -> {server}/{original}"
                    for exposed, (server, original) in self._tool_map.items()
                ),
            )

    def has_tool(self, name: str) -> bool:
        return name in self._tool_map

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return list(self._tool_defs)

    def get_tools_info(self) -> List[Dict[str, str]]:
        return list(self._tool_info)

    def get_errors(self) -> List[str]:
        lines: List[str] = []
        for name, message in self._errors.items():
            if name in ("config", "__client__"):
                lines.append(f"MCP：{message}")
            else:
                lines.append(f"MCP Server '{name}'：{message}")
        return lines

    def describe(self) -> List[str]:
        lines: List[str] = []
        for server_name, handle in sorted(self._handles.items()):
            lines.append(
                f"MCP Server '{server_name}' 已连接，发现 {len(handle.tools)} 个工具。"
            )
        for name, message in self._errors.items():
            if name in ("config", "__client__"):
                lines.append(f"MCP 错误：{message}")
            else:
                lines.append(f"MCP Server '{name}' 错误：{message}")
        if not self._servers and not self._errors:
            lines.append("未发现可用的 MCP Server 配置（office/.mcp.json）。")
        return lines

    # ---------- tool call forwarding ----------

    def call_tool(self, name: str, arguments: Any = None) -> str:
        mapping = self._tool_map.get(name)
        if mapping is None:
            return f"未知的 MCP 工具：{name}"
        server_name, tool_name = mapping

        if self._loop is None or self._loop.is_closed():
            logger.warning("MCP 客户端未运行，无法调用 %s/%s。", server_name, tool_name)
            return f"MCP 工具调用失败（{server_name}/{tool_name}）：MCP 客户端未运行。"

        args = arguments if isinstance(arguments, dict) else {}
        logger.info("转发工具调用：%s -> %s/%s", name, server_name, tool_name)

        async def _invoke():
            handle = self._handles.get(server_name)
            if handle is None:
                raise RuntimeError(f"MCP Server '{server_name}' 未连接。")
            return await handle.session.call_tool(tool_name, args)

        timeout = get_config().mcp_call_timeout
        future = asyncio.run_coroutine_threadsafe(_invoke(), self._loop)
        try:
            result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            logger.warning("MCP 工具调用超时（%s/%s）。", server_name, tool_name)
            return (
                f"MCP 工具调用超时（{server_name}/{tool_name}，"
                f"超过 {timeout:.0f} 秒）。"
            )
        except BaseException as exc:
            # 捕获包括 CancelledError / BaseExceptionGroup 在内的所有异常，
            # 转成错误信息返回，不阻塞其他工具调用。
            detail = _describe_connect_failure(exc)
            logger.warning("MCP 工具调用失败（%s/%s）：%s", server_name, tool_name, detail)
            return f"MCP 工具调用失败（{server_name}/{tool_name}）：{detail}"
        return _format_call_result(result, server_name, tool_name)

    # ---------- shutdown ----------

    async def _shutdown_async(self) -> None:
        handles = list(self._handles.values())
        self._handles.clear()
        for handle in handles:
            await self._close_stack(handle.stack)

    def shutdown(self) -> None:
        with self._start_lock:
            if self._shutdown_requested or not self._started:
                return
            self._shutdown_requested = True
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._shutdown_async(), loop)
            future.result(timeout=10)
        except Exception:
            pass
        try:
            loop.call_soon_threadsafe(loop.stop)
        except Exception:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("MCP Client 已关闭。")


mcp_client_manager = McpClientManager()
atexit.register(mcp_client_manager.shutdown)


__all__ = [
    "McpClientManager",
    "MCPServerConfig",
    "MCPServerHandle",
    "load_mcp_config",
    "save_mcp_servers",
    "mcp_client_manager",
    "logger",
]
