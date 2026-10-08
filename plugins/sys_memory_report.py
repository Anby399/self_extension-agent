"""跨平台本机内存使用情况查询插件 (仅依赖标准库)。"""

import ctypes
import os
import platform
import re
import subprocess

PLUGIN_META = {
    "name": "sys_memory_report",
    "description": "跨平台查询本机内存使用情况 (总量/已用/可用/使用率) 与交换分区信息",
    "version": "1.0.0",
}

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def _human(size):
    """把字节数格式化成易读字符串。"""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "未知"
    for unit in _UNITS:
        if abs(value) < 1024.0 or unit == _UNITS[-1]:
            return "%.2f %s" % (value, unit)
        value /= 1024.0


def _parse_size(text):
    """解析 '2048.00M' / '1.5G' 这类带单位的容量字符串为字节数。"""
    text = str(text).strip()
    match = re.match(r"^([\d.]+)\s*([KMGTP]?)B?$", text, re.IGNORECASE)
    if not match:
        return 0
    number = float(match.group(1))
    prefix = match.group(2).upper()
    power = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5}[prefix]
    return int(number * (1024 ** power))


def _build(total, used, available, swap_total=0, swap_free=0, source="", extra=None):
    """组装统一的结果结构。"""
    used = max(int(used), 0)
    total = max(int(total), 0)
    available = max(int(available), 0)
    swap_total = max(int(swap_total), 0)
    swap_used = max(swap_total - int(swap_free), 0)

    used_percent = (used / total * 100.0) if total else 0.0
    swap_percent = (swap_used / swap_total * 100.0) if swap_total else 0.0

    result = {
        "success": True,
        "platform": platform.platform(),
        "source": source,
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "free_bytes": available,
        "used_percent": round(used_percent, 2),
        "swap_total_bytes": swap_total,
        "swap_used_bytes": swap_used,
        "swap_used_percent": round(swap_percent, 2),
        "total_human": _human(total),
        "used_human": _human(used),
        "available_human": _human(available),
        "swap_total_human": _human(swap_total),
        "swap_used_human": _human(swap_used),
        "used_percent_text": "%.1f%%" % used_percent,
        "swap_used_percent_text": "%.1f%%" % swap_percent,
    }
    if extra:
        result.update(extra)

    result["summary"] = (
        "内存总量 %s, 已用 %s (%s), 可用 %s; 交换分区 %s / %s (%.1f%%)。"
        % (
            result["total_human"],
            result["used_human"],
            result["used_percent_text"],
            result["available_human"],
            result["swap_used_human"],
            result["swap_total_human"],
            swap_percent,
        )
    )
    return result


def _cgroup_info():
    """读取 cgroup v2/v1 内存限制, 在容器环境下更贴近实际可用量。"""
    info = {}
    candidates = (
        ("v2_limit", "/sys/fs/cgroup/memory.max", "v2_current", "/sys/fs/cgroup/memory.current"),
        (
            "v1_limit",
            "/sys/fs/cgroup/memory/memory.limit_in_bytes",
            "v1_current",
            "/sys/fs/cgroup/memory/memory.usage_in_bytes",
        ),
    )
    for limit_key, limit_path, current_key, current_path in candidates:
        try:
            with open(limit_path, "r", encoding="utf-8", errors="ignore") as handle:
                raw_limit = handle.read().strip()
            if not raw_limit or raw_limit == "max":
                continue
            limit = int(raw_limit)
            if limit <= 0 or limit >= (1 << 60):
                continue
            with open(current_path, "r", encoding="utf-8", errors="ignore") as handle:
                current = int(handle.read().strip())
        except (OSError, ValueError):
            continue
        info["cgroup_limit_bytes"] = limit
        info["cgroup_current_bytes"] = current
        info["cgroup_limit_human"] = _human(limit)
        info["cgroup_used_percent"] = round(current / limit * 100.0, 2) if limit else 0.0
        return info
    return {}


def _linux_memory():
    with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as handle:
        text = handle.read()

    values = {}
    for line in text.splitlines():
        match = re.match(r"^(\w+):\s+(\d+)\s*kB", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable")
    if available is None:
        available = (
            values.get("MemFree", 0)
            + values.get("Buffers", 0)
            + values.get("Cached", 0)
        )
    used = total - available
    extra = {"cached_bytes": values.get("Cached", 0), "buffers_bytes": values.get("Buffers", 0)}
    extra.update(_cgroup_info())
    return _build(
        total,
        used,
        available,
        swap_total=values.get("SwapTotal", 0),
        swap_free=values.get("SwapFree", 0),
        source="/proc/meminfo",
        extra=extra,
    )


def _run_command(args):
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=True,
    ).stdout.decode("utf-8", errors="ignore")


def _darwin_memory():
    total = int(_run_command(["sysctl", "-n", "hw.memsize"]).strip())
    try:
        page_size = int(_run_command(["sysctl", "-n", "hw.pagesize"]).strip())
    except (subprocess.SubprocessError, ValueError):
        page_size = 4096

    vm_stat = _run_command(["vm_stat"])
    pages = {}
    for line in vm_stat.splitlines():
        match = re.match(r"^(.+?):\s+(\d+)\.?", line)
        if match:
            pages[match.group(1).strip()] = int(match.group(2))

    active = pages.get("Pages active", 0)
    wired = pages.get("Pages wired down", 0)
    compressed = pages.get("Pages occupied by compressor", 0)
    used = (active + wired + compressed) * page_size
    available = max(total - used, 0)

    swap_total = swap_free = 0
    try:
        swap_text = _run_command(["sysctl", "-n", "vm.swapusage"])
        total_match = re.search(r"total\s*=\s*([\d.]+[KMGTP]?)", swap_text)
        free_match = re.search(r"free\s*=\s*([\d.]+[KMGTP]?)", swap_text)
        if total_match:
            swap_total = _parse_size(total_match.group(1))
        if free_match:
            swap_free = _parse_size(free_match.group(1))
    except (subprocess.SubprocessError, ValueError):
        pass

    return _build(
        total,
        used,
        available,
        swap_total=swap_total,
        swap_free=swap_free,
        source="sysctl/vm_stat",
    )


def _windows_memory():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx 调用失败")

    total = int(status.ullTotalPhys)
    available = int(status.ullAvailPhys)
    used = total - available
    return _build(
        total,
        used,
        available,
        swap_total=int(status.ullTotalPageFile),
        swap_free=int(status.ullAvailPageFile),
        source="GlobalMemoryStatusEx",
        extra={"memory_load_percent": int(status.dwMemoryLoad)},
    )


def run(**kwargs):
    """查询本机内存使用情况, 返回结构化字典 (含 summary 文本)。"""
    system = platform.system().lower()
    try:
        if system == "linux":
            return _linux_memory()
        if system == "darwin":
            return _darwin_memory()
        if system == "windows":
            return _windows_memory()
        if os.path.exists("/proc/meminfo"):
            return _linux_memory()
        return {
            "success": False,
            "error": "暂不支持的操作系统: %s" % platform.system(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": "内存信息读取失败: %s: %s" % (type(exc).__name__, exc),
        }
