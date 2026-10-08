"""heima_report: 汇总黑马程序员主页抓取结果的辅助插件 (基于 web_grabber)。"""

from __future__ import annotations

import re

PLUGIN_META = {
    "name": "heima_report",
    "description": "抓取黑马程序员主页并输出标题、章节结构与摘要统计",
    "version": "1.0.0",
}

SECTION_KEYS = [
    "热门学科", "学科", "师资", "教研团队", "校区", "就业", "新闻资讯",
    "免费教程", "常见问题", "黑马研究院", "学科资讯", "关于",
]


def summarize(result, max_headings=40, snippet=600):
    """把 web_grabber 的抓取结果整理成报告字典。"""
    if not isinstance(result, dict):
        raise TypeError("result 必须是 dict")
    text = result.get("text") or ""
    headings = [list(item) for item in (result.get("headings") or [])]
    lines = [line for line in text.split("\n") if line.strip()]
    keywords = {}
    for key in SECTION_KEYS:
        count = sum(1 for line in lines if key in line)
        if count:
            keywords[key] = count
    return {
        "title": result.get("title", ""),
        "final_url": result.get("final_url"),
        "status": result.get("status"),
        "attempts": result.get("attempts"),
        "challenge_detected": result.get("challenge_detected"),
        "challenge_solved": result.get("challenge_solved"),
        "cookies": result.get("cookie_names"),
        "text_length": result.get("text_length"),
        "html_length": result.get("html_length"),
        "line_count": len(lines),
        "headings": headings[:max_headings],
        "keyword_hits": keywords,
        "snippet": text[:snippet],
    }


def format_report(report):
    """把报告字典格式化成便于阅读的多行文本。"""
    if not isinstance(report, dict):
        raise TypeError("report 必须是 dict")
    out = [
        "title: %s" % report.get("title"),
        "final_url: %s | status: %s | attempts: %s" % (
            report.get("final_url"), report.get("status"), report.get("attempts")),
        "challenge: detected=%s solved=%s cookies=%s" % (
            report.get("challenge_detected"), report.get("challenge_solved"), report.get("cookies")),
        "size: html=%s text=%s lines=%s" % (
            report.get("html_length"), report.get("text_length"), report.get("line_count")),
    ]
    headings = report.get("headings") or []
    out.append("headings(%d):" % len(headings))
    out.extend("  %s %s" % (lv, tx) for lv, tx in headings)
    hits = report.get("keyword_hits") or {}
    out.append("keyword_hits: %s" % ", ".join("%s x%d" % (k, v) for k, v in hits.items()))
    out.append("snippet:\n%s" % report.get("snippet"))
    return "\n".join(out)


def run(url="https://www.itheima.com/", timeout=20, max_headings=40):
    """插件入口: 抓取主页并返回报告文本。"""
    import web_grabber

    if not isinstance(url, str) or not url.strip():
        raise ValueError("url 必须是非空字符串")
    result = web_grabber.grab(
        url, timeout=timeout, max_chars=None, raw=True, want_headings=True
    )
    report = summarize(result, max_headings=max_headings)
    report["error"] = result.get("error")
    report["text"] = result.get("text", "")
    return {"success": result.get("success", False), "report": report,
            "text": format_report(report)}


def normalize_whitespace(value):
    """把连续空白压成单个空格 (便于在日志中紧凑输出)。"""
    if not isinstance(value, str):
        raise TypeError("value 必须是字符串")
    return re.sub(r"\s+", " ", value).strip()
