content = open('/app/syblog_project/templates/blog/ai_webdev_project_js.html').read()

old_js = '''// ════════════════════════════════════════════════
// 터미널
// ════════════════════════════════════════════════
function runTerminal() {
  const cmd = document.getElementById('terminal-cmd').value.trim();
  if (!cmd) return;
  const output = document.getElementById('terminal-output');
  output.innerHTML += `<span style="color:#58a6ff;">$ ${escHtml(cmd)}</span>\\n`;
  document.getElementById('terminal-cmd').value = '';
  fetch(`/blog/ai-webdev/${PROJECT_ID}/terminal/`, {
    method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':CSRF},
    body: JSON.stringify({command: cmd})
  }).then(async resp => {
    if (!resp.ok) { output.innerHTML += `<span style="color:#f85149;">오류 발생</span>\\n`; return; }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    while(true) {
      const {done, value} = await reader.read();
      if(done) break;
      const lines = decoder.decode(value).split('\\n');
      for(const line of lines) {
        if(!line.startsWith('data:')) continue;
        try {
          const evt = JSON.parse(line.slice(5).trim());
          if(evt.line) output.innerHTML += escHtml(evt.line);
          if(evt.done) {
            output.innerHTML += `<span style="color:#3fb950;">[완료 rc=${evt.returncode}]</span>\\n`;
            refreshFiles();
          }
          if(evt.error) output.innerHTML += `<span style="color:#f85149;">${escHtml(evt.error)}</span>\\n`;
        } catch(e){}
      }
    }
    output.scrollTop = output.scrollHeight;
  }).catch(e => {
    output.innerHTML += `<span style="color:#f85149;">오류: ${escHtml(e.message)}</span>\\n`;
  });
}
document.getElementById('terminal-cmd').addEventListener('keydown', e => {
  if(e.key === 'Enter') runTerminal();
});'''

new_js = '''// ════════════════════════════════════════════════
// 터미널 (세션 유지: cwd 추적 + 히스토리 + pip/python 자동교정)
// ════════════════════════════════════════════════
let termCwd = '.';          // 현재 디렉토리 (세션 유지)
let termHistory = [];       // 입력 히스토리
let termHistoryIdx = -1;    // 히스토리 커서

function termPrompt() {
  const dir = termCwd === '.' ? '~' : termCwd;
  return `<span style="color:#3fb950;">➜</span> <span style="color:#89b4fa;">${escHtml(dir)}</span> <span style="color:#cdd6f4;">$</span> `;
}

function runTerminal() {
  const input = document.getElementById('terminal-cmd');
  const cmd = input.value.trim();
  if (!cmd) return;
  const output = document.getElementById('terminal-output');

  // 히스토리 저장
  if (termHistory[termHistory.length - 1] !== cmd) termHistory.push(cmd);
  if (termHistory.length > 100) termHistory.shift();
  termHistoryIdx = termHistory.length;

  output.innerHTML += termPrompt() + escHtml(cmd) + '\\n';
  input.value = '';
  input.disabled = true;

  // clear 명령 처리
  if (cmd === 'clear' || cmd === 'cls') {
    output.innerHTML = '';
    input.disabled = false;
    input.focus();
    return;
  }

  fetch(`/blog/ai-webdev/${PROJECT_ID}/terminal/`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
    body: JSON.stringify({command: cmd, cwd: termCwd})
  }).then(async resp => {
    if (!resp.ok) {
      output.innerHTML += `<span style="color:#f85149;">HTTP 오류: ${resp.status}</span>\\n`;
      input.disabled = false; input.focus(); return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const parts = buf.split('\\n');
      buf = parts.pop();
      for (const line of parts) {
        if (!line.startsWith('data:')) continue;
        try {
          const evt = JSON.parse(line.slice(5).trim());
          if (evt.line) {
            output.innerHTML += escHtml(evt.line);
          }
          if (evt.error) {
            output.innerHTML += `<span style="color:#f85149;">${escHtml(evt.error)}</span>\\n`;
          }
          if (evt.done) {
            const rc = evt.returncode ?? 0;
            const color = rc === 0 ? '#3fb950' : '#f85149';
            output.innerHTML += `<span style="color:${color};">[완료 rc=${rc}]</span>\\n`;
            // cd 처리: new_cwd 수신 시 cwd 업데이트
            if (evt.new_cwd !== undefined) termCwd = evt.new_cwd;
            else if (evt.cwd !== undefined) termCwd = evt.cwd;
            refreshFiles();
          }
        } catch(e) {}
      }
    }
    input.disabled = false;
    input.focus();
    output.scrollTop = output.scrollHeight;
  }).catch(e => {
    output.innerHTML += `<span style="color:#f85149;">오류: ${escHtml(e.message)}</span>\\n`;
    input.disabled = false; input.focus();
  });
}

document.getElementById('terminal-cmd').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    runTerminal();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (termHistoryIdx > 0) {
      termHistoryIdx--;
      e.target.value = termHistory[termHistoryIdx] || '';
    }
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (termHistoryIdx < termHistory.length - 1) {
      termHistoryIdx++;
      e.target.value = termHistory[termHistoryIdx] || '';
    } else {
      termHistoryIdx = termHistory.length;
      e.target.value = '';
    }
  }
});'''

if old_js in content:
    content = content.replace(old_js, new_js, 1)
    open('/app/syblog_project/templates/blog/ai_webdev_project_js.html', 'w').write(content)
    print("✅ JS 터미널 교체 완료")
else:
    print("❌ 패턴 불일치")
    idx = content.find('function runTerminal()')
    print(f"runTerminal 위치: {idx}")
    print(repr(content[idx:idx+200]))
