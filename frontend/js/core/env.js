/**
 * @file 全局常量与轻量状态
 * @module core/env
 */

  // marked v5+ 已移除 highlight / sanitize 选项：
  // 语法高亮改在 enhanceCodeBlocks 里手动调 hljs，XSS 消毒交给 DOMPurify

  const API = '/api';

  // 当前学生 ID：登录用户名，未登录用演示账号（学情数据与登录体系打通）
  function currentStudentId() {
    return localStorage.getItem('cm_user') || 'demo_student';
  }

// 导出 + 供 HTML 内联 onclick 使用
export { API, currentStudentId };
Object.assign(window, { API, currentStudentId });
