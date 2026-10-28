import configparser
import json
import os
import sys

try:
    import requests
except ImportError:
    print("缺少 requests，请先安装：pip install requests")
    sys.exit(1)

from tools import TOOLS, call_tool

MAX_TOOL_ROUNDS = 5
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(path=None):
    """读取 LLM 配置，默认读取脚本同目录下的 config.ini。"""
    cfg = configparser.ConfigParser()
    cfg.read(path or os.path.join(BASE_DIR, "config.ini"), encoding="utf-8-sig")

    llm = cfg["LLM"]
    return {
        "base_url": llm.get("base_url", "").rstrip("/"),
        "model": llm.get("model", ""),
        "api_key": llm.get("api_key", ""),
    }


def build_payload(cfg, messages):
    return {
        "model": cfg["model"],
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }


def request_completion(cfg, messages):
    """调用 /chat/completions，返回完整响应体。"""
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, json=build_payload(cfg, messages), timeout=120)
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM 接口返回 {resp.status_code}：{resp.text}")
    return resp.json()


def run_tool_calls(messages, message):
    """执行模型请求调用的工具，并把工具结果追加到 messages。"""
    tool_calls = message.get("tool_calls") or []
    messages.append({
        "role": "assistant",
        "content": message.get("content") or "",
        "tool_calls": tool_calls
    })

    for call in tool_calls:
        fn = call.get("function") or {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            args = {}

        print(f"→ 调用工具 {name}，参数：{args}")
        result = call_tool(name, args)
        print(f"← 工具返回：{result}")

        messages.append({
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "name": name,
            "content": result
        })


def run_once(cfg, messages, user_input):
    """一轮对话：必要时先执行工具，再输出模型的最终回答。"""
    messages.append({"role": "user", "content": user_input})

    for _ in range(MAX_TOOL_ROUNDS):
        result = request_completion(cfg, messages)
        choices = result.get("choices") or []
        if not choices:
            print("模型没有返回任何结果。")
            return

        message = choices[0].get("message") or {}
        if not message.get("tool_calls"):
            print(message.get("content") or "")
            return

        run_tool_calls(messages, message)

    print("（工具调用轮次过多，已中止。）")


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    messages = []

    print("已注册工具：getDate（通过调用本地 date 命令获取日期与时间）")
    while True:
        try:
            user_input = input("输入问题：")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input.strip():
            continue

        try:
            run_once(cfg, messages, user_input)
        except requests.RequestException as exc:
            print(f"\n请求失败：{exc}")
        except Exception as exc:
            print(f"\n错误：{exc}")
        print()


if __name__ == "__main__":
    main()
