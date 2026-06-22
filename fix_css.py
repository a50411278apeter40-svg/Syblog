content = open('/app/syblog_project/templates/blog/ai_webdev_project.html').read()

# Find CSS block boundaries
css_start = content.find('{% block extra_css %}\n<style>')
css_end = content.find('</style>\n{% endblock %}')

if css_start == -1 or css_end == -1:
    print(f"❌ CSS 블록 못 찾음. css_start={css_start}, css_end={css_end}")
    # 다른 패턴 시도
    css_start = content.find('{% block extra_css %}')
    css_end = content.find('{% endblock %}\n\n{% block main_area %}')
    print(f"재시도: css_start={css_start}, css_end={css_end}")
else:
    print(f"✅ CSS 블록 위치: {css_start}~{css_end}")

new_css = '''{% block extra_css %}
<style>
/* ══════════════════════════════════════════
   기본 & 레이아웃
══════════════════════════════════════════ */
* { box-sizing: border-box; }
body.webbuilder-page { overflow: hidden; }

/* ══════════════════════════════════════════
   모바일 탭 바 (하단 네비게이션)
══════════════════════════════════════════ */
#mobile-tab-bar {
  display: none;
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 200;
  background: #161b22; border-top: 2px solid #30363d;
  padding: 4px 0 max(6px, env(safe-area-inset-bottom));
}
#mobile-tab-bar button {
  flex: 1; background: none; border: none;
  color: #8b949e; font-size: 0.68rem; font-weight: 500;
  display: flex; flex-direction: column; align-items: center;
  gap: 3px; cursor: pointer; padding: 6px 2px;
  transition: color 0.15s;
  -webkit-tap-highlight-color: transparent;
}
#mobile-tab-bar button .icon { font-size: 1.25rem; line-height: 1; }
#mobile-tab-bar button.active { color: #7c6aff; }
#mobile-tab-bar button.active .icon { filter: drop-shadow(0 0 4px #7c6aff88); }

/* ══════════════════════════════════════════
   워크벤치
══════════════════════════════════════════ */
#workbench {
  display: flex;
  height: calc(100vh - 56px);
  gap: 0;
  position: relative;
  background: #0d1117;
}

/* ══════════════════════════════════════════
   사이드바
══════════════════════════════════════════ */
#sidebar {
  width: 220px; min-width: 180px; max-width: 320px;
  background: #161b22; color: #e6edf3;
  display: flex; flex-direction: column;
  border-right: 1px solid #30363d;
  transition: transform 0.25s ease;
  z-index: 100;
}
#sidebar-header {
  padding: 10px 14px; background: #0d1117;
  font-size: .85rem; font-weight: 700; color: #58a6ff;
  border-bottom: 1px solid #30363d;
  display: flex; align-items: center; gap: 8px;
  letter-spacing: 0.02em;
}
#file-tree { flex: 1; overflow-y: auto; padding: 6px 0; font-size: .82rem; }
.tree-item {
  padding: 6px 12px; cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  border-radius: 6px; margin: 1px 6px;
  transition: background .12s; min-height: 32px;
  color: #c9d1d9; font-size: .82rem;
}
.tree-item:hover { background: #21262d; color: #e6edf3; }
.tree-item.active { background: #1f2b3e; color: #79c0ff; border-left: 2px solid #58a6ff; }
.tree-item.is-dir { color: #79c0ff; font-weight: 600; }
.tree-item.is-file { color: #c9d1d9; }
#sidebar-actions {
  padding: 8px 10px; border-top: 1px solid #30363d;
  display: flex; gap: 5px; flex-wrap: wrap;
}
#sidebar-actions button {
  flex: 1; min-width: 42px;
  font-size: .72rem; padding: 6px 4px;
  border: 1px solid #30363d; border-radius: 6px; cursor: pointer;
  background: #21262d; color: #c9d1d9;
  font-weight: 500; transition: all .15s;
}
#sidebar-actions button:hover { background: #30363d; color: #e6edf3; }

/* ══════════════════════════════════════════
   에디터 패널
══════════════════════════════════════════ */
#editor-pane {
  flex: 1; display: flex; flex-direction: column;
  background: #0d1117; min-width: 0;
}
#editor-tabs {
  background: #161b22; border-bottom: 1px solid #30363d;
  display: flex; align-items: center; padding: 0 8px;
  min-height: 38px; overflow-x: auto; gap: 2px;
  scrollbar-width: thin;
}
.editor-tab {
  padding: 7px 14px; font-size: .8rem; color: #8b949e;
  cursor: pointer; border-bottom: 2px solid transparent;
  white-space: nowrap; display: flex; align-items: center; gap: 6px;
  transition: color .15s;
}
.editor-tab:hover { color: #c9d1d9; }
.editor-tab.active { color: #e6edf3; border-bottom-color: #58a6ff; background: #0d1117; }
.editor-tab .tab-close { opacity: .5; font-size: .78rem; padding: 0 3px; }
.editor-tab .tab-close:hover { opacity: 1; color: #f85149; }
#file-path-bar {
  background: #161b22; padding: 4px 12px;
  font-size: .77rem; color: #8b949e;
  display: flex; align-items: center; gap: 8px;
  border-bottom: 1px solid #21262d;
}
#code-editor {
  flex: 1; resize: none; border: none; outline: none;
  background: #0d1117; color: #e6edf3;
  font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
  font-size: .87rem; line-height: 1.65;
  padding: 14px 18px; tab-size: 2;
  -webkit-overflow-scrolling: touch;
  caret-color: #58a6ff;
}
#editor-footer {
  background: #1f6feb; color: #fff;
  padding: 3px 12px; font-size: .73rem;
  display: flex; gap: 12px; align-items: center;
  font-weight: 500;
}
#autosave-indicator {
  margin-left: auto; display: flex; align-items: center;
  gap: 5px; font-size: .72rem;
}
.autosave-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #3fb950;
}
.autosave-dot.saving { background: #f0c000; animation: blink 0.6s infinite; }
.autosave-dot.error { background: #f85149; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
@keyframes spin { to { transform: rotate(360deg); } }

/* ══════════════════════════════════════════
   오른쪽 패널
══════════════════════════════════════════ */
#right-panel {
  width: 420px; min-width: 340px;
  display: flex; flex-direction: column;
  background: #161b22; border-left: 1px solid #30363d;
}
#right-tabs {
  background: #0d1117; border-bottom: 1px solid #30363d;
  display: flex; min-height: 40px; overflow-x: auto;
  scrollbar-width: none;
}
#right-tabs::-webkit-scrollbar { display: none; }
.right-tab {
  flex: 1; border: none; background: none;
  padding: 10px 4px; font-size: .78rem; font-weight: 600;
  cursor: pointer; color: #8b949e;
  border-bottom: 2px solid transparent; transition: all .15s;
  white-space: nowrap; min-width: 58px;
  letter-spacing: 0.01em;
}
.right-tab:hover { color: #c9d1d9; background: #161b22; }
.right-tab.active { color: #79c0ff; border-bottom-color: #58a6ff; background: #161b22; }

/* ══════════════════════════════════════════
   미리보기
══════════════════════════════════════════ */
#preview-pane { flex: 1; display: none; flex-direction: column; }
#preview-toolbar {
  padding: 7px 10px; background: #161b22;
  border-bottom: 1px solid #30363d;
  display: flex; gap: 6px; align-items: center;
}
#preview-url {
  flex: 1; font-size: .8rem; color: #8b949e;
  background: #0d1117; border: 1px solid #30363d;
  border-radius: 6px; padding: 4px 10px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
#preview-iframe { flex: 1; border: none; width: 100%; }

/* ══════════════════════════════════════════
   도구 로그
══════════════════════════════════════════ */
#tool-pane { flex: 1; display: none; flex-direction: column; overflow: hidden; }
#tool-log-area {
  flex: 1; overflow-y: auto; padding: 12px;
  font-family: 'JetBrains Mono', 'Courier New', monospace; font-size: .8rem;
  background: #0d1117; color: #e6edf3; line-height: 1.5;
}
.tool-log-entry {
  margin: 3px 0; padding: 5px 10px; border-radius: 5px;
  border-left: 3px solid; word-break: break-all;
}
.tool-log-entry.info    { border-color: #58a6ff; background: rgba(88,166,255,.1); color: #a5c8ff; }
.tool-log-entry.success { border-color: #3fb950; background: rgba(63,185,80,.1); color: #56d364; }
.tool-log-entry.error   { border-color: #f85149; background: rgba(248,81,73,.1); color: #ff7b72; }
.tool-log-entry.tool    { border-color: #d2a8ff; background: rgba(210,168,255,.1); color: #d2a8ff; }
.tool-log-entry.terminal { border-color: #ffa657; background: rgba(255,166,87,.1); color: #ffa657; white-space: pre-wrap; }

/* ══════════════════════════════════════════
   AI 채팅
══════════════════════════════════════════ */
#chat-pane { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #161b22; }
#chat-messages {
  flex: 1; overflow-y: auto; padding: 14px 12px;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin; scrollbar-color: #30363d transparent;
}
.msg-user { text-align: right; margin: 8px 0; }
.msg-user .bubble {
  display: inline-block; background: #1f6feb; color: #fff;
  padding: 9px 14px; border-radius: 16px 16px 4px 16px;
  max-width: 85%; font-size: .9rem; text-align: left;
  word-break: break-word; line-height: 1.5;
  box-shadow: 0 2px 8px rgba(31,111,235,.3);
}
.msg-ai { text-align: left; margin: 8px 0; }
.msg-ai .bubble {
  display: inline-block; background: #21262d; color: #e6edf3;
  padding: 9px 14px; border-radius: 16px 16px 16px 4px;
  max-width: 92%; font-size: .9rem; word-break: break-word;
  line-height: 1.55; border: 1px solid #30363d;
}
.msg-ai .bubble pre {
  background: #0d1117; color: #e6edf3; padding: 10px 12px;
  border-radius: 8px; font-size: .8rem;
  overflow-x: auto; margin: 8px 0; white-space: pre-wrap;
  border: 1px solid #30363d;
}
.msg-ai .bubble code {
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  background: #0d1117; padding: 1px 5px; border-radius: 4px;
  font-size: .85em; color: #79c0ff;
}
.tool-call-badge {
  background: #2d1f0e; border: 1px solid #ffa657; border-radius: 6px;
  padding: 3px 10px; font-size: .76rem; margin: 3px 0;
  display: inline-block; word-break: break-all; color: #ffa657;
}
#chat-input-area {
  border-top: 1px solid #30363d; padding: 10px;
  background: #161b22;
}
#chat-input {
  width: 100%; border: 1.5px solid #30363d;
  border-radius: 10px; padding: 9px 14px; font-size: 16px;
  resize: none; outline: none; font-family: inherit;
  transition: border-color .15s;
  background: #0d1117; color: #e6edf3;
  line-height: 1.5;
}
#chat-input::placeholder { color: #484f58; }
#chat-input:focus { border-color: #58a6ff; }
#chat-send-row {
  display: flex; justify-content: space-between;
  align-items: center; margin-top: 8px;
}
#send-btn {
  background: linear-gradient(135deg, #1f6feb, #7c6aff);
  color: #fff; border: none; border-radius: 8px;
  padding: 8px 20px; font-size: .87rem; font-weight: 600; cursor: pointer;
  min-width: 72px; transition: opacity .15s;
  box-shadow: 0 2px 8px rgba(31,111,235,.4);
}
#send-btn:hover { opacity: .9; }
#send-btn:disabled { opacity: .4; cursor: not-allowed; }
.credit-info { font-size: .76rem; color: #8b949e; }

/* ══════════════════════════════════════════
   배포 패널
══════════════════════════════════════════ */
#deploy-pane {
  flex: 1; display: none; flex-direction: column;
  padding: 16px; overflow-y: auto; background: #161b22;
  -webkit-overflow-scrolling: touch;
}
#deploy-pane h5 { color: #e6edf3; font-size: .95rem; font-weight: 700; }
#deploy-pane p, #deploy-pane label { color: #8b949e; font-size: .85rem; }
#deploy-log {
  background: #0d1117; color: #e6edf3; border-radius: 10px;
  padding: 12px 14px; font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: .8rem; min-height: 150px; overflow-y: auto;
  white-space: pre-wrap; margin-bottom: 12px; border: 1px solid #30363d;
}
.deploy-url-box {
  background: #0f2d1f; border: 2px solid #3fb950;
  border-radius: 10px; padding: 12px 16px; text-align: center; color: #56d364;
}
#deploy-pane button {
  background: #238636; color: #fff; border: none; border-radius: 8px;
  padding: 9px 20px; font-size: .87rem; font-weight: 600; cursor: pointer;
  transition: background .15s;
}
#deploy-pane button:hover { background: #2ea043; }

/* ══════════════════════════════════════════
   터미널
══════════════════════════════════════════ */
#terminal-pane { flex: 1; display: none; flex-direction: column; background: #0d1117; }
#terminal-output {
  flex: 1; background: #0d1117; color: #e6edf3;
  font-family: 'JetBrains Mono', 'Courier New', monospace; font-size: .83rem;
  padding: 12px 14px; overflow-y: auto; white-space: pre-wrap;
  line-height: 1.55; -webkit-overflow-scrolling: touch;
  scrollbar-width: thin; scrollbar-color: #30363d transparent;
}
#terminal-input-row {
  display: flex; border-top: 1px solid #30363d;
  background: #161b22; padding: 8px 12px; gap: 8px; align-items: center;
}
#terminal-cmd {
  flex: 1; background: transparent; border: none; outline: none;
  color: #e6edf3; font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 16px; caret-color: #3fb950;
}
#terminal-cmd::placeholder { color: #484f58; }
#terminal-run {
  background: #238636; color: #fff; border: none; border-radius: 6px;
  padding: 6px 14px; font-size: .8rem; cursor: pointer; font-weight: 600;
  transition: background .15s; white-space: nowrap;
}
#terminal-run:hover { background: #2ea043; }

/* ══════════════════════════════════════════
   리사이저
══════════════════════════════════════════ */
.resizer { width: 4px; background: #21262d; cursor: col-resize; flex-shrink: 0; transition: background .15s; }
.resizer:hover { background: #58a6ff; }

/* ══════════════════════════════════════════
   백그라운드 진행 표시기
══════════════════════════════════════════ */
#bg-progress {
  position: fixed; top: 56px; left: 0; right: 0; z-index: 500;
  display: none; background: #161b22;
  padding: 8px 16px; border-bottom: 1px solid #30363d;
  align-items: center; gap: 10px;
}
#bg-progress .spinner {
  width: 16px; height: 16px; border: 2px solid #7c6aff;
  border-top-color: transparent; border-radius: 50%;
  animation: spin 0.7s linear infinite; flex-shrink: 0;
}
#bg-progress-text { color: #c9d1d9; font-size: .84rem; font-weight: 500; flex: 1; }
#bg-progress-bar-wrap {
  width: 120px; height: 5px; background: #30363d; border-radius: 3px; overflow: hidden;
}
#bg-progress-bar-inner {
  height: 100%; background: linear-gradient(90deg, #7c6aff, #56d364);
  border-radius: 3px; transition: width 0.3s ease;
}
#bg-cancel-btn {
  background: #da3633; color: #fff; border: none; border-radius: 6px;
  padding: 4px 12px; font-size: .78rem; cursor: pointer; font-weight: 600;
}

/* ══════════════════════════════════════════
   사이드바 오버레이
══════════════════════════════════════════ */
#sidebar-overlay {
  display: none; position: fixed; inset: 0; z-index: 299;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(2px);
}
#sidebar-overlay.visible { display: block; }

/* ══════════════════════════════════════════
   버튼 공통
══════════════════════════════════════════ */
button { touch-action: manipulation; }

/* ══════════════════════════════════════════
   모바일 (768px 이하)
══════════════════════════════════════════ */
@media (max-width: 768px) {
  body.webbuilder-page { overflow: hidden; }

  #workbench {
    flex-direction: column;
    height: calc(100vh - 56px - 54px);
  }

  #mobile-tab-bar { display: flex; }

  #sidebar {
    position: fixed; top: 56px; left: 0; bottom: 54px;
    width: 82vw !important; max-width: 300px !important; min-width: unset !important;
    transform: translateX(-100%);
    box-shadow: 6px 0 24px rgba(0,0,0,0.7);
    z-index: 300;
  }
  #sidebar.open { transform: translateX(0); }

  #editor-pane {
    flex: 1; width: 100%;
    display: none;
  }
  #editor-pane.mobile-active { display: flex; }

  #right-panel {
    width: 100% !important; min-width: unset !important;
    border-left: none !important;
    display: none; flex: 1;
  }
  #right-panel.mobile-active { display: flex; }

  .resizer { display: none; }

  #right-tabs { overflow-x: auto; }
  .right-tab { min-width: 56px; font-size: .72rem; padding: 9px 3px; }

  #code-editor { font-size: 14px; padding: 10px 12px; }
  #chat-input { font-size: 16px; }
  #editor-footer { font-size: .67rem; padding: 3px 8px; gap: 6px; }

  /* 채팅 버블 조금 더 크게 */
  .msg-user .bubble, .msg-ai .bubble { font-size: .88rem; }

  /* 터미널 폰트 */
  #terminal-output { font-size: .82rem; padding: 10px 12px; }
  #terminal-cmd { font-size: 16px; }
}

/* 초소형 (480px 이하) */
@media (max-width: 480px) {
  #sidebar { width: 88vw !important; }
  .right-tab { font-size: .68rem; min-width: 50px; }
  #code-editor { font-size: 13px; }
  .msg-user .bubble, .msg-ai .bubble { font-size: .85rem; }
}
</style>
{% endblock %}'''

