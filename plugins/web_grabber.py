"""web_grabber: 抓取网页, 提取标题与正文, 并能通过执行页面自带的 JS 挑战绕过阿里云 WAF。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from html.parser import HTMLParser

PLUGIN_META = {
    "name": "web_grabber",
    "description": "抓取指定 URL 的网页内容, 提取标题与正文纯文本, 可用 node 执行 JS 挑战绕过阿里云 WAF",
    "version": "2.1.0",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
SIMPLE_USER_AGENT = "Mozilla/5.0"

JS_ENGINE_NAMES = ("node", "nodejs")
CHALLENGE_MARKERS = ("aliyun_waf", "acw_sc__v2", "renderData", "arg1")

_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "iframe"})
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
     "section", "article", "header", "footer", "nav", "table", "ul", "ol"}
)
_HEADING_RE = re.compile(r"<(h[1-3])\b[^>]*>(.*?)</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# 在 node 中以最小 DOM 桩执行页面内联脚本, 捕获脚本写入的 cookie。
JS_SOLVER = r"""
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(0, 'utf8');
const jar = {};
const emit = process.stdout.write.bind(process.stdout);
process.stdout.write = function () { return true; };

const renderMatch = html.match(/<textarea[^>]*id="renderData"[^>]*>([\s\S]*?)<\/textarea>/i);
const renderInner = renderMatch ? renderMatch[1] : '';
const loc = {
  href: '', search: '', hash: '', reload: function () {}, replace: function () {}, assign: function () {}
};
const doc = {
  getElementById: function () {
    return { innerHTML: renderInner, value: renderInner, style: {}, setAttribute: function () {}, appendChild: function () {} };
  },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  getElementsByTagName: function () { return []; },
  getElementsByClassName: function () { return []; },
  createElement: function () { return { style: {}, setAttribute: function () {}, appendChild: function () {} }; },
  addEventListener: function () {},
  removeEventListener: function () {},
  write: function () {}, writeln: function () {}, open: function () {}, close: function () {},
  referrer: 'https://www.baidu.com/', scripts: [], location: loc
};
Object.defineProperty(doc, 'cookie', {
  get: function () {
    return Object.keys(jar).map(function (k) { return k + '=' + jar[k]; }).join('; ');
  },
  set: function (v) {
    const first = String(v).split(';')[0];
    const i = first.indexOf('=');
    if (i > 0) { jar[first.slice(0, i).trim()] = first.slice(i + 1).trim(); }
  }
});
const sandbox = {
  document: doc, location: loc, console: console,
  navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32', appVersion: '5.0' },
  setTimeout: setTimeout, clearTimeout: clearTimeout, setInterval: setInterval, clearInterval: clearInterval,
  encodeURIComponent: encodeURIComponent, decodeURIComponent: decodeURIComponent,
  encodeURI: encodeURI, decodeURI: decodeURI
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.top = sandbox;
sandbox.parent = sandbox;
const ctx = vm.createContext(sandbox);
const scriptRe = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
const scripts = [];
let m;
while ((m = scriptRe.exec(html)) !== null) { if (m[1].trim()) { scripts.push(m[1]); } }
for (let i = 0; i < scripts.length; i++) {
  try { vm.runInContext(scripts[i], ctx, { timeout: 5000 }); } catch (e) { /* 忽略单个脚本错误 */ }
}
emit(JSON.stringify({ cookies: jar, scripts: scripts.length }));
"""


def _normalize(raw):
    """合并多余空白, 去除行首行尾空格, 压缩连续空行。"""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0\u3000]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    out = []
    for line in lines:
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


class _PageParser(HTMLParser):
    """提取 <title> 与可见正文, 跳过脚本/样式等非内容节点。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = 0
        self._chunks = []
        self._title_chunks = []

    def _visible(self):
        return self._skip_depth == 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title += 1
        elif tag in _BLOCK_TAGS and self._visible():
            self._chunks.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in _BLOCK_TAGS and self._visible():
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
        elif tag == "title":
            if self._in_title > 0:
                self._in_title -= 1
        elif tag in _BLOCK_TAGS and self._visible():
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._in_title > 0:
            self._title_chunks.append(data)
        elif self._visible():
            self._chunks.append(data)

    def result(self):
        return _normalize("".join(self._title_chunks)), _normalize("".join(self._chunks))


def extract_title_and_text(html):
    """从 HTML 源码中解析出 (标题, 正文文本)。"""
    if not isinstance(html, str):
        raise TypeError("html 必须是字符串")
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    return parser.result()


def extract_headings(html):
    """抽取 h1~h3 标题文本, 返回 [(层级, 文本), ...]。"""
    if not isinstance(html, str):
        raise TypeError("html 必须是字符串")
    items = []
    for level, inner in _HEADING_RE.findall(html):
        inner = _TAG_RE.sub(" ", inner)
        text = re.sub(r"\s+", " ", inner).strip()
        if text:
            items.append((level.lower(), text))
    return items


def normalize_url(url):
    """补全协议头, 校验 URL 基本格式。"""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url 必须是非空字符串")
    url = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        url = "https://" + url.lstrip("/")
    return url


def build_headers(user_agent=None, extra=None):
    """构造请求头, 可用自定义 UA 覆盖默认值。"""
    headers = {
        "User-Agent": user_agent or _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    if extra:
        headers.update(extra)
    return headers


def detect_challenge(html):
    """返回命中的反爬挑战特征列表; 空列表表示不是挑战页。"""
    if not isinstance(html, str):
        raise TypeError("html 必须是字符串")
    return [marker for marker in CHALLENGE_MARKERS if marker in html]


def is_challenge(html):
    """判断响应是否为阿里云 WAF 之类的验证挑战页。"""
    hits = set(detect_challenge(html))
    if hits & {"aliyun_waf", "acw_sc__v2"}:
        return True
    return {"renderData", "arg1"} <= hits


def describe_page(html, head_chars=2000):
    """给出页面的快速诊断信息。"""
    if not isinstance(html, str):
        raise TypeError("html 必须是字符串")
    return {
        "html_length": len(html),
        "challenge_markers": detect_challenge(html),
        "html_head": html[:head_chars],
    }


def parse_set_cookies(values):
    """把 Set-Cookie 头解析成 cookie 字典, 空值视为删除。"""
    jar = {}
    for value in values or []:
        first = str(value).split(";")[0]
        if "=" not in first:
            continue
        name, val = first.split("=", 1)
        name = name.strip()
        val = val.strip()
        if not name:
            continue
        if val == "":
            jar.pop(name, None)
        else:
            jar[name] = val
    return jar


def find_js_engine(node_path=None):
    """查找可用的 JS 引擎 (node), 未找到返回 None。"""
    if node_path:
        return shutil.which(node_path) or (node_path if os.path.isfile(node_path) else None)
    for name in JS_ENGINE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def solve_js_challenge(html, node_path=None, timeout=20):
    """用 node 执行页面自带脚本, 返回 {'success','cookies','scripts','error'}。"""
    if not isinstance(html, str):
        raise TypeError("html 必须是字符串")
    engine = find_js_engine(node_path)
    if not engine:
        return {"success": False, "cookies": {}, "scripts": 0,
                "error": "未找到 JS 引擎(node), 无法执行反爬挑战脚本"}
    try:
        proc = subprocess.run(
            [engine, "-e", JS_SOLVER],
            input=html.encode("utf-8", errors="replace"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "cookies": {}, "scripts": 0, "error": "JS 挑战执行超时"}
    except OSError as exc:
        return {"success": False, "cookies": {}, "scripts": 0,
                "error": "%s: %s" % (type(exc).__name__, exc)}

    stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return {"success": False, "cookies": {}, "scripts": 0,
                "error": "node 退出码 %s: %s" % (proc.returncode, stderr_text[:300])}
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(out)
    except ValueError:
        return {"success": False, "cookies": {}, "scripts": 0,
                "error": "无法解析 node 输出: %s" % out[:200]}
    cookies = {k: v for k, v in (data.get("cookies") or {}).items() if v}
    if not cookies:
        return {"success": False, "cookies": {}, "scripts": data.get("scripts", 0),
                "error": "挑战脚本未产出 cookie"}
    return {"success": True, "cookies": cookies, "scripts": data.get("scripts", 0), "error": None}


def fetch(url, timeout=15, encoding=None, headers=None):
    """下载网页, 返回 (最终 URL, 状态码, HTML, 响应头字典, Set-Cookie 列表)。"""
    req = urllib.request.Request(url, headers=headers or build_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = encoding or resp.headers.get_content_charset() or "utf-8"
        try:
            html = raw.decode(charset, errors="replace")
        except LookupError:
            html = raw.decode("utf-8", errors="replace")
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        set_cookies = resp.headers.get_all("Set-Cookie") or []
        return resp.geturl(), getattr(resp, "status", None), html, resp_headers, list(set_cookies)


def grab(url, timeout=15, max_chars=8000, encoding=None, headers=None, raw=False,
         solve_challenge=True, max_attempts=3, challenge_timeout=20,
         node_path=None, cookies=None, want_headings=False):
    """抓取 URL 并返回标题与正文; 遇到 WAF 挑战时自动解 cookie 后重试。"""
    result = {
        "success": False,
        "url": url,
        "final_url": None,
        "status": None,
        "title": "",
        "text": "",
        "text_length": 0,
        "truncated": False,
        "error": None,
        "attempts": 0,
        "challenge_detected": False,
        "challenge_solved": False,
        "cookie_names": [],
    }
    target = normalize_url(url)
    result["url"] = target

    if max_chars is not None and (not isinstance(max_chars, int) or max_chars <= 0):
        raise ValueError("max_chars 必须是正整数或 None")
    if max_attempts is not None and (not isinstance(max_attempts, int) or max_attempts <= 0):
        raise ValueError("max_attempts 必须是正整数")

    jar = {k: v for k, v in (cookies or {}).items() if v}
    attempts = max(1, max_attempts or 1)
    html = ""

    for attempt in range(attempts):
        result["attempts"] = attempt + 1
        req_headers = dict(headers or build_headers())
        if jar:
            req_headers["Cookie"] = "; ".join("%s=%s" % item for item in sorted(jar.items()))
        try:
            final_url, status, html, resp_headers, set_cookies = fetch(
                target, timeout=timeout, encoding=encoding, headers=req_headers
            )
        except urllib.error.HTTPError as exc:
            result["error"] = "HTTPError %s: %s" % (exc.code, exc.reason)
            result["status"] = exc.code
            return result
        except urllib.error.URLError as exc:
            result["error"] = "URLError: %s" % (exc.reason,)
            return result
        except (OSError, ValueError) as exc:
            result["error"] = "%s: %s" % (type(exc).__name__, exc)
            return result

        jar.update(parse_set_cookies(set_cookies))
        result["final_url"] = final_url
        result["status"] = status

        if not is_challenge(html):
            break

        result["challenge_detected"] = True
        if not solve_challenge:
            result["error"] = result["error"] or "页面为反爬挑战页, 未开启自动破解"
            break
        solved = solve_js_challenge(html, node_path=node_path, timeout=challenge_timeout)
        if not solved["success"]:
            result["error"] = solved["error"]
            break
        jar.update(solved["cookies"])
        result["challenge_solved"] = True

    result["cookie_names"] = sorted(jar)
    if result["challenge_detected"] and not result["challenge_solved"] and not result["error"]:
        result["error"] = "多次重试后仍被反爬挑战拦截"

    if not html:
        return result

    title, text = extract_title_and_text(html)
    result["success"] = True
    result["title"] = title
    result["text_length"] = len(text)
    result["html_length"] = len(html)
    if want_headings:
        result["headings"] = extract_headings(html)
    if raw:
        result["resp_headers"] = resp_headers
        result["challenge_markers"] = detect_challenge(html)
        result["html_head"] = html[:2000]
    if max_chars is not None and len(text) > max_chars:
        result["text"] = text[:max_chars]
        result["truncated"] = True
    else:
        result["text"] = text
    return result


def run(url, timeout=15, max_chars=8000, encoding=None, headers=None, raw=False,
        solve_challenge=True, max_attempts=3, node_path=None, cookies=None):
    """插件入口: 抓取网页并返回标题与正文文本。"""
    return grab(
        url, timeout=timeout, max_chars=max_chars, encoding=encoding, headers=headers,
        raw=raw, solve_challenge=solve_challenge, max_attempts=max_attempts,
        node_path=node_path, cookies=cookies,
    )
