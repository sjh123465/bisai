/**
 * @file 语音提问（Web Speech API）
 * @module features/voice
 */

    // 从图谱等其他 Tab 触发时，先切回对话 Tab，否则用户看不到回答

  // ---------- 代码面板 ----------
  // ---------- 语音提问（Web Speech API，浏览器原生识别） ----------
  let _voiceRec = null;
  let _voiceOn = false;
  const VOICE_PLACEHOLDER = '问我任何计算机知识 — 理论、代码、算法... 我会调用工具帮你';

  function _setVoiceState(on, btn) {
    _voiceOn = on;
    if (!btn) return;
    btn.classList.toggle('voice-on', on);
    btn.innerHTML = on
      ? '<svg class="cm-icon" aria-hidden="true"><use href="#i-x"></use></svg>'
      : '<svg class="cm-icon" aria-hidden="true"><use href="#i-mic"></use></svg>';
    btn.title = on ? '正在聆听… 点击停止' : '语音提问（Chrome / Edge，需允许麦克风）';
  }

  function toggleVoiceInput() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const btn = document.getElementById('voice-btn');
    if (!SR) {
      alert('当前浏览器不支持语音识别。\n请使用 Chrome / Edge，并通过 http://localhost 或 HTTPS 访问。');
      return;
    }
    if (_voiceOn) { _voiceRec && _voiceRec.stop(); return; }
    const rec = new SR();
    _voiceRec = rec;
    rec.lang = 'zh-CN';
    rec.interimResults = true;
    rec.continuous = false;
    rec.onstart = () => _setVoiceState(true, btn);
    rec.onresult = (e) => {
      const input = document.getElementById('user-input');
      let finalTxt = '', interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalTxt += t; else interim += t;
      }
      if (finalTxt) {
        input.value = (input.value ? input.value + ' ' : '') + finalTxt.trim();
        input.placeholder = VOICE_PLACEHOLDER;
      } else if (interim) {
        input.placeholder = '正在聆听 · ' + interim;
      }
    };
    rec.onerror = (e) => {
      const map = {
        'not-allowed': '麦克风权限被拒绝，请点击地址栏的权限图标允许麦克风',
        'no-speech': '没有检测到语音，请靠近麦克风再试一次',
        'audio-capture': '未找到可用的麦克风设备',
        'network': '语音识别服务网络异常',
      };
      if (e.error !== 'aborted') alert('语音识别失败：' + (map[e.error] || e.error));
    };
    rec.onend = () => {
      _setVoiceState(false, btn);
      document.getElementById('user-input').placeholder = VOICE_PLACEHOLDER;
    };
    try { rec.start(); } catch (err) { alert('无法启动语音识别：' + err.message); }
  }

// 导出 + 供 HTML 内联 onclick 使用
export { toggleVoiceInput };
Object.assign(window, { toggleVoiceInput });
