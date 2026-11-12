"""测试用：起两个 streamable-http MCP Server（含同名工具 query_data）。"""
import threading

import uvicorn
from mcp.server.mcpserver import MCPServer


def build(name, greeting):
    mcp = MCPServer(name)

    @mcp.tool()
    def query_data(keyword: str) -> str:
        """按关键词查询数据。"""
        return f"[{name}] query_data({keyword}) -> 命中 3 条记录"

    @mcp.tool()
    def greet(who: str) -> str:
        """打个招呼。"""
        return f"{greeting}, {who}!"

    return mcp


def run(mcp, port):
    app = mcp.streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    t1 = threading.Thread(target=run, args=(build("TestA", "Hello"), 9990), daemon=True)
    t2 = threading.Thread(target=run, args=(build("TestB", "你好"), 9991), daemon=True)
    t1.start()
    t2.start()
    print("READY: http://127.0.0.1:9990/mcp and http://127.0.0.1:9991/mcp", flush=True)
    while True:
        pass
