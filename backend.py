"""self-extension agent 的 Flask 后端。

接口:
- ``GET  /``           返回前端 HTML 页面
- ``GET  /api/health`` 健康检查 (返回当前模型等)
- ``POST /api/chat``   请求体 ``{"message": "..."}``, 调用 agent 并返回 ``{"reply": "..."}``
- ``POST /api/reset``  清空对话历史
"""

import threading

from flask import Flask, jsonify, request
from langchain_core.messages import HumanMessage

from agent import Agent
from config import Config
from frontend import HTML_PAGE

app = Flask(__name__)

#: 单用户会话, 用锁串行化对 agent 的调用
_lock = threading.Lock()
_agent: Agent | None = None
_history: list = []


def _get_agent() -> Agent:
    """惰性构建 agent (首次请求时初始化模型与插件工具)。"""
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


def _extract_text(result: dict) -> str:
    """从 agent 返回结果中提取最后一条 AI 消息的文本。"""
    messages = result.get("messages", [])
    if not messages:
        return "(无输出)"
    content = getattr(messages[-1], "content", messages[-1])
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


@app.get("/")
def index():
    """返回前端页面。"""
    return HTML_PAGE


@app.get("/api/health")
def health():
    """健康检查。"""
    return jsonify({"status": "ok", "model": Config.MODEL})


@app.post("/api/chat")
def chat():
    """接收用户指令, 调用 agent, 返回回复。"""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message 不能为空"}), 400

    try:
        with _lock:
            agent = _get_agent()
            _history.append(HumanMessage(content=message))
            result = agent.agent.invoke({"messages": list(_history)})
            _history[:] = result.get("messages", _history)
            reply = _extract_text(result)
    except Exception as exc:  # noqa: BLE001 - 统一转为 JSON 错误
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    return jsonify({"reply": reply})


@app.post("/api/reset")
def reset():
    """清空对话历史。"""
    with _lock:
        _history.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
