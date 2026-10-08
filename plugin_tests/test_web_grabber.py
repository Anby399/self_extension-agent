"""web_grabber 的测试: 解析/挑战识别离线验证, JS 挑战求解用本地样例, 另含联网抓取。"""

import warnings

import pytest

import web_grabber as wg

SAMPLE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <title>  传智教育·黑马程序员  </title>
  <style>body { color: red; }</style>
  <script>var x = 1; console.log("script 里的文本不应出现");</script>
</head>
<body>
  <h1>黑马程序员</h1>
  <h2>  精品课程  </h2>
  <p>页面&nbsp;正文&nbsp;第一段</p>
  <div>第二段
     <span>内联内容</span>
  </div>
  <ul><li>课程一</li><li>课程二</li></ul>
  <noscript>需要开启 JavaScript</noscript>
</body>
</html>
"""

ARG1 = "5deb2d03ed4bc1fb4fea6e44d1ed15965c563dfe9b201d4c2c"

FAKE_CHALLENGE = (
    '<textarea id="renderData" style="display:none">{"l1":"var arg1=\'%s\';"}</textarea>'
    '<!doctype html><html><head><meta name="aliyun_waf_aa" content="x">'
    '<script>function getRenderData(){return document.getElementById("renderData").innerHTML}'
    'var renderData=JSON.parse(getRenderData()),arg1=renderData.l1.slice(10,60);'
    'function setCookie(e,r){document.cookie=e+"="+r+";max-age=3600;path=/"}'
    'function reload(e){setCookie("acw_sc__v2",e)}'
    'reload(arg1)</script></head><body></body></html>'
) % ARG1

TARGET = "https://www.itheima.com/"


def _emit(label, text):
    """把长文本切片通过 warning 回传, 便于在测试输出中查看。"""
    payload = "%s\n%s" % (label, text)
    for chunk in [payload[i:i + 900] for i in range(0, len(payload), 900)]:
        warnings.warn("DIAG " + chunk)


def test_normalize_url_adds_scheme():
    assert wg.normalize_url("www.itheima.com") == "https://www.itheima.com"
    assert wg.normalize_url(" http://example.com/a ") == "http://example.com/a"


def test_normalize_url_rejects_empty():
    for bad in ("", "   ", None, 123):
        with pytest.raises(ValueError):
            wg.normalize_url(bad)


def test_build_headers_allows_override():
    assert wg.build_headers()["User-Agent"] == wg._USER_AGENT
    assert wg.build_headers(wg.SIMPLE_USER_AGENT)["User-Agent"] == wg.SIMPLE_USER_AGENT
    assert wg.build_headers(extra={"Referer": "https://x.com"})["Referer"] == "https://x.com"


def test_extract_title_and_text():
    title, text = wg.extract_title_and_text(SAMPLE_HTML)
    assert title == "传智教育·黑马程序员"
    assert "黑马程序员" in text
    assert "第一段" in text
    assert "内联内容" in text
    assert "课程二" in text


def test_extract_text_skips_script_and_style():
    _, text = wg.extract_title_and_text(SAMPLE_HTML)
    assert "script 里的文本不应出现" not in text
    assert "color: red" not in text
    assert "需要开启 JavaScript" not in text


def test_extract_text_collapses_blank_lines():
    _, text = wg.extract_title_and_text(SAMPLE_HTML)
    assert "\n\n\n" not in text
    assert "  " not in text
    assert not text.startswith("\n")


def test_extract_requires_string():
    with pytest.raises(TypeError):
        wg.extract_title_and_text(None)


def test_extract_headings():
    headings = wg.extract_headings(SAMPLE_HTML)
    assert ("h1", "黑马程序员") in headings
    assert ("h2", "精品课程") in headings
    with pytest.raises(TypeError):
        wg.extract_headings(None)


def test_detect_challenge():
    assert wg.detect_challenge(SAMPLE_HTML) == []
    assert wg.is_challenge(SAMPLE_HTML) is False
    assert wg.is_challenge(FAKE_CHALLENGE) is True
    assert "aliyun_waf" in wg.detect_challenge(FAKE_CHALLENGE)


def test_parse_set_cookies():
    jar = wg.parse_set_cookies([
        "acw_tc=abc123; Path=/; HttpOnly",
        "acw_sc__v2=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/",
        "other=1; Path=/",
    ])
    assert jar == {"acw_tc": "abc123", "other": "1"}
    assert wg.parse_set_cookies(None) == {}


def test_find_js_engine_reports_missing():
    assert wg.find_js_engine("definitely-not-an-engine-xyz") is None


def test_solve_js_challenge_missing_engine():
    result = wg.solve_js_challenge(FAKE_CHALLENGE, node_path="definitely-not-an-engine-xyz")
    assert result["success"] is False
    assert result["error"]


def test_solve_js_challenge_requires_string():
    with pytest.raises(TypeError):
        wg.solve_js_challenge(None)


def test_solve_js_challenge_on_local_page():
    if not wg.find_js_engine():
        pytest.skip("本机没有 node, 跳过 JS 挑战求解测试")
    result = wg.solve_js_challenge(FAKE_CHALLENGE, timeout=30)
    assert result["success"] is True, result["error"]
    assert result["cookies"]["acw_sc__v2"] == ARG1


def test_grab_rejects_empty_url():
    with pytest.raises(ValueError):
        wg.grab("")


def test_grab_rejects_bad_max_chars():
    with pytest.raises(ValueError):
        wg.grab("example.com", max_chars=0)


def test_grab_rejects_bad_max_attempts():
    with pytest.raises(ValueError):
        wg.grab("example.com", max_attempts=0)


def test_grab_reports_network_error_without_raising():
    result = wg.grab("https://this-host-should-not-exist-9f8a7b6c.invalid", timeout=5)
    assert result["success"] is False
    assert result["error"]


def test_meta_present():
    assert wg.PLUGIN_META["name"] == "web_grabber"
    assert wg.PLUGIN_META["version"]
    assert wg.PLUGIN_META["description"]


def test_live_grab_heima_homepage():
    """联网抓取黑马程序员主页 (自动解 WAF 挑战), 关键结果通过 warning 回传。"""
    result = wg.grab(TARGET, timeout=20, max_chars=None, challenge_timeout=30,
                     raw=True, want_headings=True)
    if not result["success"]:
        pytest.skip("网络不可达: %s" % result["error"])
    summary = {
        "status": result["status"],
        "final_url": result["final_url"],
        "attempts": result["attempts"],
        "challenge_detected": result["challenge_detected"],
        "challenge_solved": result["challenge_solved"],
        "cookie_names": result["cookie_names"],
        "title": result["title"],
        "text_length": result["text_length"],
        "html_length": result["html_length"],
        "markers_after": result.get("challenge_markers"),
        "server": (result.get("resp_headers") or {}).get("server"),
    }
    headings = result.get("headings") or []
    heading_txt = "\n".join("%s: %s" % (lv, tx) for lv, tx in headings[:60])
    _emit("SUMMARY %s" % summary, "HEADINGS(%d)\n%s" % (len(headings), heading_txt))
    _emit("BODY", result["text"])
    assert result["challenge_solved"] is True
    assert result["title"]
