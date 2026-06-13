/**
 * 认证工具模块 (auth.js)
 * =======================
 * 全局对象 Auth，提供 token 管理、自动刷新、401 拦截等功能。
 *
 * 本模块被 login.html（登录页）和 index.html（仪表板）共用。
 * 所有需要鉴权的 API 请求都应通过 Auth.fetchWithAuth() 发送，
 * 它会自动附带 Authorization 请求头并在 token 过期时尝试刷新。
 *
 * 数据存储:
 *   localStorage 中存储三样东西:
 *     access_token  — 短期 JWT（默认 30 分钟），用于 API 鉴权
 *     refresh_token — 长期 JWT（默认 7 天），用于刷新 access_token
 *     user_info     — JSON 字符串，含 id/username/display_name/permissions 等
 *
 * 使用示例:
 *   // 页面加载时检查登录状态
 *   Auth.guard();
 *
 *   // 判断用户是否有某权限
 *   if (Auth.hasPermission('users:manage')) { ... }
 *
 *   // 发起需要鉴权的 API 请求
 *   var resp = await Auth.fetchWithAuth('/api/users');
 */
var Auth = {

  /** 获取 access token（短期），可能为 null */
  getToken: function() {
    return localStorage.getItem('access_token');
  },

  /** 获取 refresh token（长期），可能为 null */
  getRefreshToken: function() {
    return localStorage.getItem('refresh_token');
  },

  /**
   * 存储 token 到浏览器本地存储。
   * 登录成功后调用: Auth.setTokens(access_token, refresh_token)
   */
  setTokens: function(access, refresh) {
    localStorage.setItem('access_token', access);
    if (refresh) localStorage.setItem('refresh_token', refresh);
  },

  /**
   * 获取当前登录用户的信息对象。
   * 返回: { id, username, display_name, auth_type, permissions: [...] }
   * 未登录时返回 null。
   */
  getUser: function() {
    try {
      return JSON.parse(localStorage.getItem('user_info'));
    } catch (e) { return null; }
  },

  /**
   * 构建带 Authorization 头的 HTTP headers 对象。
   * 供 fetchWithAuth() 内部使用。
   * 返回: { 'Authorization': 'Bearer <token>' } 或 {}
   */
  getAuthHeaders: function() {
    var token = this.getToken();
    return token ? { 'Authorization': 'Bearer ' + token } : {};
  },

  /**
   * 用 refresh token 换取新的 access token。
   * 当 API 返回 401 时由 fetchWithAuth() 自动调用。
   * 成功 → 更新 localStorage 中的 access_token → 返回 true
   * 失败 → 返回 false（此时需要重新登录）
   *
   * 注意: 此函数调用 /api/auth/refresh，该接口在中间件白名单中，无需鉴权。
   */
  refreshAccessToken: async function() {
    var refresh = this.getRefreshToken();
    if (!refresh) return false;   // 没有 refresh token，无法刷新
    try {
      var resp = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (resp.ok) {
        var data = await resp.json();
        localStorage.setItem('access_token', data.access_token);
        return true;
      }
    } catch (e) { /* 网络错误，忽略 */ }
    return false;
  },

  /**
   * 退出登录。
   * 清除所有 token 和用户信息 → 跳转回登录页。
   */
  logout: function() {
    if (!confirm('确定退出登录吗？')) return;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_info');
    window.location.replace('/');   // 回到登录页
  },

  /**
   * 封装 fetch，自动附带 Authorization 请求头。
   *
   * 与原生 fetch 的区别:
   *   - 自动添加 Authorization: Bearer <token>
   *   - 收到 401 时自动尝试刷新 token
   *   - 刷新成功 → 重试原请求
   *   - 刷新失败 → 清除 token → 跳转登录页
   *
   * 用法同 fetch:
   *   var resp = await Auth.fetchWithAuth('/api/users');
   *   var resp = await Auth.fetchWithAuth('/api/users/3', { method: 'DELETE' });
   */
  fetchWithAuth: async function(url, options) {
    options = options || {};
    // 合并自定义 headers 和认证 headers
    options.headers = Object.assign({}, options.headers || {}, this.getAuthHeaders());
    var resp = await fetch(url, options);

    // 401 → token 可能过期，尝试刷新
    if (resp.status === 401) {
      var refreshed = await this.refreshAccessToken();
      if (refreshed) {
        // 刷新成功: 用新 token 重试
        options.headers = Object.assign({}, options.headers || {}, this.getAuthHeaders());
        resp = await fetch(url, options);
      } else {
        // 刷新失败: 退出登录
        this.logout();
        throw new Error('认证已过期');
      }
    }
    return resp;
  },

  /**
   * 登录守卫 — 页面加载时调用。
   * 没有 access token → 跳转回登录页。
   * 返回 false 表示未登录，调用方可据此阻止后续逻辑。
   */
  guard: function() {
    if (!this.getToken()) {
      window.location.replace('/');
      return false;
    }
    return true;
  },

  /**
   * 检查当前用户是否拥有指定权限。
   * 参数 code: 权限码，如 'users:manage'、'dashboard:view'
   * 用于判断是否显示管理按钮、导出按钮等。
   */
  hasPermission: function(code) {
    var user = this.getUser();
    return user && user.permissions && user.permissions.indexOf(code) !== -1;
  },
};
