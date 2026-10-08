"""self-extension agent 构建模块。

基于 LangChain 的 ``create_agent`` 组装一个能够创建插件并运行其测试的 agent。
本模块只负责构建 agent, 不负责调用 (调用逻辑由外部入口实现)。
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Config
from registry import load_registry
from tools.create_plugin import create_plugin, run_plugin_tests

#: 内置工具 (创建插件 / 运行插件测试)
TOOLS = [create_plugin, run_plugin_tests]


def _load_tools() -> list:
    """内置工具 + 已注册的插件工具。"""
    return [*TOOLS, *load_registry().as_tools()]


def _build_model() -> ChatOpenAI:
    """按 Config 配置构建 LLM 模型实例。"""
    if not Config.MODEL_API_KEY:
        raise ValueError(
            "未配置模型 API Key, 请设置环境变量 DEEPSEEK_API_KEY "
            "(或 OPENAI_API_KEY) 后重试"
        )
    return ChatOpenAI(
        model_name=Config.MODEL, # type: ignore
        openai_api_base=Config.MODEL_BASE_URL, # type: ignore
        openai_api_key=Config.MODEL_API_KEY, # type: ignore
        temperature=0,
    )


class Agent:
    """self-extension agent。

    封装标准创建流程: 组装模型、工具与系统提示词, 并构建可执行的
    LangChain agent graph (结果存储在 ``self.agent``)。
    """

    def __init__(
        self,
        model: ChatOpenAI | None = None,
        tools: list | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model or _build_model()
        self.tools = list(tools) if tools is not None else _load_tools()
        self.system_prompt = system_prompt or Config.SYSTEM_PROMPT
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.system_prompt,
        )
