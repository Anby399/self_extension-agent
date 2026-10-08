"""前端页面 (HTML)。

前端以 HTML 形式编写, 由 Flask 后端在 ``GET /`` 时直接返回。

特性:
- 类 ChatGPT 布局: 左侧可折叠导航栏 + 居中对话列 + 底部圆角输入框;
- 不使用头像图标, 用户消息右对齐气泡, 助手消息左对齐纯文本;
- 可隐藏/展开的设置抽屉 (主题、强调色、字号、气泡样式、功能开关);
- 内置轻量 Markdown 渲染器, 无外部 CDN 依赖; 设置持久化到 localStorage。
"""

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Self-Extension Agent</title>
<style>
  :root {
    --bg:#0f172a; --panel:#1e293b; --sidebar:#0b1120;
    --text:#e2e8f0; --muted:#94a3b8; --border:#334155;
    --user:#2563eb; --user-text:#ffffff;
    --input:#0b1220; --accent:#2563eb; --font-size:15px;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin:0; font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    background:var(--bg); color:var(--text); height:100vh; overflow:hidden;
    display:flex; transition: background .3s, color .3s;
  }
  ::-webkit-scrollbar { width:10px; height:10px; }
  ::-webkit-scrollbar-thumb { background:var(--border); border-radius:6px; }
  ::-webkit-scrollbar-thumb:hover { background:#475569; }

  .app { display:flex; width:100%; height:100%; }

  /* ================= 左侧导航栏 ================= */
  .sidebar {
    width:260px; flex:0 0 260px; background:var(--sidebar);
    border-right:1px solid var(--border); display:flex; flex-direction:column;
    padding:12px; transition: background .3s, margin-left .25s, width .25s; overflow:hidden;
  }
  body.sidebar-collapsed .sidebar { width:0; flex:0 0 0; padding:0; border-right:none; }
  .new-chat {
    display:flex; align-items:center; justify-content:center; gap:8px;
    width:100%; padding:11px; background:transparent; border:1px solid var(--border);
    color:var(--text); border-radius:12px; cursor:pointer; font-size:14px;
    transition: background .15s, border-color .15s;
  }
  .new-chat:hover { background:var(--panel); border-color:var(--muted); }
  .nav-section { margin-top:20px; flex:1; overflow-y:auto; }
  .nav-title { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.6px; margin:0 6px 8px; font-weight:600; }
  .history-item {
    width:100%; text-align:left; padding:10px 12px; background:transparent; border:none;
    color:var(--text); border-radius:10px; cursor:pointer; font-size:14px;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:background .15s;
  }
  .history-item:hover { background:var(--panel); }
  .history-item.active { background:var(--panel); }
  .nav-bottom { margin-top:12px; }
  .nav-btn {
    display:flex; align-items:center; gap:8px; width:100%; padding:10px 12px;
    background:transparent; border:none; color:var(--muted); border-radius:10px;
    cursor:pointer; font-size:14px; transition: background .15s, color .15s;
  }
  .nav-btn:hover { background:var(--panel); color:var(--text); }

  .nav-mask { display:none; }

  /* ================= 设置抽屉 ================= */
  .drawer-mask {
    position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:60;
    opacity:0; pointer-events:none; transition:opacity .25s;
  }
  body.settings-open .drawer-mask { opacity:1; pointer-events:auto; }
  .settings-drawer {
    position:fixed; top:0; right:0; height:100%; width:320px; max-width:90vw;
    background:var(--sidebar); border-left:1px solid var(--border); z-index:70;
    display:flex; flex-direction:column; transform:translateX(100%); transition:transform .28s;
  }
  body.settings-open .settings-drawer { transform:translateX(0); }
  .drawer-head {
    display:flex; align-items:center; justify-content:space-between;
    padding:16px 18px; border-bottom:1px solid var(--border); font-size:15px; font-weight:600;
  }
  .drawer-head button {
    background:none; border:none; color:var(--muted); font-size:18px; cursor:pointer;
    width:30px; height:30px; border-radius:8px;
  }
  .drawer-head button:hover { background:var(--panel); color:var(--text); }
  .drawer-body { flex:1; overflow-y:auto; padding:18px; }

  .setting { margin-bottom:22px; }
  .setting > .label {
    display:flex; justify-content:space-between; align-items:center;
    font-size:11px; color:var(--muted); margin-bottom:8px;
    text-transform:uppercase; letter-spacing:.6px; font-weight:600;
  }
  .swatches { display:flex; gap:8px; flex-wrap:wrap; }
  .swatch {
    width:28px; height:28px; border-radius:8px; border:2px solid var(--border);
    cursor:pointer; padding:0; transition: transform .15s;
  }
  .swatch:hover { transform: scale(1.12); }
  .swatch.active { border-color:var(--text); box-shadow:0 0 0 2px var(--accent); }
  input[type="color"] {
    width:100%; height:34px; margin-top:10px; padding:2px; border:1px solid var(--border);
    border-radius:8px; background:var(--input); cursor:pointer;
  }
  input[type="range"] { width:100%; accent-color:var(--accent); cursor:pointer; }
  .seg { display:flex; background:var(--input); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
  .seg button {
    flex:1; padding:8px 0; background:none; border:none; color:var(--muted);
    font-size:13px; cursor:pointer; transition: background .15s, color .15s;
  }
  .seg button.active { background:var(--accent); color:#fff; }
  .switch-row {
    display:flex; align-items:center; justify-content:space-between;
    padding:9px 0; font-size:14px; cursor:pointer;
  }
  .switch { position:relative; width:42px; height:24px; flex:0 0 42px; }
  .switch input { opacity:0; width:0; height:0; }
  .switch .slider { position:absolute; inset:0; background:var(--border); border-radius:24px; transition:.25s; cursor:pointer; }
  .switch .slider:before {
    content:""; position:absolute; height:18px; width:18px; left:3px; top:3px;
    background:#fff; border-radius:50%; transition:.25s;
  }
  .switch input:checked + .slider { background:var(--accent); }
  .switch input:checked + .slider:before { transform:translateX(18px); }
  .btn-ghost {
    margin-top:6px; padding:10px; background:var(--input); border:1px solid var(--border);
    color:var(--text); border-radius:10px; cursor:pointer; font-size:13px; width:100%;
  }
  .btn-ghost:hover { border-color:var(--accent); color:var(--accent); }

  /* ================= 主区域 ================= */
  .main { flex:1; display:flex; flex-direction:column; min-width:0; }
  header {
    padding:12px 16px; background:var(--panel); border-bottom:1px solid var(--border);
    display:flex; align-items:center; gap:12px; transition: background .3s;
  }
  .icon-btn {
    width:36px; height:36px; background:none; border:none; color:var(--text);
    border-radius:9px; cursor:pointer; font-size:18px; display:flex; align-items:center; justify-content:center;
  }
  .icon-btn:hover { background:var(--sidebar); }
  header .title { font-size:15px; font-weight:600; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  #status { font-size:12px; color:var(--muted); display:flex; align-items:center; }
  .dot { width:8px; height:8px; border-radius:50%; background:#22c55e; display:inline-block; margin-right:6px; flex:0 0 8px; }
  .dot.offline { background:#ef4444; }

  /* ================= 聊天区 (类 ChatGPT) ================= */
  .chat-scroll { flex:1; overflow-y:auto; }
  #chat { max-width:768px; margin:0 auto; padding:28px 24px; display:flex; flex-direction:column; gap:22px; }
  .msg-row { display:flex; width:100%; }
  .msg-row.user { justify-content:flex-end; }
  .msg-row.bot { justify-content:flex-start; }
  .msg-col { display:flex; flex-direction:column; min-width:0; }
  .msg-row.user .msg-col { align-items:flex-end; max-width:80%; }
  .msg-row.bot .msg-col { align-items:flex-start; width:100%; }
  .msg {
    font-size:var(--font-size); line-height:1.7; word-break:break-word; white-space:pre-wrap;
  }
  .msg-row.user .msg {
    background:var(--user); color:var(--user-text); padding:10px 16px; border-radius:18px;
    transition: background .3s;
  }
  .msg-row.bot .msg { background:transparent; color:var(--text); padding:0; }
  body[data-bubble="square"] .msg-row.user .msg { border-radius:6px; }
  body[data-bubble="soft"] .msg-row.user .msg { border-radius:24px; }
  .msg-time { font-size:11px; color:var(--muted); margin-top:5px; padding:0 4px; }

  /* Markdown 元素样式 */
  .msg h1,.msg h2,.msg h3,.msg h4 { margin:12px 0 6px; line-height:1.3; }
  .msg h1 { font-size:1.4em; } .msg h2 { font-size:1.25em; } .msg h3 { font-size:1.1em; }
  .msg p { margin:6px 0; }
  .msg ul,.msg ol { margin:6px 0; padding-left:22px; }
  .msg li { margin:3px 0; }
  .msg code {
    background:rgba(148,163,184,.18); padding:2px 6px; border-radius:5px;
    font-family: ui-monospace, Consolas, "Courier New", monospace; font-size:.9em;
  }
  .msg pre.code { background:#0b1120; border:1px solid var(--border); border-radius:10px; margin:8px 0; overflow:hidden; }
  .msg pre.code code { display:block; padding:14px; overflow-x:auto; background:none; border-radius:0; font-size:13px; white-space:pre; }
  .code-head {
    display:flex; justify-content:space-between; align-items:center; gap:10px;
    padding:6px 12px; background:rgba(255,255,255,.05); border-bottom:1px solid var(--border);
    font-size:12px; color:var(--muted);
  }
  .copy-btn {
    background:rgba(255,255,255,.08); border:1px solid var(--border); color:var(--muted);
    border-radius:6px; padding:3px 10px; font-size:12px; cursor:pointer;
  }
  .copy-btn:hover { color:var(--text); border-color:var(--muted); }
  .msg blockquote {
    margin:8px 0; padding:6px 14px; border-left:3px solid var(--accent);
    background:rgba(148,163,184,.08); border-radius:0 8px 8px 0; color:var(--muted);
  }
  .msg table { border-collapse:collapse; margin:8px 0; width:100%; font-size:.95em; }
  .msg th,.msg td { border:1px solid var(--border); padding:6px 10px; text-align:left; }
  .msg th { background:rgba(148,163,184,.12); }
  .msg hr { border:none; border-top:1px solid var(--border); margin:10px 0; }
  .msg a { color:var(--accent); text-decoration:none; }
  .msg a:hover { text-decoration:underline; }
  .msg strong { font-weight:700; }
  .msg em { font-style:italic; }
  .msg del { text-decoration:line-through; opacity:.7; }

  .msg.typing span {
    width:7px; height:7px; border-radius:50%; background:var(--muted);
    display:inline-block; margin:0 2px; animation:blink 1.2s infinite;
  }
  .msg.typing span:nth-child(2) { animation-delay:.2s; }
  .msg.typing span:nth-child(3) { animation-delay:.4s; }
  @keyframes blink { 0%,60%,100% { opacity:.3; transform:translateY(0); } 30% { opacity:1; transform:translateY(-4px); } }

  /* 欢迎页 */
  .welcome { text-align:center; margin:auto; padding:40px 20px; max-width:460px; }
  .welcome-icon { font-size:40px; line-height:1; }
  .welcome h2 { margin:14px 0 8px; font-size:22px; }
  .welcome p { color:var(--muted); line-height:1.6; margin:0; }
  .hints { margin-top:20px; display:flex; gap:8px; flex-wrap:wrap; justify-content:center; }
  .hints span {
    padding:7px 13px; background:var(--panel); border:1px solid var(--border);
    border-radius:999px; font-size:13px; color:var(--muted); cursor:pointer;
  }
  .hints span:hover { border-color:var(--accent); color:var(--text); }

  /* ================= 输入区 (类 ChatGPT) ================= */
  .composer { padding:0 24px 18px; }
  .composer form {
    max-width:768px; margin:0 auto; display:flex; align-items:flex-end; gap:8px;
    background:var(--panel); border:1px solid var(--border); border-radius:24px;
    padding:8px 8px 8px 18px; box-shadow:0 4px 24px rgba(0,0,0,.15); transition: background .3s, border-color .2s;
  }
  .composer form:focus-within { border-color:var(--accent); }
  .composer textarea {
    flex:1; background:transparent; border:none; outline:none; color:var(--text);
    font-size:15px; resize:none; max-height:200px; padding:9px 0; font-family:inherit; line-height:1.5;
  }
  .composer #send {
    width:36px; height:36px; flex:0 0 36px; border-radius:50%; border:none; background:var(--accent);
    color:#fff; font-size:18px; cursor:pointer; display:flex; align-items:center; justify-content:center;
    transition:opacity .2s, transform .15s;
  }
  .composer #send:disabled { opacity:.4; cursor:not-allowed; }
  .composer #send:not(:disabled):hover { transform:scale(1.06); }
  .composer-note { max-width:768px; margin:8px auto 0; text-align:center; font-size:11px; color:var(--muted); }

  /* ================= 响应式 ================= */
  @media (max-width: 900px) {
    .sidebar {
      position:fixed; left:0; top:0; height:100%; z-index:50; width:280px; flex:none;
      transform:translateX(-100%); transition:transform .25s; box-shadow:4px 0 24px rgba(0,0,0,.5);
    }
    body.sidebar-open .sidebar { transform:translateX(0); }
    body.sidebar-collapsed .sidebar { width:280px; padding:12px; border-right:1px solid var(--border); }
    body.sidebar-open .nav-mask {
      display:block; position:fixed; inset:0; background:rgba(0,0,0,.4); z-index:45;
    }
    .composer { padding:0 12px 12px; }
    #chat { padding:20px 14px; }
  }
</style>
</head>
<body>
  <div class="app">
    <!-- 左侧导航栏 -->
    <aside class="sidebar" id="sidebar">
      <button class="new-chat" id="newChat" type="button">＋ 新建对话</button>
      <div class="nav-section">
        <div class="nav-title">对话历史</div>
        <div class="history-list" id="historyList">
          <button class="history-item active" id="currentConv" type="button">当前对话</button>
        </div>
      </div>
      <div class="nav-bottom">
        <button class="nav-btn" id="openSettings" type="button">⚙️ 设置</button>
      </div>
    </aside>
    <div class="nav-mask" id="navMask"></div>

    <!-- 设置抽屉 -->
    <div class="drawer-mask" id="drawerMask"></div>
    <aside class="settings-drawer" id="settingsDrawer">
      <div class="drawer-head">
        <span>显示设置</span>
        <button id="closeSettings" type="button">✕</button>
      </div>
      <div class="drawer-body">
        <div class="setting">
          <div class="label"><span>主题</span></div>
          <div class="swatches" id="themeSwatches">
            <button class="swatch" data-theme="dark" style="background:#0f172a" title="深色" type="button"></button>
            <button class="swatch" data-theme="light" style="background:#f1f5f9" title="浅色" type="button"></button>
            <button class="swatch" data-theme="midnight" style="background:#000000" title="午夜" type="button"></button>
            <button class="swatch" data-theme="forest" style="background:#0b1a12" title="森林" type="button"></button>
            <button class="swatch" data-theme="ocean" style="background:#082032" title="海洋" type="button"></button>
          </div>
        </div>

        <div class="setting">
          <div class="label"><span>强调色</span></div>
          <div class="swatches" id="accentSwatches">
            <button class="swatch" data-accent="#2563eb" style="background:#2563eb" type="button"></button>
            <button class="swatch" data-accent="#10b981" style="background:#10b981" type="button"></button>
            <button class="swatch" data-accent="#f59e0b" style="background:#f59e0b" type="button"></button>
            <button class="swatch" data-accent="#ef4444" style="background:#ef4444" type="button"></button>
            <button class="swatch" data-accent="#a855f7" style="background:#a855f7" type="button"></button>
            <button class="swatch" data-accent="#ec4899" style="background:#ec4899" type="button"></button>
          </div>
          <input type="color" id="accentCustom" title="自定义强调色">
        </div>

        <div class="setting">
          <div class="label"><span>字号</span><span id="fontSizeLabel">15px</span></div>
          <input type="range" id="fontSizeRange" min="12" max="22" step="1" value="15">
        </div>

        <div class="setting">
          <div class="label"><span>用户气泡样式</span></div>
          <div class="seg" id="bubbleSeg">
            <button data-bubble="rounded" type="button">圆角</button>
            <button data-bubble="soft" type="button">柔和</button>
            <button data-bubble="square" type="button">直角</button>
          </div>
        </div>

        <div class="setting">
          <div class="label"><span>功能开关</span></div>
          <label class="switch-row"><span>Markdown 渲染</span>
            <span class="switch"><input type="checkbox" id="mdToggle"><span class="slider"></span></span></label>
          <label class="switch-row"><span>显示时间</span>
            <span class="switch"><input type="checkbox" id="timeToggle"><span class="slider"></span></span></label>
        </div>

        <button class="btn-ghost" id="resetSettings" type="button">恢复默认设置</button>
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="main">
      <header>
        <button class="icon-btn" id="toggleSidebar" type="button" title="侧边栏">☰</button>
        <div class="title">Self-Extension Agent</div>
        <span id="status"><i class="dot"></i>连接中…</span>
        <button class="icon-btn" id="openSettingsHeader" type="button" title="设置">⚙️</button>
      </header>

      <div class="chat-scroll" id="chatScroll">
        <div id="chat"></div>
      </div>

      <div class="composer">
        <form id="form">
          <textarea id="input" rows="1" placeholder="给 Self-Extension Agent 发送消息…" autocomplete="off"></textarea>
          <button id="send" type="submit" title="发送">↑</button>
        </form>
        <div class="composer-note">Enter 发送 · Shift+Enter 换行 · 内容由 AI 生成，请注意甄别</div>
      </div>
    </div>
  </div>

<script>
(function () {
  'use strict';

  /* ================= 显示设置 ================= */
  var THEMES = {
    dark:    { bg:'#0f172a', panel:'#1e293b', sidebar:'#0b1120', text:'#e2e8f0', muted:'#94a3b8', border:'#334155', input:'#0b1220' },
    light:   { bg:'#ffffff', panel:'#f7f7f8', sidebar:'#f9f9fb', text:'#1f2937', muted:'#6b7280', border:'#e5e7eb', input:'#ffffff' },
    midnight:{ bg:'#000000', panel:'#101014', sidebar:'#0a0a0c', text:'#e5e7eb', muted:'#6b7280', border:'#26262b', input:'#101014' },
    forest:  { bg:'#0b1a12', panel:'#12251a', sidebar:'#081410', text:'#e6f0ea', muted:'#8aa596', border:'#1f3a2b', input:'#0d1e15' },
    ocean:   { bg:'#082032', panel:'#0f3040', sidebar:'#061820', text:'#e6f0f5', muted:'#7f9dab', border:'#164a5f', input:'#0a2634' }
  };
  var DEFAULTS = { theme:'dark', accent:'#2563eb', fontSize:15, bubbleStyle:'rounded', markdown:true, showTimestamp:true };
  var STORE_KEY = 'self-extension.settings';

  function loadSettings() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (!raw) return Object.assign({}, DEFAULTS);
      return Object.assign({}, DEFAULTS, JSON.parse(raw));
    } catch (e) { return Object.assign({}, DEFAULTS); }
  }
  function saveSettings() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(settings)); } catch (e) { /* ignore */ }
  }

  var settings = loadSettings();
  var rootStyle = document.documentElement.style;

  function applySettings() {
    var t = THEMES[settings.theme] || THEMES.dark;
    rootStyle.setProperty('--bg', t.bg);
    rootStyle.setProperty('--panel', t.panel);
    rootStyle.setProperty('--sidebar', t.sidebar);
    rootStyle.setProperty('--text', t.text);
    rootStyle.setProperty('--muted', t.muted);
    rootStyle.setProperty('--border', t.border);
    rootStyle.setProperty('--input', t.input);
    rootStyle.setProperty('--user-text', '#ffffff');
    rootStyle.setProperty('--accent', settings.accent);
    rootStyle.setProperty('--user', settings.accent);
    rootStyle.setProperty('--font-size', settings.fontSize + 'px');
    document.body.dataset.bubble = settings.bubbleStyle;
    syncControls();
  }

  function syncControls() {
    document.querySelectorAll('#themeSwatches .swatch').forEach(function (b) {
      b.classList.toggle('active', b.dataset.theme === settings.theme);
    });
    document.querySelectorAll('#accentSwatches .swatch').forEach(function (b) {
      b.classList.toggle('active', b.dataset.accent.toLowerCase() === settings.accent.toLowerCase());
    });
    accentCustom.value = settings.accent;
    fontSizeRange.value = settings.fontSize;
    fontSizeLabel.textContent = settings.fontSize + 'px';
    document.querySelectorAll('#bubbleSeg button').forEach(function (b) {
      b.classList.toggle('active', b.dataset.bubble === settings.bubbleStyle);
    });
    mdToggle.checked = settings.markdown;
    timeToggle.checked = settings.showTimestamp;
  }

  /* ================= Markdown 渲染 ================= */
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderInline(s) {
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return s;
  }

  function renderMarkdown(raw) {
    if (!raw) return '';
    raw = raw.replace(/\r\n?/g, '\n');

    var blocks = [];
    var s = raw.replace(/```([a-zA-Z0-9_+#-]*)[ \t]*\n?([\s\S]*?)```/g, function (m, lang, code) {
      blocks.push({ lang: lang || '', code: code.replace(/\n$/, '') });
      return '\u0000B' + (blocks.length - 1) + '\u0000';
    });

    s = escapeHtml(s);

    function codeBlockHtml(i) {
      var b = blocks[i];
      return '<pre class="code"><div class="code-head"><span>' + escapeHtml(b.lang || 'code') +
        '</span><button type="button" class="copy-btn">复制</button></div><code>' +
        escapeHtml(b.code) + '</code></pre>';
    }
    function isBlank(l) { return /^\s*$/.test(l); }
    function isBlockStart(l) {
      return /^(#{1,6}\s|>\s?|[-*+]\s|\d+\.\s|\|)/.test(l) ||
             /^\s*(---+|\*\*\*+|___+)\s*$/.test(l) ||
             /^\u0000B\d+\u0000$/.test(l);
    }

    var lines = s.split('\n');
    var html = '';
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];
      if (isBlank(line)) { i++; continue; }

      var pm = line.match(/^\u0000B(\d+)\u0000$/);
      if (pm) { html += codeBlockHtml(+pm[1]); i++; continue; }

      var m = line.match(/^(#{1,6})\s+(.*)$/);
      if (m) {
        var lvl = m[1].length;
        html += '<h' + lvl + '>' + renderInline(m[2]) + '</h' + lvl + '>';
        i++; continue;
      }
      if (/^\s*(---+|\*\*\*+|___+)\s*$/.test(line)) { html += '<hr>'; i++; continue; }
      if (/^\s*>\s?/.test(line)) {
        var q = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          q.push(lines[i].replace(/^\s*>\s?/, '')); i++;
        }
        html += '<blockquote>' + renderInline(q.join('<br>')) + '</blockquote>';
        continue;
      }
      if (/^\s*[-*+]\s+/.test(line)) {
        html += '<ul>';
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          html += '<li>' + renderInline(lines[i].replace(/^\s*[-*+]\s+/, '')) + '</li>'; i++;
        }
        html += '</ul>'; continue;
      }
      if (/^\s*\d+\.\s+/.test(line)) {
        html += '<ol>';
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          html += '<li>' + renderInline(lines[i].replace(/^\s*\d+\.\s+/, '')) + '</li>'; i++;
        }
        html += '</ol>'; continue;
      }
      if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
        var header = line.trim().replace(/^\||\|$/g, '').split('|').map(function (c) { return c.trim(); });
        i += 2;
        var rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) {
          rows.push(lines[i].trim().replace(/^\||\|$/g, '').split('|').map(function (c) { return c.trim(); }));
          i++;
        }
        html += '<table><thead><tr>' + header.map(function (h) { return '<th>' + renderInline(h) + '</th>'; }).join('') +
                '</tr></thead><tbody>';
        rows.forEach(function (r) {
          html += '<tr>' + r.map(function (c) { return '<td>' + renderInline(c) + '</td>'; }).join('') + '</tr>';
        });
        html += '</tbody></table>'; continue;
      }

      var p = [line];
      i++;
      while (i < lines.length && !isBlank(lines[i]) && !isBlockStart(lines[i])) {
        p.push(lines[i]); i++;
      }
      html += '<p>' + renderInline(p.join('<br>')) + '</p>';
    }
    html = html.replace(/\u0000B(\d+)\u0000/g, function (m2, idx) { return codeBlockHtml(+idx); });
    return html;
  }

  /* ================= 聊天逻辑 ================= */
  var chat = document.getElementById('chat');
  var chatScroll = document.getElementById('chatScroll');
  var form = document.getElementById('form');
  var input = document.getElementById('input');
  var send = document.getElementById('send');
  var status = document.getElementById('status');
  var messages = []; // { role:'user'|'bot', text, time }

  function now() {
    return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  function scrollBottom() { chatScroll.scrollTop = chatScroll.scrollHeight; }

  function buildMessage(m) {
    var row = document.createElement('div');
    row.className = 'msg-row ' + m.role;
    var col = document.createElement('div');
    col.className = 'msg-col';
    var msg = document.createElement('div');
    msg.className = 'msg';
    if (m.role === 'bot' && settings.markdown) {
      msg.innerHTML = renderMarkdown(m.text);
    } else {
      msg.textContent = m.text;
    }
    col.appendChild(msg);
    if (settings.showTimestamp) {
      var tm = document.createElement('div');
      tm.className = 'msg-time';
      tm.textContent = m.time;
      col.appendChild(tm);
    }
    row.appendChild(col);
    return row;
  }

  function renderAll() {
    chat.innerHTML = '';
    if (!messages.length) {
      var w = document.createElement('div');
      w.className = 'welcome';
      w.innerHTML = '<div class="welcome-icon">✨</div><h2>你好，我是 Self-Extension Agent</h2>' +
        '<p>输入你的指令，我会调用工具完成任务，并在能力不足时自动创建插件扩展自己。</p>' +
        '<div class="hints"><span>上海今天天气怎么样</span><span>帮我写一个计算器插件</span><span>用 **Markdown** 回复</span></div>';
      chat.appendChild(w);
    } else {
      messages.forEach(function (m) { chat.appendChild(buildMessage(m)); });
    }
    scrollBottom();
  }

  function addTyping() {
    var row = document.createElement('div');
    row.className = 'msg-row bot';
    row.innerHTML = '<div class="msg-col"><div class="msg typing"><span></span><span></span><span></span></div></div>';
    chat.appendChild(row);
    scrollBottom();
    return row;
  }

  function setSending(on) {
    send.disabled = on;
    send.textContent = on ? '…' : '↑';
  }

  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
  }

  /* ---------- 事件绑定 ---------- */
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    messages.push({ role: 'user', text: text, time: now() });
    input.value = '';
    autoResize();
    renderAll();
    setSending(true);
    var typing = addTyping();
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (typing.parentNode) typing.parentNode.removeChild(typing);
      messages.push({ role: 'bot', text: data.reply || data.error || '（无响应）', time: now() });
    }).catch(function (err) {
      if (typing.parentNode) typing.parentNode.removeChild(typing);
      messages.push({ role: 'bot', text: '请求失败: ' + err, time: now() });
    }).then(function () {
      setSending(false);
      renderAll();
      input.focus();
    });
  });

  input.addEventListener('input', autoResize);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  document.getElementById('newChat').addEventListener('click', function () {
    messages = [];
    renderAll();
    fetch('/api/reset', { method: 'POST' }).catch(function () { /* ignore */ });
    if (window.innerWidth < 900) document.body.classList.remove('sidebar-open');
  });

  document.getElementById('currentConv').addEventListener('click', function () {
    chatScroll.scrollTo({ top: 0, behavior: 'smooth' });
    if (window.innerWidth < 900) document.body.classList.remove('sidebar-open');
  });

  // 点击欢迎页示例时填入输入框 + 代码块复制
  document.addEventListener('click', function (e) {
    var hint = e.target.closest('.hints span');
    if (hint) { input.value = hint.textContent; autoResize(); input.focus(); }
    var btn = e.target.closest('.copy-btn');
    if (btn) {
      var pre = btn.closest('pre');
      var code = pre ? pre.querySelector('code').textContent : '';
      copyText(code);
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = '复制'; }, 1200);
    }
  });

  function copyText(t) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).catch(function () { fallbackCopy(t); });
    } else { fallbackCopy(t); }
  }
  function fallbackCopy(t) {
    var ta = document.createElement('textarea');
    ta.value = t;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  // 健康检查
  fetch('/api/health').then(function (r) { return r.json(); }).then(function (d) {
    status.innerHTML = '<i class="dot"></i>' + (d.model || '未知');
  }).catch(function () {
    status.innerHTML = '<i class="dot offline"></i>离线';
  });

  /* ---------- 侧边栏 / 设置抽屉开关 ---------- */
  var toggleSidebar = document.getElementById('toggleSidebar');
  var navMask = document.getElementById('navMask');
  var drawerMask = document.getElementById('drawerMask');

  function openSettings() { document.body.classList.add('settings-open'); }
  function closeSettings() { document.body.classList.remove('settings-open'); }

  toggleSidebar.addEventListener('click', function () {
    if (window.innerWidth < 900) {
      document.body.classList.toggle('sidebar-open');
    } else {
      document.body.classList.toggle('sidebar-collapsed');
    }
  });
  navMask.addEventListener('click', function () { document.body.classList.remove('sidebar-open'); });
  document.getElementById('openSettings').addEventListener('click', openSettings);
  document.getElementById('openSettingsHeader').addEventListener('click', openSettings);
  document.getElementById('closeSettings').addEventListener('click', closeSettings);
  drawerMask.addEventListener('click', closeSettings);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeSettings();
      document.body.classList.remove('sidebar-open');
    }
  });

  /* ---------- 设置控件 ---------- */
  var themeSwatches = document.getElementById('themeSwatches');
  var accentSwatches = document.getElementById('accentSwatches');
  var accentCustom = document.getElementById('accentCustom');
  var fontSizeRange = document.getElementById('fontSizeRange');
  var fontSizeLabel = document.getElementById('fontSizeLabel');
  var bubbleSeg = document.getElementById('bubbleSeg');
  var mdToggle = document.getElementById('mdToggle');
  var timeToggle = document.getElementById('timeToggle');
  var resetSettings = document.getElementById('resetSettings');

  themeSwatches.addEventListener('click', function (e) {
    var b = e.target.closest('[data-theme]');
    if (!b) return;
    settings.theme = b.dataset.theme;
    saveSettings(); applySettings();
  });
  accentSwatches.addEventListener('click', function (e) {
    var b = e.target.closest('[data-accent]');
    if (!b) return;
    settings.accent = b.dataset.accent;
    saveSettings(); applySettings();
  });
  accentCustom.addEventListener('input', function (e) {
    settings.accent = e.target.value;
    saveSettings(); applySettings();
  });
  fontSizeRange.addEventListener('input', function (e) {
    settings.fontSize = +e.target.value;
    saveSettings(); applySettings();
  });
  bubbleSeg.addEventListener('click', function (e) {
    var b = e.target.closest('[data-bubble]');
    if (!b) return;
    settings.bubbleStyle = b.dataset.bubble;
    saveSettings(); applySettings();
  });
  mdToggle.addEventListener('change', function () {
    settings.markdown = mdToggle.checked;
    saveSettings(); renderAll();
  });
  timeToggle.addEventListener('change', function () {
    settings.showTimestamp = timeToggle.checked;
    saveSettings(); renderAll();
  });
  resetSettings.addEventListener('click', function () {
    settings = Object.assign({}, DEFAULTS);
    saveSettings(); applySettings(); renderAll();
  });

  /* ---------- 初始化 ---------- */
  applySettings();
  renderAll();
  input.focus();
})();
</script>
</body>
</html>
"""
