"""插件注册表。

从 ``Config.PLUGINS_DIR`` 中发现并加载插件模块, 校验插件契约,
维护插件记录, 并支持把插件转换为 LangChain 工具供 agent 调用。

插件契约:
- 模块级 ``PLUGIN_META`` 字典, 至少包含 name、description、version 字段;
- 可调用的 ``run()`` 函数。
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from langchain_core.tools import StructuredTool

from config import Config

#: PLUGIN_META 必须包含的字段
REQUIRED_META_KEYS = ("name", "description", "version")


class PluginError(Exception):
    """插件加载或契约校验失败。"""


@dataclass(frozen=True)
class PluginRecord:
    """一个已加载插件的不可变描述。"""

    #: 插件标识 (等于插件模块名, 与 create_plugin / run_plugin_tests 一致)
    name: str
    #: 插件描述 (来自 PLUGIN_META)
    description: str
    #: 插件版本 (来自 PLUGIN_META)
    version: str
    #: 插件源文件路径
    path: Path
    #: 已加载的插件模块
    module: ModuleType
    #: 插件的 run() 可调用对象
    run: Callable[..., Any]

    def as_tool(self) -> StructuredTool:
        """把插件的 ``run()`` 转换为 LangChain 工具。"""
        return StructuredTool.from_function(
            func=self.run,
            name=self.name,
            description=self.description or f"插件 {self.name}",
        )


class PluginRegistry:
    """插件注册表。

    负责发现、加载、校验并注册插件; 坏插件会被记录到 :meth:`errors`
    而不会中断其它插件的加载。
    """

    def __init__(self, plugins_dir: Path | str | None = None) -> None:
        self.plugins_dir = Path(plugins_dir) if plugins_dir else Config.PLUGINS_DIR
        self._records: dict[str, PluginRecord] = {}
        self._errors: dict[str, str] = {}

    # ---------- 加载 / 注册 ----------

    def load_all(self) -> PluginRegistry:
        """扫描插件目录并加载全部插件, 返回自身以便链式调用。"""
        self._records.clear()
        self._errors.clear()

        if not self.plugins_dir.is_dir():
            return self

        for path in sorted(self.plugins_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            self.load_file(path)

        return self

    def load_file(self, path: Path | str) -> PluginRecord | None:
        """加载单个插件文件。

        失败时记录错误并返回 ``None``, 不影响其它插件。
        """
        path = Path(path)
        try:
            module = self._import_module(path)
            record = self._build_record(module, path)
        except Exception as exc:  # noqa: BLE001 - 汇总任意加载错误
            self._errors[path.stem] = f"{type(exc).__name__}: {exc}"
            return None

        self.register(record)
        return record

    def register(self, record: PluginRecord) -> None:
        """注册一条插件记录 (同名会覆盖)。"""
        self._records[record.name] = record

    # ---------- 查询 / 调用 ----------

    def get(self, name: str) -> PluginRecord:
        """按名称获取插件记录, 不存在时抛出 ``KeyError``。"""
        try:
            return self._records[name]
        except KeyError:
            raise KeyError(f"未注册的插件: {name}") from None

    def has(self, name: str) -> bool:
        """插件是否已注册。"""
        return name in self._records

    def names(self) -> list[str]:
        """返回已注册插件名 (排序后)。"""
        return sorted(self._records)

    def records(self) -> list[PluginRecord]:
        """返回全部插件记录 (按名称排序)。"""
        return [self._records[name] for name in self.names()]

    def errors(self) -> dict[str, str]:
        """返回加载失败的插件: {模块名: 错误信息}。"""
        return dict(self._errors)

    def run(self, name: str, **kwargs: Any) -> Any:
        """调用指定插件的 ``run()`` 函数。"""
        return self.get(name).run(**kwargs)

    def as_tools(self) -> list[StructuredTool]:
        """把全部插件转换为 LangChain 工具列表。"""
        return [record.as_tool() for record in self.records()]

    # ---------- 内部实现 ----------

    def _import_module(self, path: Path) -> ModuleType:
        """按文件路径加载模块, 注册到 ``sys.modules`` 以支持相对导入。"""
        module_name = f"{self.plugins_dir.name}.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise PluginError(f"无法为 {path} 创建模块 spec")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return module

    def _build_record(self, module: ModuleType, path: Path) -> PluginRecord:
        """校验插件契约并构建插件记录。"""
        meta = getattr(module, "PLUGIN_META", None)
        if not isinstance(meta, dict):
            raise PluginError("缺少模块级 PLUGIN_META 字典")

        missing = [key for key in REQUIRED_META_KEYS if key not in meta]
        if missing:
            raise PluginError(f"PLUGIN_META 缺少字段: {', '.join(missing)}")

        run = getattr(module, "run", None)
        if not callable(run):
            raise PluginError("缺少可调用的 run() 函数")

        return PluginRecord(
            name=path.stem,
            description=str(meta.get("description", "")),
            version=str(meta.get("version", "")),
            path=path,
            module=module,
            run=run,
        )

    # ---------- 容器协议 ----------

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._records

    def __iter__(self):
        return iter(self.records())

    def __len__(self) -> int:
        return len(self._records)

    def __repr__(self) -> str:
        return f"PluginRegistry(plugins={self.names()}, errors={list(self._errors)})"


def load_registry(plugins_dir: Path | str | None = None) -> PluginRegistry:
    """创建并加载插件注册表。"""
    return PluginRegistry(plugins_dir).load_all()
