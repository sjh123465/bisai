/**
 * @file 学生/教师自己的远程模型配置（浏览器本地保存，不上传服务端持久化）
 * @module core/llmSettings
 *
 * 默认只存 sessionStorage；用户勾选「记住此设备」才写 localStorage。
 * 所有请求通过 X-LLM-* 头把配置带给后端，后端只在请求生命周期内使用。
 */

const SESSION_KEY = 'cm_llm_config_session';
const LOCAL_KEY = 'cm_llm_config_local';

const PROVIDER_DEFAULTS = {
  deepseek: {
    id: 'deepseek',
    name: 'DeepSeek',
    model: 'deepseek-chat',
    keyHint: 'sk-...',
    hasVision: false,
  },
  zhipu: {
    id: 'zhipu',
    name: '智谱 GLM',
    model: 'glm-4-flash',
    keyHint: '智谱开放平台 API Key',
    hasVision: true,
  },
};

function _parse(raw) {
  if (!raw) return null;
  try {
    const cfg = JSON.parse(raw);
    if (!cfg || !cfg.apiKey) return null;
    return cfg;
  } catch (_) {
    return null;
  }
}

/** 读取当前配置（session 优先，其次 remember 的 local） */
function getLLMSettings() {
  return _parse(sessionStorage.getItem(SESSION_KEY)) || _parse(localStorage.getItem(LOCAL_KEY));
}

/** 保存配置。remember=true 时持久化到 localStorage。 */
function saveLLMSettings({ provider = 'deepseek', apiKey, model, remember = false }) {
  const key = (apiKey || '').trim();
  if (!key) throw new Error('请填写 API Key');
  const preset = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.deepseek;
  const cfg = {
    provider: preset.id,
    apiKey: key,
    model: (model || preset.model).trim(),
  };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(cfg));
  if (remember) {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(cfg));
  } else {
    localStorage.removeItem(LOCAL_KEY);
  }
  return cfg;
}

function clearLLMSettings() {
  sessionStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(LOCAL_KEY);
}

function hasLLMSettings() {
  return !!getLLMSettings();
}

function isRemembered() {
  return !!localStorage.getItem(LOCAL_KEY);
}

/** 把浏览器中的配置转成后端约定的请求头 */
function llmHeaders() {
  const cfg = getLLMSettings();
  if (!cfg) return {};
  return {
    'X-LLM-Provider': cfg.provider || 'deepseek',
    'X-LLM-Key': cfg.apiKey,
    'X-LLM-Model': cfg.model || '',
  };
}

/** 生成脱敏展示，例如 sk-abc...1234 */
function maskKey(key) {
  const k = String(key || '');
  if (k.length <= 10) return k ? '••••' : '';
  return k.slice(0, 4) + '••••' + k.slice(-4);
}

export {
  PROVIDER_DEFAULTS,
  getLLMSettings,
  saveLLMSettings,
  clearLLMSettings,
  hasLLMSettings,
  isRemembered,
  llmHeaders,
  maskKey,
};
Object.assign(window, {
  PROVIDER_DEFAULTS,
  getLLMSettings,
  saveLLMSettings,
  clearLLMSettings,
  hasLLMSettings,
  isRemembered,
  maskKey,
});
