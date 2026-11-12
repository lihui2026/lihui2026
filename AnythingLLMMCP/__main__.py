"""AnythingLLM MCP 入口。

默认 stdio（由 MCP Host 拉起）；也可以独立以 Streamable HTTP 方式提供：

    python -m AnythingLLMMCP                          # stdio
    python -m AnythingLLMMCP --transport streamable-http --port 8091

端口与 Agent/office/.mcp.json 中的 http://127.0.0.1:8091/mcp 保持一致。
"""
from __future__ import annotations

import argparse

from .server import server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AnythingLLM MCP Server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="传输方式，默认 stdio",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 监听地址")
    parser.add_argument("--port", type=int, default=8091, help="HTTP 监听端口")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.transport == "streamable-http":
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            json_response=True,
            stateless_http=True,
        )
    else:
        server.run()


if __name__ == "__main__":
    main()
