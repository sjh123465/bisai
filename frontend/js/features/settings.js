/**
 * @file 模型设置弹窗 + 本地学情导入导出
 * @module features/settings
 *
 * 模型 Key 只保存在浏览器；后端只在单次请求期间使用，不落盘、不写日志。
 */
import {
  PROVIDER_DEFAULTS,
  getLLMSettings,
  saveLLMSettings,
  clearLLMSettings,
  hasLLMSettings,
  isRemembered,
  maskKey,
} from '../core/llmSettings.js';
import { exportProfile, importProfile, clearProfile } from '../core/localStore.js';
import { clearLatestAnalysis } from '../core/analysisStore.js';
import { escapeHtml } from '../core/render.js';

let _providersLoaded = false;

function _msg(text, ok = false) {
  const el = document.getElementById('settings-msg');
  if (!el) return;
  el.textContent = text;
  el.className = ok ? 'msg-ok mb-3' : 'msg-err mb-3';
  el.classList.remove('hidden');
}

function _clearMsg() {
  const el = document.getElementById('settings-msg');
  if (el) el.classList.add('hidden');
}

async function _loadProviders() {
  const sel = document.getElementById('llm-provider');
  if (!sel) return;
  if (!_providersLoaded) {
    try {
      const resp = await fetch('/api/settings/llm/providers');
      const data = await resp.json();
      const providers = data.providers || [];
      if (providers.length) {
        sel.innerHTML = providers.map(p =>
          `<option value="${p.id}">${p.name}（默认 ${escapeHtml(p.model)}）</option>`
        ).join('');
        _providersLoaded = true;
      }
    } catch (_) { /* 后端未启动时使用本地预设 */ }
  }
  if (!sel.options.length) {
    sel.innerHTML = Object.values(PROVIDER_DEFAULTS).map(p =>
      `<option value="${p.id}">${p.name}（默认 ${escapeHtml(p.model)}）</option>`
    ).join('');
  }
}

function openSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  _clearMsg();
  _loadProviders();
  const cfg = getLLMSettings();
  const providerEl = document.getElementById('llm-provider');
  const keyEl = document.getElementById('llm-key');
  const rememberEl = document.getElementById('llm-remember');
  if (cfg) {
    if (providerEl) providerEl.value = cfg.provider;
    if (keyEl) keyEl.value = cfg.apiKey;
  } else {
    if (keyEl) keyEl.value = '';
  }
  if (rememberEl) rememberEl.checked = isRemembered();
  updateLLMStatus();
  setTimeout(() => keyEl && keyEl.focus(), 100);
}

function closeSettings() {
  document.getElementById('settings-modal')?.classList.add('hidden');
}

function _formConfig() {
  const provider = document.getElementById('llm-provider')?.value || 'deepseek';
  const apiKey = document.getElementById('llm-key')?.value || '';
  const remember = !!document.getElementById('llm-remember')?.checked;
  return { provider, apiKey, remember };
}

function saveSettingsFromForm() {
  const { provider, apiKey, remember } = _formConfig();
  if (!apiKey.trim()) {
    _msg('请填写远程 API Key');
    return false;
  }
  try {
    saveLLMSettings({ provider, apiKey, remember });
    updateLLMStatus();
    _msg('已保存到浏览器。Key 不会上传到服务器持久化。', true);
    return true;
  } catch (e) {
    _msg('保存失败：' + (e.message || e));
    return false;
  }
}

async function testLLMSettings() {
  const { provider, apiKey } = _formConfig();
  if (!apiKey.trim()) {
    _msg('请先填写 API Key，再测试连接');
    return;
  }
  const btn = document.getElementById('settings-test-btn');
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '测试中...'; }
  _clearMsg();
  try {
    // 显式携带表单里的头，避免用户还没保存时测试到旧配置
    const resp = await fetch('/api/settings/llm/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-LLM-Provider': provider,
        'X-LLM-Key': apiKey.trim(),
      },
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
    _msg(`连接成功：${data.provider} / ${data.model}${data.reply ? ' · ' + data.reply : ''}`, true);
  } catch (e) {
    _msg('连接失败：' + (e.message || e));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

function clearSettings() {
  clearLLMSettings();
  const keyEl = document.getElementById('llm-key');
  if (keyEl) keyEl.value = '';
  updateLLMStatus();
  _msg('已清除本浏览器的 API Key。', true);
}

/** 只检查本地是否配置了 Key；没有则打开设置窗口。 */
function requireLLMConfigured() {
  if (hasLLMSettings()) return true;
  openSettings();
  _msg('请先配置你自己的远程 API Key，再使用 AI 对话 / 出题功能。');
  return false;
}

function updateLLMStatus() {
  const cfg = getLLMSettings();
  const btn = document.getElementById('btn-settings');
  if (btn) {
    const label = document.getElementById('settings-btn-label');
    if (label) label.textContent = cfg ? '模型已配置' : '配置模型';
    btn.dataset.configured = cfg ? '1' : '0';
  }
  const statusEl = document.getElementById('llm-key-status');
  if (statusEl) {
    statusEl.textContent = cfg
      ? `${PROVIDER_DEFAULTS[cfg.provider]?.name || cfg.provider} · ${maskKey(cfg.apiKey)}`
      : '尚未配置远程 API Key';
  }
  const tip = document.getElementById('api-tip');
  if (tip) tip.classList.toggle('hidden', !!cfg);
}

function exportLocalData() {
  try {
    const text = exportProfile();
    const blob = new Blob([text], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'codementor-local-profile.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    _msg('已导出本地学情文件。', true);
  } catch (e) {
    _msg('导出失败：' + (e.message || e));
  }
}

function triggerImportLocalData() {
  document.getElementById('profile-import-file')?.click();
}

function importLocalData(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      importProfile(String(reader.result || ''));
      _msg('已导入本地学情。', true);
      window.refreshTodayStats?.();
      window.refreshPersonalRadar?.();
      window.refreshProgressCurve?.();
    } catch (e) {
      _msg('导入失败：' + (e.message || e));
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

function clearLocalData() {
  if (!confirm('确定清空当前浏览器中的个人学情（BKT / 错题本 / 历史 / AI 分析缓存）吗？此操作不可撤销。')) return;
  clearProfile();
  clearLatestAnalysis();
  _msg('本地学情与 AI 分析缓存已清空。', true);
  window.refreshTodayStats?.();
  window.refreshPersonalRadar?.();
  window.refreshProgressCurve?.();
}

export {
  openSettings,
  closeSettings,
  saveSettingsFromForm,
  testLLMSettings,
  clearSettings,
  requireLLMConfigured,
  updateLLMStatus,
  exportLocalData,
  triggerImportLocalData,
  importLocalData,
  clearLocalData,
};
Object.assign(window, {
  openSettings,
  closeSettings,
  saveSettingsFromForm,
  testLLMSettings,
  clearSettings,
  requireLLMConfigured,
  updateLLMStatus,
  exportLocalData,
  triggerImportLocalData,
  importLocalData,
  clearLocalData,
});
