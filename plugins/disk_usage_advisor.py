"""磁盘占用分析与释放空间建议插件 (仅依赖标准库)。

功能:
- 统计各磁盘剩余空间;
- 扫描指定目录, 按类别归集可清理的缓存/临时文件占用;
- 找出最大的文件、长期未修改的文件、内容重复的文件;
- 汇总可释放空间并给出优化建议。
"""

import hashlib
import os
import shutil
import stat as statmod
import string
import time
from collections import defaultdict

PLUGIN_META = {
    "name": "disk_usage_advisor",
    "description": "扫描磁盘占用, 识别大文件/陈旧文件/重复文件与可清理缓存, 输出释放空间指南",
    "version": "1.0.0",
}

UNITS = ("B", "KB", "MB", "GB", "TB", "PB")

SKIP_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "$winreagent",
    "config.msi",
    "recovery",
    "application data",
    "history",
    "temporary internet files",
}

REPARSE_FLAG = getattr(statmod, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

CATEGORY_ORDER = [
    "临时文件",
    "浏览器/应用缓存",
    "开发工具缓存",
    "Python 缓存",
    "Node.js 依赖缓存",
    "Windows 更新缓存",
    "Windows 系统组件",
    "回收站",
    "云盘同步目录",
    "普通文件",
]

CATEGORY_ADVICE = {
    "临时文件": "直接清空 %TEMP% 与 C:\\Windows\\Temp 下的内容, 正在使用的文件会自动跳过。",
    "浏览器/应用缓存": "清缓存不会丢书签和密码, 建议定期在浏览器里执行\"清除缓存\"。",
    "开发工具缓存": "pip / npm / gradle / maven 缓存可安全删除, 只是下次装包会重新下载。",
    "Python 缓存": "__pycache__ 与 .pytest_cache 可全部删除, 由解释器自动重建。",
    "Node.js 依赖缓存": "node_modules 可删除后用 npm install 重建, 长期不碰的老项目优先处理。",
    "Windows 更新缓存": "可用系统自带的\"磁盘清理\"清理 Windows 更新缓存, 建议保留工具操作。",
    "Windows 系统组件": "属于系统目录, 不要手工删除, 请使用磁盘清理或 DISM 组件清理。",
    "回收站": "确认无需恢复后清空回收站即可立即释放空间。",
    "云盘同步目录": "可利用云盘的\"按需下载/文件随取\"功能, 释放本地副本。",
    "普通文件": "按修改时间与体积排序, 归档或转移不常用的资料到外部存储。",
}


def _human(size):
    """字节数格式化为易读字符串。"""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "未知"
    if value < 0:
        value = 0.0
    for unit in UNITS:
        if abs(value) < 1024.0 or unit == UNITS[-1]:
            return "%.2f %s" % (value, unit)
        value /= 1024.0


def _categorize(path):
    """根据路径判断文件所属的可清理类别。"""
    normalized = path.replace("/", "\\")
    lowered = normalized.lower()
    parts = lowered.split("\\")

    if "$recycle.bin" in parts or "recycler" in parts:
        return "回收站"
    if "temp" in parts or lowered.rstrip("\\").endswith("\\temp"):
        return "临时文件"
    if "node_modules" in parts:
        return "Node.js 依赖缓存"
    if "__pycache__" in parts or ".pytest_cache" in parts or ".mypy_cache" in parts:
        return "Python 缓存"
    if "softwaredistribution" in parts and "download" in parts:
        return "Windows 更新缓存"
    if any(
        key in lowered
        for key in ("\\cache\\", "\\cache2\\", "code cache", "gpucache", "service worker")
    ):
        return "浏览器/应用缓存"
    if any(
        key in lowered
        for key in (
            "\\pip\\cache",
            "\\npm-cache",
            "\\yarn\\cache",
            "\\.gradle\\",
            "\\.m2\\",
            "\\.nuget\\",
            "\\.cargo\\registry",
            "\\go\\pkg\\mod",
            "\\yarn\\berry",
        )
    ):
        return "开发工具缓存"
    if any(key in lowered for key in ("\\windows\\installer", "\\windows\\winsxs")):
        return "Windows 系统组件"
    if any(key in lowered for key in ("\\onedrive", "\\dropbox", "\\google 云端硬盘")):
        return "云盘同步目录"
    return "普通文件"


def _drives():
    """列出所有存在的盘符及其容量使用情况。"""
    result = []
    for letter in string.ascii_uppercase:
        root = "%s:\\" % letter
        try:
            if not os.path.exists(root):
                continue
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        free_percent = (usage.free / usage.total * 100.0) if usage.total else 0.0
        result.append(
            {
                "drive": root,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "total_human": _human(usage.total),
                "used_human": _human(usage.used),
                "free_human": _human(usage.free),
                "free_percent": round(free_percent, 1),
            }
        )
    return result


def _scan(roots, deadline, max_files):
    """遍历目录收集文件元信息, 受时间与数量预算约束。"""
    counters = {"files": 0, "bytes": 0, "errors": 0, "truncated": False}
    records = []
    stack = [os.path.abspath(root) for root in roots if os.path.isdir(root)]
    stop = False

    while stack and not stop:
        if time.monotonic() > deadline or counters["files"] >= max_files:
            counters["truncated"] = True
            break
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                for entry in iterator:
                    if time.monotonic() > deadline or counters["files"] >= max_files:
                        counters["truncated"] = True
                        stop = True
                        break
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        counters["errors"] += 1
                        continue
                    attributes = getattr(info, "st_file_attributes", 0)
                    if attributes and attributes & REPARSE_FLAG:
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        if entry.name.lower() in SKIP_DIR_NAMES:
                            continue
                        stack.append(entry.path)
                    else:
                        records.append(
                            {
                                "path": entry.path,
                                "size": info.st_size,
                                "mtime": info.st_mtime,
                                "atime": info.st_atime,
                                "category": _categorize(entry.path),
                            }
                        )
                        counters["files"] += 1
                        counters["bytes"] += info.st_size
        except OSError:
            counters["errors"] += 1
            continue
    return records, counters


def _hash_file(path, limit=0):
    """计算文件哈希; limit 大于 0 时只读取前若干字节作为采样指纹。"""
    digest = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as handle:
        if limit:
            digest.update(handle.read(limit))
        else:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if not chunk:
                    break
                digest.update(chunk)
    return digest.hexdigest()


def _find_duplicates(records, min_size, deadline, max_files=20000):
    """按 (大小, 采样哈希, 完整哈希) 三级比对找出重复文件组。"""
    by_size = defaultdict(list)
    for item in records:
        if item["size"] >= min_size:
            by_size[item["size"]].append(item)

    groups = []
    hashed = 0
    for size, items in by_size.items():
        if len(items) < 2 or time.monotonic() > deadline:
            continue
        by_sample = defaultdict(list)
        for item in items:
            if hashed >= max_files or time.monotonic() > deadline:
                break
            try:
                item["_sample"] = _hash_file(item["path"], limit=65536)
            except OSError:
                continue
            hashed += 1
            by_sample[item["_sample"]].append(item)

        for sample_items in by_sample.values():
            if len(sample_items) < 2:
                continue
            by_full = defaultdict(list)
            for item in sample_items:
                if time.monotonic() > deadline:
                    break
                try:
                    item["_full"] = _hash_file(item["path"])
                except OSError:
                    continue
                by_full[item["_full"]].append(item)
            for full_items in by_full.values():
                if len(full_items) >= 2:
                    paths = sorted(entry["path"] for entry in full_items)
                    groups.append(
                        {
                            "size": size,
                            "count": len(full_items),
                            "reclaimable": size * (len(full_items) - 1),
                            "paths": paths,
                        }
                    )

    groups.sort(key=lambda item: item["reclaimable"], reverse=True)
    for item in records:
        item.pop("_sample", None)
        item.pop("_full", None)
    return groups


def _build_suggestions(categories, large_files, old_files, duplicates, reclaimable):
    """根据扫描结果生成人类可读的优化建议。"""
    suggestions = []
    for name in CATEGORY_ORDER:
        if name == "普通文件" or name not in categories:
            continue
        info = categories[name]
        if info["size"] < 10 * 1024 * 1024:
            continue
        suggestions.append(
            "%s 占用 %s (%d 个文件)。%s"
            % (name, _human(info["size"]), info["files"], CATEGORY_ADVICE.get(name, ""))
        )

    if duplicates:
        suggestions.append(
            "发现 %d 组内容完全相同的文件, 每组只保留一份可释放 %s。"
            % (len(duplicates), _human(reclaimable))
        )
    if old_files:
        suggestions.append(
            "有 %d 个较大文件超过 6 个月未修改, 建议归档或删除, 合计 %s。"
            % (len(old_files), _human(sum(item["size"] for item in old_files)))
        )
    if large_files:
        suggestions.append(
            "体积最大的 %d 个文件合计 %s, 优先确认它们是否还需要保留。"
            % (len(large_files), _human(sum(item["size"] for item in large_files)))
        )
    if not suggestions:
        suggestions.append("本次扫描范围内未发现明显的空间浪费点。")
    return suggestions


def run(
    roots=None,
    old_days=180,
    old_min_mb=20,
    large_min_mb=100,
    duplicate_min_mb=1,
    top=12,
    time_budget=45,
    max_files=300000,
    **kwargs
):
    """扫描磁盘并返回结构化分析结果 (含 report 文本与建议)。"""
    started = time.monotonic()
    deadline = started + float(time_budget)

    if not roots:
        home = os.path.expanduser("~")
        roots = [home]
        for key in ("TEMP", "TMP"):
            temp_dir = os.environ.get(key)
            if temp_dir and os.path.isdir(temp_dir):
                if all(os.path.abspath(temp_dir) != os.path.abspath(r) for r in roots):
                    roots.append(temp_dir)
                break

    try:
        records, counters = _scan(roots, deadline, int(max_files))

        categories = {}
        for item in records:
            bucket = categories.setdefault(item["category"], {"size": 0, "files": 0})
            bucket["size"] += item["size"]
            bucket["files"] += 1

        now = time.time()
        old_threshold = now - float(old_days) * 86400
        old_bytes = float(old_min_mb) * 1024 ** 2
        large_bytes = float(large_min_mb) * 1024 ** 2

        large_files = sorted(
            (item for item in records if item["size"] >= large_bytes),
            key=lambda item: item["size"],
            reverse=True,
        )[: int(top)]

        old_files = sorted(
            (
                item
                for item in records
                if item["size"] >= old_bytes and item["mtime"] < old_threshold
            ),
            key=lambda item: item["size"],
            reverse=True,
        )[: int(top)]

        duplicates = _find_duplicates(
            records, float(duplicate_min_mb) * 1024 ** 2, deadline
        )[: int(top)]

        reclaimable = sum(item["reclaimable"] for item in duplicates)
        suggestions = _build_suggestions(
            categories, large_files, old_files, duplicates, reclaimable
        )

        category_list = []
        for name in CATEGORY_ORDER:
            if name in categories and categories[name]["size"] > 0:
                info = categories[name]
                category_list.append(
                    {
                        "name": name,
                        "size_bytes": info["size"],
                        "size_human": _human(info["size"]),
                        "files": info["files"],
                    }
                )
        for name, info in categories.items():
            if name not in CATEGORY_ORDER and info["size"] > 0:
                category_list.append(
                    {
                        "name": name,
                        "size_bytes": info["size"],
                        "size_human": _human(info["size"]),
                        "files": info["files"],
                    }
                )
        category_list.sort(key=lambda item: item["size_bytes"], reverse=True)

        drives = _drives()
        elapsed = time.monotonic() - started

        report_lines = []
        report_lines.append("扫描目录: %s" % ", ".join(roots))
        report_lines.append(
            "扫描文件 %d 个, 合计 %s, 耗时 %.1fs%s"
            % (
                counters["files"],
                _human(counters["bytes"]),
                elapsed,
                " (已截断, 结果不完整)" if counters["truncated"] else "",
            )
        )
        for drive in drives:
            report_lines.append(
                "磁盘 %s 总 %s, 已用 %s, 剩余 %s (%.1f%%)"
                % (
                    drive["drive"],
                    drive["total_human"],
                    drive["used_human"],
                    drive["free_human"],
                    drive["free_percent"],
                )
            )
        report_lines.append("--- 按类别占用 ---")
        for item in category_list:
            report_lines.append(
                "%-14s %10s  (%d 个文件)"
                % (item["name"], item["size_human"], item["files"])
            )
        report_lines.append("--- 最大文件 ---")
        for item in large_files:
            report_lines.append(
                "%10s  %s  %s"
                % (
                    _human(item["size"]),
                    time.strftime("%Y-%m-%d", time.localtime(item["mtime"])),
                    item["path"],
                )
            )
        report_lines.append("--- 长期未修改的大文件 ---")
        for item in old_files:
            report_lines.append(
                "%10s  %s  %s"
                % (
                    _human(item["size"]),
                    time.strftime("%Y-%m-%d", time.localtime(item["mtime"])),
                    item["path"],
                )
            )
        report_lines.append("--- 重复文件组 ---")
        for group in duplicates:
            report_lines.append(
                "%10s x%d  可释放 %s  首份: %s"
                % (
                    _human(group["size"]),
                    group["count"],
                    _human(group["reclaimable"]),
                    group["paths"][0],
                )
            )
        report_lines.append("--- 优化建议 ---")
        report_lines.extend("- " + text for text in suggestions)

        return {
            "success": True,
            "roots": roots,
            "elapsed_sec": round(elapsed, 2),
            "scanned_files": counters["files"],
            "scanned_bytes": counters["bytes"],
            "scanned_human": _human(counters["bytes"]),
            "scan_errors": counters["errors"],
            "truncated": counters["truncated"],
            "drives": drives,
            "categories": category_list,
            "large_files": [
                {
                    "path": item["path"],
                    "size_human": _human(item["size"]),
                    "size_bytes": item["size"],
                    "modified": time.strftime("%Y-%m-%d", time.localtime(item["mtime"])),
                }
                for item in large_files
            ],
            "old_files": [
                {
                    "path": item["path"],
                    "size_human": _human(item["size"]),
                    "size_bytes": item["size"],
                    "modified": time.strftime("%Y-%m-%d", time.localtime(item["mtime"])),
                }
                for item in old_files
            ],
            "duplicate_groups": [
                {
                    "count": group["count"],
                    "size_human": _human(group["size"]),
                    "reclaimable_human": _human(group["reclaimable"]),
                    "reclaimable_bytes": group["reclaimable"],
                    "paths": group["paths"],
                }
                for group in duplicates
            ],
            "duplicate_reclaimable_bytes": reclaimable,
            "duplicate_reclaimable_human": _human(reclaimable),
            "suggestions": suggestions,
            "summary": "扫描 %d 个文件共 %s, 发现 %d 组重复文件可释放 %s。"
            % (
                counters["files"],
                _human(counters["bytes"]),
                len(duplicates),
                _human(reclaimable),
            ),
            "report": "\n".join(report_lines),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": "磁盘分析失败: %s: %s" % (type(exc).__name__, exc),
        }