# Replace CSS block
css_block_start = content.find('{% block extra_css %}')
css_block_end = content.find('{% endblock %}\n\n{% block main_area %}')
if css_block_end == -1:
    css_block_end = content.find('{% endblock %}\n\n{% block main_area %}')
if css_block_end == -1:
    css_block_end = content.find('\n{% endblock %}\n\n{% block main_area %}')

print(f"CSS start={css_block_start}, end={css_block_end}")

if css_block_start != -1 and css_block_end != -1:
    # endblock 이후 텍스트 보존
    after = content[css_block_end + len('{% endblock %}'):]
    new_content = content[:css_block_start] + new_css + after
    open('/app/syblog_project/templates/blog/ai_webdev_project.html', 'w').write(new_content)
    print("✅ CSS 교체 완료")
    # 검증
    result = open('/app/syblog_project/templates/blog/ai_webdev_project.html').read()
    print(f"파일 길이: {len(result)}")
    blk = [(i, l) for i, l in enumerate(result.splitlines()) if 'block' in l and '%}' in l]
    for i, l in blk:
        print(f"  line {i+1}: {l.strip()}")
else:
    print("❌ CSS 블록 경계를 못 찾음")
    # 디버그
    idx1 = content.find('{% block extra_css %}')
    idx2 = content.find('{% block main_area %}')
    print(f"extra_css at {idx1}, main_area at {idx2}")
    print(repr(content[idx1:idx1+50]))
    print(repr(content[idx2-60:idx2+30]))
