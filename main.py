"""self-extension agent 入口。

负责实际创建 agent 并调用: 读取用户命令, 交给 agent 执行,
并维护多轮对话上下文。
"""

import sys

from langchain_core.messages import HumanMessage

from agent import Agent


def _extract_final_text(result: dict) -> str:
    """从 agent 返回结果中提取最后一条 AI 消息的文本。"""
    messages = result.get("messages", [])
    if not messages:
        return "(无输出)"

    last = messages[-1]
    content = getattr(last, "content", last)

    # 多模态内容为列表时, 拼接其中的文本片段
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text", ""))
            else:
                parts.append(str(part))
        return "".join(parts)

    return str(content)


def _run_once(agent: Agent, user_input: str, messages: list) -> list:
    """执行一轮对话, 打印回复, 返回更新后的消息历史。"""
    messages.append(HumanMessage(content=user_input))
    result = agent.agent.invoke({"messages": messages})
    print(_extract_final_text(result))
    print()
    return list(result.get("messages", messages))


def repl(agent: Agent) -> None:
    """交互式命令行循环。"""
    print("self-extension agent 已启动, 输入命令 (exit/quit 退出):")
    messages: list = []

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            break

        try:
            messages = _run_once(agent, user_input, messages)
        except Exception as exc:  # noqa: BLE001 - 保持 REPL 持续运行
            print(f"执行失败: {exc}\n")


def main() -> None:
    """程序入口。"""
    try:
        agent = Agent()
    except ValueError as exc:
        print(f"agent 初始化失败: {exc}")
        sys.exit(1)

    # 支持一次性命令: python main.py "你的命令"
    if len(sys.argv) > 1:
        _run_once(agent, " ".join(sys.argv[1:]), [])
        return

    repl(agent)


if __name__ == "__main__":
    main()
