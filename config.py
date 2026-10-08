"""项目配置模块。

集中管理 self-extension agent 的目录路径、模型与提示词配置,
其他模块通过 ``from config import Config`` 获取统一的配置。
"""

import os
from pathlib import Path


class Config:
    """self-extension agent 的全局配置。

    所有路径均为绝对路径, 基于项目根目录解析;
    模型与提示词配置优先读取环境变量, 并提供合理的默认值。
    """

    # ---------- 路径配置 ----------

    #: 项目根目录 (config.py 所在目录)
    BASE_DIR: Path = Path(__file__).resolve().parent

    #: 插件目录, 存放 self-extension 的插件模块
    PLUGINS_DIR: Path = BASE_DIR / "plugins"

    #: 插件测试目录, 存放插件的测试文件
    PLUGIN_TESTS_DIR: Path = BASE_DIR / "plugin_tests"

    #: 工作空间目录, 存放 agent 运行过程中生成的临时/中间产物
    WORKSPACE_DIR: Path = BASE_DIR / "workspace"

    # ---------- 模型配置 ----------

    #: 默认 LLM 模型
    MODEL: str = os.getenv("SELF_EXTENSION_MODEL", "deepseek-flash")

    #: LLM 的 OpenAI 兼容接口地址 (DeepSeek 官方地址)
    MODEL_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    #: LLM API Key (优先 DEEPSEEK_API_KEY, 回退 OPENAI_API_KEY)
    MODEL_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))

    # ---------- 提示词配置 ----------

    #: agent 系统提示词
    SYSTEM_PROMPT: str = """\
你是 self-extension 智能体, 核心职责是执行用户提出的命令, 并在能力不足时自动扩展自己。

工作原则:
1. 优先执行用户的命令, 使用已有工具直接完成任务。
2. 若当前缺少完成任务所需的插件 (能力缺失), 自动创建缺失的插件:
   - 编写插件源码, 必须定义模块级 PLUGIN_META 字典
     (包含 name、description、version 字段) 和 run() 函数;
   - 编写对应的测试代码;
   - 调用 create_plugin 工具创建插件文件与测试文件;
   - 调用 run_plugin_tests 工具运行测试, 失败则根据输出修复后重新创建并重试;
   - 测试通过后, 使用新插件继续完成用户的任务。

约束:
- 所有路径由 config.Config 统一管理, 不要硬编码路径。
- 插件名必须是合法的 Python 模块名, 且不得使用保留名, 尤其禁止使用
  pytest、unittest、pip、setuptools、config、tools、registry、agent、main、
  plugins 等名称, 也不得与标准库或已安装模块同名。
- 插件只提供完成用户任务的业务能力, 模块级不得有导入期副作用:
  禁止调用函数、安装依赖 (如 pip install)、写文件或修改运行环境。
- 禁止创建测试框架/工具链的替代品 (如 pytest 兼容层) 或自举安装脚本;
  若运行测试所需依赖缺失, 应如实告知用户, 而不是自行创建或安装。
"""
