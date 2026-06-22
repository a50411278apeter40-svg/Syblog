content = open('/app/syblog_project/templates/blog/ai_webdev_project_js.html').read()

# ── 1) 전역 변수 블록 교체 (bgTaskActive, bgTaskId 추가) ──
old_globals = '''const PROJECT_ID = {{ project.pk }};
const CSRF = '{{ csrf_token }}';
let activeFile = null;
let toolLogCount = 0;
let isSending = false;
let bgCancelFlag = false;
let bgTaskActive = false;
let autosaveTimer = null;
let lastSavedContent = '';'''

new_globals = '''const PROJECT_ID = {{ project.pk }};
const CSRF = '{{ csrf_token }}';
let activeFile = null;
let toolLogCount = 0;
let isSending = false;
let bgCancelFlag = false;
let bgTaskActive = false;
let bgTaskId = null;        // 서버 task ID
let autosaveTimer = null;
let lastSavedContent = '';'''

if old_globals in content:
    content = content.replace(old_globals, new_globals, 1)
    print("✅ 전역 변수 업데이트")
else:
    print("⚠️ 전역 변수 패턴 불일치 (계속 진행)")

# ── 2) bg-progress 관련 함수들 → 채팅 상태 표시로 교체 ──
old_bg_funcs = '''// 백그라운드 진행 표시기
// ════════════════════════════════════════════════
function showBgProgress(text, pct) {
  const el = document.getElementById('bg-progress');
  if (el) {
    el.style.display = 'flex';
    const textEl = document.getElementById('bg-progress-text');
    if (textEl) textEl.textContent = text || 'AI 작업 중...';
    if (pct !== undefined) {
      const bar = document.getElementById('bg-progress-bar-inner');
      if (bar) bar.style.width = Math.min(pct, 98) + '%';
    }
  }
  bgTaskActive = true;
  bgCancelFlag = false;
}

function updateBgProgress(text, pct) {
  if (!bgTaskActive) return;
  const textEl = document.getElementById('bg-progress-text');
  if (textEl) textEl.textContent = text;
  if (pct !== undefined) {
    const bar = document.getElementById('bg-progress-bar-inner');
    if (bar) bar.style.width = Math.min(pct, 98) + '%';
  }
}

function hideBgProgress() {
  const bar = document.getElementById('bg-progress-bar-inner');
  if (bar) bar.style.width = '100%';
  setTimeout(() => {
    const el = document.getElementById('bg-progress');
    if (el) el.style.display = 'none';
    if (bar) bar.style.width = '0%';
  }, 500);
  bgTaskActive = false;
}

function cancelBgTask() {
  bgCancelFlag = true;
  hideBgProgress();
  addToolLog('🛑 작업 취소됨', 'error');
}'''

new_bg_funcs = '''// 진행 상태 (배너 없이 채팅창에만 표시)
// ════════════════════════════════════════════════
let _statusBubble = null;

function showBgProgress(text) {
  bgTaskActive = true;
  bgCancelFlag = false;
  // 채팅창에 상태 버블 업데이트
  _updateStatusBubble(text);
}

function updateBgProgress(text) {
  if (!bgTaskActive) return;
  _updateStatusBubble(text);
  // 서버 task 라벨도 업데이트 (throttled)
  if (bgTaskId) {
    clearTimeout(updateBgProgress._t);
    updateBgProgress._t = setTimeout(() => {
      fetch(`/blog/ai-webdev/${PROJECT_ID}/task/upsert/`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
        body: JSON.stringify({action: 'update', task_id: bgTaskId, label: text})
      }).catch(() => {});
    }, 800);
  }
}

function _updateStatusBubble(text) {
  if (_statusBubble) {
    _statusBubble.innerHTML = `<span style="color:#8b949e;font-size:.82rem;">⏳ ${escHtml(text)}</span>`;
    document.getElementById('chat-messages').scrollTop = 9999;
  }
}

function hideBgProgress() {
  bgTaskActive = false;
  if (_statusBubble) {
    _statusBubble.remove();
    _statusBubble = null;
  }
}

function cancelBgTask() {
  bgCancelFlag = true;
  hideBgProgress();
  if (bgTaskId) {
    fetch(`/blog/ai-webdev/${PROJECT_ID}/task/upsert/`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
      body: JSON.stringify({action: 'cancel', task_id: bgTaskId})
    }).catch(() => {});
    bgTaskId = null;
  }
}'''

if old_bg_funcs in content:
    content = content.replace(old_bg_funcs, new_bg_funcs, 1)
    print("✅ bg-progress 함수 교체")
