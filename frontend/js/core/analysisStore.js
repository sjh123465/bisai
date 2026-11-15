/**
 * @file 学情 AI 分析缓存（按用户分区，只保留最新一份）
 * @module core/analysisStore
 *
 * 用户选择的“一个文本文件，每次分析重写”的等价实现：
 * - 只保存最新一条分析，生成新分析时直接覆盖，不累积历史；
 * - 记录数据指纹，供前端判断分析是否已过期；
 * - 服务端不保存；个人学情仍只在浏览器。
 */

const VERSION = 1;
const MAX_REPORT_CHARS = 50000;

function currentUser() {
  return localStorage.getItem('cm_user') || 'guest';
}

function storageKey() {
  return `cm_analysis_v1:${encodeURIComponent(currentUser())}`;
}

/** 读取当前账号最新一份分析；没有或格式不符返回 null。 */
function loadLatestAnalysis() {
  try {
    const raw = localStorage.getItem(storageKey());
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || data.version !== VERSION || typeof data.report !== 'string' || !data.report.trim()) {
      return null;
    }
    return data;
  } catch (e) {
    console.warn('[analysisStore] 分析缓存读取失败', e);
    return null;
  }
}

/** 覆盖保存最新一份分析（单文件语义：旧报告被重写掉）。 */
function saveLatestAnalysis({ report, scope = 'all', concept_id = null, concept_name = '', fingerprint = '', model = '', generated_at = '' }) {
  const data = {
    version: VERSION,
    report: String(report || '').slice(0, MAX_REPORT_CHARS),
    scope,
    concept_id: concept_id || null,
    concept_name: concept_name || '',
    fingerprint: fingerprint || '',
    model: model || '',
    generated_at: generated_at || new Date().toISOString(),
  };
  try {
    localStorage.setItem(storageKey(), JSON.stringify(data));
  } catch (e) {
    console.warn('[analysisStore] 分析缓存写入失败（可能是存储空间不足）', e);
  }
  return data;
}

function clearLatestAnalysis() {
  try {
    localStorage.removeItem(storageKey());
  } catch (e) {
    console.warn('[analysisStore] 分析缓存清除失败', e);
  }
}

export { currentUser, loadLatestAnalysis, saveLatestAnalysis, clearLatestAnalysis };
Object.assign(window, {
  cmAnalysisStore: { currentUser, loadLatestAnalysis, saveLatestAnalysis, clearLatestAnalysis },
});
