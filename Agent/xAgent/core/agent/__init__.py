"""Agent core logic separated from UI."""
import json
from typing import Any, Dict, List

from core.llm import LLMClient
from core.tools import call_tool
from core.utils import getDate as _getDate
from core.skills import skill_manager


MAX_TOOL_ROUNDS = 5


class Agent:
    def __init__(self, cfg, client: LLMClient | None = None):
        self.cfg = cfg
        self.client = client or LLMClient(cfg)
        self.messages: List[Dict[str, Any]] = [{"role": "system", "content": self.build_system_prompt()}]

    def build_system_prompt(self) -> str:
        base = (
            "你是一个本地文件操作助手。当前电脑的日期与时间是 "
            f"{_getDate()}。\n"
            "你可以使用以下工具：getCurrentWorkingDirectory、listDirectory、getFileType、"
            "getFileContent、createFile、editFileContent、createDirectory、"
            "removeDirectory、deleteFile、renamePath、getDate、isLeapYear、fetchWeb、searchWeb、RunCli、loadSkill、createSkill。\n"
            "对于文件内容操作，仅支持纯文本格式文件。\n"
            "当用户要求创建新的 Skill 时，请调用 createSkill 工具；若还需创建 references/、scripts/ 等附加目录或文件，"
            "请在创建 Skill 后继续使用 createFile、createDirectory 等文件工具完成。\n"
            "当需要运行本地命令行程序时，请使用 RunCli 工具，并通过 command 和 args 分别传入程序名和参数列表。\n"
            "当需要获取网页主要内容时，请使用 fetchWeb 工具；当需要获取互联网上的最新信息时，请使用 searchWeb 工具。\n"
            "当需要操作本地文件时，请先调用合适的工具获取必要信息再执行后续操作。\n"
        )
        skills_info = skill_manager.get_skills_info()
        if skills_info:
            skills_text = "\nYou have access to the following skills:\n\n"
            for s in skills_info:
                skills_text += f"- `{s['name']}`: {s['description']}\n"
            skills_text += "\nUse the `loadSkill` tool to load the full instructions of a skill when needed. You can also load additional files referenced by a skill.\n"
            base += skills_text
        else:
            base += "\nYou have access to the following skills:\n\n（无）\n\nUse the `loadSkill` tool to load the full instructions of a skill when needed. You can also load additional files referenced by a skill.\n"
        return base

    def run_tool_calls(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        tool_calls = message.get("tool_calls") or []
        results = []
        self.messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        })
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            result = call_tool(name, args)
            results.append({"tool": name, "args": args, "result": result})
            self.messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": name,
                "content": result,
            })
        return results

    def process(self, user_input: str):
        self.messages.append({"role": "user", "content": user_input})
        for _ in range(MAX_TOOL_ROUNDS):
            result = self.client.chat(self.messages)
            choices = result.get("choices") or []
            if not choices:
                yield {"type": "error", "content": "模型没有返回任何结果"}
                return
            message = choices[0].get("message") or {}
            if not message.get("tool_calls"):
                yield {"type": "thought", "content": message.get("content") or ""}
                return
            tool_results = self.run_tool_calls(message)
            for tr in tool_results:
                yield {"type": "tool_call", "tool": tr["tool"], "args": tr["args"], "result": tr["result"]}
        yield {"type": "error", "content": "（工具调用轮次过多，已中止。）"}