else:
    print("❌ bg-progress 함수 패턴 불일치")
    idx = content.find('function showBgProgress')
    print(f"  showBgProgress 위치: {idx}")
    print(repr(content[idx:idx+200]))

# ── 3) loadChatHistory에서 running_task 처리 추가 ──
old_load_history = '''async function loadChatHistory() {
  try {
    const r = await fetch(`/blog/ai-webdev/${PROJECT_ID}/history/`);
    const d = await r.json();
    const msgs = document.getElementById('chat-messages');
    msgs.innerHTML = '';
    if (!d.history || d.history.length === 0) {
      msgs.innerHTML = `
        <div style="text-align:center;padding:30px 16px;color:#9ca3af;">
          <div style="font-size:2.5rem;">🤖</div>
          <p style="margin-top:10px;font-size:.9rem;line-height:1.8;">
            AI에게 무엇을 만들지 말씀해주세요!<br>
            <small>"React 투두앱 만들어줘"<br>"Bootstrap 포트폴리오"<br>"Flask REST API"</small>
          </p>
        </div>`;
      return;
    }
    d.history.forEach(s => renderMsg(s.role, s.content, s.tool_calls || []));
    msgs.scrollTop = msgs.scrollHeight;
  } catch(e) { console.error('이력 로딩 실패:', e); }
}'''

new_load_history = '''async function loadChatHistory() {
  try {
    const r = await fetch(`/blog/ai-webdev/${PROJECT_ID}/history/`);
    const d = await r.json();
    const msgs = document.getElementById('chat-messages');
    msgs.innerHTML = '';
    if (!d.history || d.history.length === 0) {
      msgs.innerHTML = `
        <div style="text-align:center;padding:30px 16px;color:#8b949e;">
          <div style="font-size:2.5rem;">🤖</div>
          <p style="margin-top:10px;font-size:.9rem;line-height:1.8;">
            AI에게 무엇을 만들지 말씀해주세요!<br>
            <small style="color:#484f58;">"React 투두앱 만들어줘"<br>"Bootstrap 포트폴리오"<br>"Flask REST API"</small>
          </p>
        </div>`;
    } else {
      d.history.forEach(s => renderMsg(s.role, s.content, s.tool_calls || []));
      msgs.scrollTop = msgs.scrollHeight;
    }

    // 서버에서 실행중인 task가 있으면 표시
    if (d.running_task) {
      const div = document.createElement('div');
      div.className = 'msg-ai';
      div.id = 'running-task-indicator';
      div.innerHTML = `<div class="bubble" style="background:#1c2128;border:1px solid #3d444d;">
        <span style="color:#f0c000;">⏳ ${escHtml(d.running_task.label)}</span>
        <div style="font-size:.75rem;color:#484f58;margin-top:4px;">백그라운드에서 작업 중입니다. 잠시 후 자동으로 업데이트됩니다.</div>
      </div>`;
      msgs.appendChild(div);
      msgs.scrollTop = msgs.scrollHeight;
      // 5초마다 이력 갱신
      setTimeout(pollRunningTask, 5000);
    }
  } catch(e) { console.error('이력 로딩 실패:', e); }
}

async function pollRunningTask() {
  if (isSending) return;
  try {
    const r = await fetch(`/blog/ai-webdev/${PROJECT_ID}/task/status/`);
    const d = await r.json();
    const indicator = document.getElementById('running-task-indicator');
    if (!d.running) {
      // 완료됨 → 이력 새로고침
      if (indicator) indicator.remove();
      await loadChatHistory();
      return;
    }
    // 아직 실행중 → 라벨 업데이트
    if (indicator) {
      indicator.querySelector('.bubble').innerHTML = `
        <span style="color:#f0c000;">⏳ ${escHtml(d.label)}</span>
        <div style="font-size:.75rem;color:#484f58;margin-top:4px;">백그라운드에서 작업 중입니다. 잠시 후 자동으로 업데이트됩니다.</div>`;
    }
    setTimeout(pollRunningTask, 5000);
  } catch(e) {
    setTimeout(pollRunningTask, 8000);
  }
}'''

if old_load_history in content:
    content = content.replace(old_load_history, new_load_history, 1)
    print("✅ loadChatHistory 교체")
else:
    print("❌ loadChatHistory 패턴 불일치")
    idx = content.find('async function loadChatHistory()')
    print(f"  위치: {idx}")

