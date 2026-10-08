"""用于创建插件及其测试文件的 LangChain 工具。"""

import ast
import builtins
import importlib.util
import keyword
import os
import re
import subprocess
import sys

from langchain.tools import tool

from config import Config

#: 插件元信息 PLUGIN_META 必须包含的字段
REQUIRED_META_KEYS = ("name", "description", "version")

#: 禁止用作插件名的保留名称 (与测试工具链或本项目模块冲突)
_RESERVED_NAMES = frozenset(
    {
        # 测试/打包工具链
        "pytest",
        "unittest",
        "doctest",
        "pip",
        "setuptools",
        "wheel",
        # 本项目模块与包
        "config",
        "tools",
        "registry",
        "agent",
        "main",
        "plugins",
        "plugin_tests",
        "workspace",
    }
)

#: 插件模块级允许出现的语句类型 (禁止导入期副作用)
_ALLOWED_TOP_LEVEL_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Assign,
    ast.AnnAssign,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Pass,
)

_IDENTIFIER_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\Z")

#: 测试输出返回给 agent 时的最大字符数 (截断保留末尾关键信息)
_MAX_OUTPUT_CHARS = 4000


def _module_exists(name: str) -> bool:
    """名称是否对应已存在的可导入模块 (标准库/第三方/项目模块)。"""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _is_valid_module_name(name: str) -> bool:
    """名称是否为合法的插件模块名。

    要求: 合法标识符、非关键字、非内置名、非保留名, 且不与标准库或
    已安装模块同名 (避免遮蔽)。
    """
    if not _IDENTIFIER_RE.fullmatch(name) or keyword.iskeyword(name):
        return False
    if name in _RESERVED_NAMES or name in dir(builtins):
        return False
    if name in sys.stdlib_module_names or _module_exists(name):
        return False
    return True


def _name_rejection_reason(name: str) -> str:
    """返回插件名被拒绝的原因 (用于错误提示)。"""
    if not _IDENTIFIER_RE.fullmatch(name) or keyword.iskeyword(name):
        return "必须是合法 Python 标识符且不能是关键字"
    if name in _RESERVED_NAMES:
        return "该名称为保留名, 与测试工具链或项目模块冲突"
    if name in dir(builtins):
        return "不能使用内置名"
    if name in sys.stdlib_module_names:
        return "不能与标准库模块同名"
    if _module_exists(name):
        return "不能与已安装模块同名, 以免遮蔽"
    return "名称不可用"


def _is_main_guard(node: ast.If) -> bool:
    """判断是否为 ``if __name__ == "__main__":`` 守卫。"""
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False

    left, right = test.left, test.comparators[0]

    def _is_name(n: ast.AST) -> bool:
        return isinstance(n, ast.Name) and n.id == "__name__"

    def _is_main(n: ast.AST) -> bool:
        return isinstance(n, ast.Constant) and n.value == "__main__"

    return (_is_name(left) and _is_main(right)) or (_is_name(right) and _is_main(left))


def _validate_no_import_side_effects(tree: ast.Module) -> None:
    """禁止插件在导入时执行代码 (防止安装依赖、写文件等危险副作用)。"""
    for node in tree.body:
        if isinstance(node, ast.Expr):
            # 仅允许模块文档字符串
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            raise ValueError("插件模块级不允许执行表达式 (禁止导入期副作用)")
        if isinstance(node, ast.If):
            if _is_main_guard(node):
                continue
            raise ValueError("插件模块级不允许条件执行, 请将逻辑放入 run()")
        if not isinstance(node, _ALLOWED_TOP_LEVEL_NODES):
            raise ValueError(
                f"插件模块级不允许 {type(node).__name__} 语句 (禁止导入期副作用)"
            )


