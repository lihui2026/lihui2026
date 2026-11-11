"""MCP 集成模块（兼容层）。

实现已迁移至 :mod:`core.mcp.mcp_client`（``McpClientManager``，
读取 office/.mcp.json，支持 streamable-http 协议），
本模块仅保留原有导入路径的兼容导出，方便现有代码继续
``from core.mcp import mcp_manager, save_mcp_servers``。
"""
from core.mcp.mcp_client import (
    MCPServerConfig,
    McpClientManager,
    load_mcp_config,
    mcp_client_manager,
    save_mcp_servers,
)

# 兼容旧代码的名称
MCPManager = McpClientManager
mcp_manager = mcp_client_manager

__all__ = [
    "MCPManager",
    "McpClientManager",
    "MCPServerConfig",
    "load_mcp_config",
    "save_mcp_servers",
    "mcp_client_manager",
    "mcp_manager",
]