# ── 4) sendChat 첫 부분에 task 시작 로직 추가 ──
old_send_start = '''  isSending = true;
  bgCancelFlag = false;
  input.value = '';
  const btn = document.getElementById('send-btn');
  btn.disabled = true;
  btn.textContent = '⏳';

  appendUserMsg(msg);
  addToolLog(`💬 전송: ${msg.slice(0, 60)}`, 'info');
  showBgProgress('AI가 응답 생성 중...', 5);'''

new_send_start = '''  isSending = true;
  bgCancelFlag = false;
  bgTaskId = null;
  input.value = '';
  const btn = document.getElementById('send-btn');
  btn.disabled = true;
  btn.textContent = '⏳';

  appendUserMsg(msg);

  // 서버에 task 시작 등록 (새로고침 후 복원용)
  fetch(`/blog/ai-webdev/${PROJECT_ID}/task/upsert/`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
    body: JSON.stringify({action: 'start', label: 'AI 응답 생성 중...'})
  }).then(r => r.json()).then(d => { if (d.task_id) bgTaskId = d.task_id; }).catch(() => {});

  // 상태 버블 생성 (채팅창 내)
  const statusDiv = document.createElement('div');
  statusDiv.className = 'msg-ai';
  statusDiv.id = 'chat-status-bubble';
  statusDiv.innerHTML = '<div class="bubble" style="background:#1c2128;border:1px solid #30363d;"><span style="color:#8b949e;font-size:.82rem;">⏳ AI가 응답 준비 중...</span></div>';
  document.getElementById('chat-messages').appendChild(statusDiv);
  document.getElementById('chat-messages').scrollTop = 9999;
  _statusBubble = statusDiv.querySelector('.bubble');

  showBgProgress('AI가 응답 생성 중...');'''

if old_send_start in content:
    content = content.replace(old_send_start, new_send_start, 1)
    print("✅ sendChat 시작 부분 교체")
else:
    print("❌ sendChat 시작 패턴 불일치")
    idx = content.find('isSending = true;')
    print(f"  isSending 위치: {idx}")
    print(repr(content[idx:idx+300]))

# ── 5) sendChat에서 `단계 X` 텍스트 제거 ──
old_loop_progress = '''      updateBgProgress(`AI 응답 중 (단계 ${loopCount})...`, 10 + loopCount * 12);'''
new_loop_progress = '''      // 상태 버블은 유지 (단계 표시 없음)'''

if old_loop_progress in content:
    content = content.replace(old_loop_progress, new_loop_progress, 1)
    print("✅ 단계 표시 제거")
else:
    print("⚠️ 단계 표시 패턴 불일치")

# ── 6) sendChat 완료 부분에 task done 처리 추가 ──
old_send_end = '''  if (loopCount >= MAX_LOOPS) addToolLog('⚠️ 도구 실행 루프 최대 횟수 도달', 'error');
  addToolLog('✅ 작업 완료', 'success');
  executedToolHashes.clear();
  isSending = false;
  btn.disabled = false;
  btn.textContent = '▶ 전송';
  hideBgProgress();
  await refreshFiles();
}'''

new_send_end = '''  if (loopCount >= MAX_LOOPS) addToolLog('⚠️ 도구 실행 루프 최대 횟수 도달', 'error');
  executedToolHashes.clear();

  // 상태 버블 제거
  const sb = document.getElementById('chat-status-bubble');
  if (sb) sb.remove();
  _statusBubble = null;

  // 서버 task 완료 처리
  if (bgTaskId) {
    fetch(`/blog/ai-webdev/${PROJECT_ID}/task/upsert/`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
      body: JSON.stringify({action: 'done', task_id: bgTaskId, label: '작업 완료'})
    }).catch(() => {});
    bgTaskId = null;
  }

  isSending = false;
  btn.disabled = false;
  btn.textContent = '▶ 전송';
  hideBgProgress();
  await refreshFiles();
}'''

if old_send_end in content:
    content = content.replace(old_send_end, new_send_end, 1)
    print("✅ sendChat 완료 부분 교체")
else:
    print("❌ sendChat 완료 패턴 불일치")
    idx = content.find("addToolLog('✅ 작업 완료', 'success');")
    print(f"  위치: {idx}")

# ── 7) sendChat 오류 처리에도 task error 추가 ──
old_send_err = '''    } catch (e) {
      bubble.innerHTML = `<span style="color:#ef4444;">연결 오류: ${escHtml(e.message)}</span>`;
      addToolLog(`❌ 오류: ${e.message}`, 'error');
      break;
    }
  }'''