def _validate_plugin_contract(code: str) -> None:
    """校验插件代码约定。

    - 必须定义模块级 PLUGIN_META 字典 (含必需字段) 与 run() 函数;
    - 模块级不允许导入期副作用 (如调用函数、安装依赖、写文件)。
    """
    tree = ast.parse(code)
    _validate_no_import_side_effects(tree)

    meta_value = None
    has_run = False

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            has_run = True
        elif isinstance(node, ast.Assign) and meta_value is None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLUGIN_META":
                    meta_value = node.value
                    break

    if meta_value is None:
        raise ValueError("插件代码必须定义模块级 PLUGIN_META 字典")
    if not has_run:
        raise ValueError("插件代码必须定义 run() 函数")

    # 若 PLUGIN_META 是字面量字典, 校验其包含必需字段
    if isinstance(meta_value, ast.Dict):
        keys = {
            key.value
            for key in meta_value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        missing = [key for key in REQUIRED_META_KEYS if key not in keys]
        if missing:
            raise ValueError(f"PLUGIN_META 缺少字段: {', '.join(missing)}")


@tool
def create_plugin(
    name: str, code: str, test_code: str, overwrite: bool = True
) -> str:
    """创建一个新插件及其测试文件; 重复使用同名插件时会幂等地更新。

    - name: 插件模块名; 必须是合法标识符, 且不能是关键字、内置名、保留名
      (如 pytest)、标准库或已安装模块名。
    - code: 插件源码; 必须定义模块级 PLUGIN_META 字典和 run() 函数,
      且模块级不得有导入期副作用 (如调用函数、安装依赖、写文件)。
    - test_code: 插件测试源码。
    - overwrite: 同名文件已存在且内容不同时是否覆盖, 默认 True。
      内容完全一致时直接返回, 不会报错; 设为 False 时已存在会报错 (严格模式)。
    """
    if not _is_valid_module_name(name):
        raise ValueError(f"非法插件名 {name!r}: {_name_rejection_reason(name)}")

    if not isinstance(code, str) or not code.strip():
        raise ValueError("插件代码不能为空")
    if not isinstance(test_code, str) or not test_code.strip():
        raise ValueError("测试代码不能为空")

    try:
        _validate_plugin_contract(code)
        ast.parse(test_code)
    except SyntaxError as exc:
        raise ValueError(f"代码存在语法错误: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"插件代码校验失败: {exc}") from exc

    plugins_dir = Config.PLUGINS_DIR
    tests_dir = Config.PLUGIN_TESTS_DIR
    plugins_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    plugin_file = plugins_dir / f"{name}.py"
    test_file = tests_dir / f"test_{name}.py"

    plugin_exists = plugin_file.exists()
    test_exists = test_file.exists()

    # 内容完全一致时幂等返回, 避免重复创建同一插件时报错
    if plugin_exists and test_exists:
        unchanged = (
            plugin_file.read_text(encoding="utf-8") == code
            and test_file.read_text(encoding="utf-8") == test_code
        )
        if unchanged:
            return f"插件已存在且内容一致, 无需重复创建:\n{plugin_file}\n{test_file}"

    if not overwrite and (plugin_exists or test_exists):
        existing = [str(p) for p in (plugin_file, test_file) if p.exists()]
        raise FileExistsError(
            "目标文件已存在, 如需覆盖请设置 overwrite=True: " + ", ".join(existing)
        )

    plugin_file.write_text(code, encoding="utf-8")
    test_file.write_text(test_code, encoding="utf-8")

    plugin_action = "已更新" if plugin_exists else "已创建"
    test_action = "已更新" if test_exists else "已创建"
    return f"插件{plugin_action}: {plugin_file}\n测试{test_action}: {test_file}"


@tool
def run_plugin_tests(name: str, timeout: int = 30) -> str:
    """运行指定插件的测试。

    - name: 插件模块名。
    - timeout: 测试超时秒数, 默认 30。
    """
    if not _is_valid_module_name(name):
        raise ValueError(f"非法插件名 {name!r}: {_name_rejection_reason(name)}")

    test_file = Config.PLUGIN_TESTS_DIR / f"test_{name}.py"
    if not test_file.exists():
        raise ValueError(f"测试文件不存在: {test_file}")

    # 确保项目根目录在导入路径上, 便于测试文件 import plugins.*
    # 同时加入项目根目录与插件目录, 便于测试文件 `import plugins.x` 或 `import x`
    env = dict(os.environ)
    paths = [str(Config.BASE_DIR), str(Config.PLUGINS_DIR)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Config.BASE_DIR),
            env=env,
        )
    except FileNotFoundError:
        return "无法运行测试: 未安装 pytest, 请先执行 pip install pytest"
    except subprocess.TimeoutExpired:
        return f"插件测试超时 (>{timeout}s)"

    output = (result.stdout + "\n" + result.stderr).strip()
    if len(output) > _MAX_OUTPUT_CHARS:
        output = output[-_MAX_OUTPUT_CHARS:]

    if result.returncode != 0:
        return f"插件测试失败 (exit code {result.returncode}):\n{output}"
    return f"插件测试通过:\n{output}"
