"""heima_report 的测试: 离线用样例结果验证摘要逻辑, 联网时输出精简报告。"""

import warnings

import pytest

import heima_report as hr

FAKE_RESULT = {
    "success": True,
    "final_url": "https://www.itheima.com/",
    "status": 200,
    "attempts": 2,
    "challenge_detected": True,
    "challenge_solved": True,
    "cookie_names": ["acw_sc__v2"],
    "title": "黑马程序员官网",
    "text": "黑马程序员\n精品学科：\nAI大模型开发\nAI测试\n校区分布\n就业薪资",
    "text_length": 40,
    "html_length": 1000,
    "headings": [("h1", "黑马程序员"), ("h2", "精品学科")],
}


def _emit(text):
    for chunk in [text[i:i + 900] for i in range(0, len(text), 900)]:
        warnings.warn("REPORT " + chunk)


def test_summarize_basic_fields():
    report = hr.summarize(FAKE_RESULT)
    assert report["title"] == "黑马程序员官网"
    assert report["challenge_solved"] is True
    assert report["line_count"] == 6
    assert ["h1", "黑马程序员"] in report["headings"]
    assert report["keyword_hits"]["学科"] >= 1


def test_summarize_requires_dict():
    with pytest.raises(TypeError):
        hr.summarize(None)


def test_summarize_handles_empty_result():
    report = hr.summarize({})
    assert report["title"] == ""
    assert report["headings"] == []
    assert report["keyword_hits"] == {}


def test_format_report_contains_key_lines():
    text = hr.format_report(hr.summarize(FAKE_RESULT))
    assert "title: 黑马程序员官网" in text
    assert "challenge: detected=True solved=True" in text
    assert "h1 黑马程序员" in text


def test_format_report_requires_dict():
    with pytest.raises(TypeError):
        hr.format_report("x")


def test_normalize_whitespace():
    assert hr.normalize_whitespace("  a \n b\t c ") == "a b c"
    with pytest.raises(TypeError):
        hr.normalize_whitespace(1)


def test_run_rejects_empty_url():
    with pytest.raises(ValueError):
        hr.run("")


def test_meta_present():
    assert hr.PLUGIN_META["name"] == "heima_report"
    assert hr.PLUGIN_META["version"]
    assert hr.PLUGIN_META["description"]


def test_live_report_heima():
    """联网生成精简报告 (网络不可达时跳过)。"""
    out = hr.run(timeout=25)
    if not out["success"]:
        pytest.skip("抓取失败: %s" % out["report"].get("error"))
    _emit(out["text"])
    assert out["report"]["title"]