new_send_err = '''    } catch (e) {
      bubble.innerHTML = `<span style="color:#ef4444;">연결 오류: ${escHtml(e.message)}</span>`;
      addToolLog(`❌ 오류: ${e.message}`, 'error');
      if (bgTaskId) {
        fetch(`/blog/ai-webdev/${PROJECT_ID}/task/upsert/`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
          body: JSON.stringify({action: 'error', task_id: bgTaskId, error_msg: e.message})
        }).catch(() => {});
        bgTaskId = null;
      }
      break;
    }
  }'''

if old_send_err in content:
    content = content.replace(old_send_err, new_send_err, 1)
    print("✅ sendChat 오류 처리 교체")
else:
    print("⚠️ sendChat 오류 처리 패턴 불일치")

# ── 8) DOMContentLoaded에 모바일 키보드 가림 방지 코드 추가 ──
old_dom_init = '''document.addEventListener('DOMContentLoaded', async () => {
  document.body.classList.add('webbuilder-page');

  // 리사이저 초기화
  initResizer('resizer-left', document.getElementById('sidebar'), document.getElementById('editor-pane'));
  initResizer('resizer-right', document.getElementById('editor-pane'), document.getElementById('right-panel'));

  // 대화 이력 + 파일 트리 로딩
  await loadChatHistory();
  await refreshFiles();
  updateCreditBadge();

  // 모바일 초기 상태: AI 채팅 패널 표시
  if (isMobile()) {
    document.getElementById('right-panel').classList.add('mobile-active');
    document.getElementById('editor-pane').classList.remove('mobile-active');
    setMobileTabActive('mtab-chat');
    switchTab('chat');
  }
});'''

new_dom_init = '''document.addEventListener('DOMContentLoaded', async () => {
  document.body.classList.add('webbuilder-page');

  // 리사이저 초기화
  initResizer('resizer-left', document.getElementById('sidebar'), document.getElementById('editor-pane'));
  initResizer('resizer-right', document.getElementById('editor-pane'), document.getElementById('right-panel'));

  // 대화 이력 + 파일 트리 로딩
  await loadChatHistory();
  await refreshFiles();
  updateCreditBadge();

  // 모바일 초기 상태: AI 채팅 패널 표시
  if (isMobile()) {
    document.getElementById('right-panel').classList.add('mobile-active');
    document.getElementById('editor-pane').classList.remove('mobile-active');
    setMobileTabActive('mtab-chat');
    switchTab('chat');
  }

  // ── 모바일 키보드 올라올 때 입력창 가림 방지 ──
  const chatInput = document.getElementById('chat-input');
  const chatPane  = document.getElementById('chat-pane');

  function adjustForKeyboard() {
    if (!isMobile()) return;
    // visual viewport 지원 브라우저 (iOS 13+)
    const vvh = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    const winH = window.innerHeight;
    const kbHeight = Math.max(0, winH - vvh);
    const tabBarH = 54;
    // chat-pane 높이를 키보드 위까지 맞춤
    if (kbHeight > 50) {
      chatPane.style.maxHeight = (vvh - tabBarH - 56) + 'px';
      chatPane.style.height    = (vvh - tabBarH - 56) + 'px';
      // 입력창이 보이도록 스크롤
      setTimeout(() => {
        document.getElementById('chat-messages').scrollTop = 9999;
        chatInput.scrollIntoView({block: 'nearest', behavior: 'smooth'});
      }, 100);
    } else {
      chatPane.style.maxHeight = '';
      chatPane.style.height    = '';
    }
  }

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', adjustForKeyboard);
    window.visualViewport.addEventListener('scroll', adjustForKeyboard);
  } else {
    window.addEventListener('resize', adjustForKeyboard);
  }

  chatInput.addEventListener('focus', () => {
    if (isMobile()) {
      setTimeout(adjustForKeyboard, 300);
      setTimeout(() => {
        document.getElementById('chat-messages').scrollTop = 9999;
      }, 400);
    }
  });

  chatInput.addEventListener('blur', () => {
    if (isMobile()) {
      setTimeout(() => {
        chatPane.style.maxHeight = '';
        chatPane.style.height    = '';
      }, 200);
    }
  });
});'''

if old_dom_init in content:
    content = content.replace(old_dom_init, new_dom_init, 1)
    print("✅ DOMContentLoaded 교체 (키보드 처리 추가)")
else:
    print("❌ DOMContentLoaded 패턴 불일치")
    idx = content.find("document.addEventListener('DOMContentLoaded'")
    print(f"  위치: {idx}")

open('/app/syblog_project/templates/blog/ai_webdev_project_js.html', 'w').write(content)
print("\n✅ JS 파일 저장 완료")
