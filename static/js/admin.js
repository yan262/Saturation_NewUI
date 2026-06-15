/**
 * 管理面板模块 (admin.js)
 * ========================
 * 提供用户管理和角色管理的完整前端交互逻辑。
 *
 * 本模块通过 IIFE（立即执行函数）封装，对外暴露 window.Admin 对象。
 * 管理面板内嵌在 index.html 中，点击顶栏"🔑 管理"按钮打开。
 *
 * 管理面板结构:
 *   ┌─ admin-tabs-bar ───────────────────┐
 *   │ [📋 用户管理] [🔑 角色管理]    [✕] │
 *   ├────────────────────────────────────┤
 *   │    用户列表表格 / 角色列表+权限编辑 │
 *   └────────────────────────────────────┘
 *
 * 数据来源（所有请求通过 Auth.fetchWithAuth 发送，自动鉴权）:
 *   用户管理 → GET/POST/PUT/DELETE /api/users      （需 users:manage 权限）
 *   角色管理 → GET/POST/PUT/DELETE /api/roles      （需 roles:manage 权限）
 *   权限列表 → GET /api/permissions                （需 roles:manage 权限）
 */
(function () {
  'use strict';

  // 快捷选择器
  var $ = function(sel) { return document.querySelector(sel); };

  // 模块内部状态缓存
  var rolesData = [];      // 所有角色数据
  var allPermissions = []; // 所有可用权限项

  // ================================================================
  // 面板开关
  // ================================================================

  /** 打开管理面板（index.html 中按钮 onclick 触发） */
  function open() {
    $('#admin-panel').classList.remove('hidden');
    switchTab('users');   // 默认显示用户管理标签
  }

  /** 关闭管理面板 */
  function close() {
    $('#admin-panel').classList.add('hidden');
  }

  /**
   * 切换标签页（用户管理 / 角色管理）
   * 由标签按钮 onclick 触发
   */
  function switchTab(tab) {
    document.querySelectorAll('.admin-tab').forEach(function(el) {
      el.classList.toggle('active', el.dataset.tab === tab);
    });
    $('#admin-users-tab').style.display = tab === 'users' ? 'block' : 'none';
    $('#admin-roles-tab').style.display = tab === 'roles' ? 'block' : 'none';
    // 切换标签时自动加载对应数据
    if (tab === 'users') loadUsers();
    if (tab === 'roles') loadRoles();
  }

  // ================================================================
  // 用户管理
  // ================================================================

  /** 从后端加载用户列表并渲染表格 */
  async function loadUsers() {
    try {
      var resp = await Auth.fetchWithAuth('/api/users');
      var users = await resp.json();
      renderUserTable(users);
    } catch (e) { console.error('加载用户列表失败', e); }
  }

  /**
   * 渲染用户表格。
   * 每列: 用户名 | 显示名 | 认证方式标签 | 角色列表 | 状态圆点 | 编辑/删除按钮
   */
  function renderUserTable(users) {
    var tbody = $('#users-table-body');
    tbody.innerHTML = users.map(function(u) {
      return '<tr>' +
        '<td><code>' + esc(u.username) + '</code></td>' +
        '<td>' + esc(u.display_name) + '</td>' +
        // 认证方式标签: 本地=青蓝色, LDAP=橙色
        '<td><span class="user-tag tag-' + u.auth_type + '">' + (u.auth_type === 'ldap' ? 'LDAP' : '本地') + '</span></td>' +
        '<td>' + esc((u.role_names || []).join(', ')) + '</td>' +
        // 状态: 绿色圆点=启用, 红色圆点=禁用
        '<td><span class="status-dot ' + (u.is_active ? 'on' : 'off') + '">●</span> ' + (u.is_active ? '启用' : '禁用') + '</td>' +
        '<td>' +
          '<button class="btn-glass btn-sm" onclick="Admin.editUser(' + u.id + ')">编辑</button> ' +
          '<button class="btn-glass btn-sm btn-danger" onclick="Admin.deleteUser(' + u.id + ', \'' + esc(u.username) + '\')">删除</button>' +
        '</td>' +
      '</tr>';
    }).join('');
  }

  /**
   * 打开用户编辑/新建弹窗。
   * @param {number} id — 0 表示新建，>0 表示编辑已有用户
   * 并行加载用户列表和角色列表，找到目标用户后展示弹窗。
   */
  async function editUser(id) {
    try {
      // 并行加载用户列表和角色列表
      var _a = await Promise.all([
        Auth.fetchWithAuth('/api/users'),
        Auth.fetchWithAuth('/api/roles')
      ]);
      var usersResp = _a[0], rolesResp = _a[1];
      var users = await usersResp.json();
      var roles = await rolesResp.json();

      var user = null;
      if (id) {
        // 编辑已有用户：从列表中查找
        user = users.find(function(u) { return u.id === id; });
        if (!user) return;   // 用户不存在，放弃
      }
      // id 为 0 时 user 为 null，进入新建模式
      showUserModal(user, roles);
    } catch (e) { console.error(e); }
  }

  /** 删除用户（需确认） */
  async function deleteUser(id, username) {
    if (!confirm('确定删除用户 "' + username + '" 吗？此操作不可恢复。')) return;
    try {
      var resp = await Auth.fetchWithAuth('/api/users/' + id, { method: 'DELETE' });
      if (resp.ok) loadUsers();    // 刷新列表
      else alert('删除失败');
    } catch (e) { console.error(e); }
  }

  /**
   * 显示用户编辑/新建弹窗。
   * 字段: 用户名 | 显示名称 | 认证方式 | 密码 | 启用开关 | 角色多选
   */
  function showUserModal(user, roles) {
    var isNew = !user;
    var u = user || { username: '', display_name: '', auth_type: 'local', is_active: true, role_ids: [] };

    // 角色复选框
    var roleChecks = roles.map(function(r) {
      return '<label class="admin-check-label">' +
        '<input type="checkbox" value="' + r.id + '"' + (u.role_ids.indexOf(r.id) !== -1 ? ' checked' : '') + '> ' + esc(r.name) +
      '</label>';
    }).join('');

    var html = '<div class="admin-modal-content">' +
      '<h3>' + (isNew ? '新建用户' : '编辑用户') + '</h3>' +
      // 用户名（编辑时禁用修改）
      '<div class="admin-field"><label>用户名</label>' +
        '<input type="text" id="mu-username" class="login-input" value="' + esc(u.username) + '"' + (!isNew ? ' disabled' : '') + ' autocomplete="off"></div>' +
      '<div class="admin-field"><label>显示名称</label>' +
        '<input type="text" id="mu-display" class="login-input" value="' + esc(u.display_name || '') + '" autocomplete="off"></div>' +
      // 认证方式下拉
      '<div class="admin-field"><label>认证方式</label>' +
        '<select id="mu-auth-type" class="login-input">' +
          '<option value="local"' + (u.auth_type === 'local' ? ' selected' : '') + '>本地账号</option>' +
          '<option value="ldap"' + (u.auth_type === 'ldap' ? ' selected' : '') + '>LDAP / AD</option>' +
        '</select></div>' +
      // 密码字段（LDAP 用户自动隐藏，带 👁 显隐切换）
      '<div class="admin-field" id="mu-pw-field" style="display:' + ((isNew && u.auth_type !== 'ldap') || !isNew ? 'block' : 'none') + '">' +
        '<label>' + (isNew ? '密码' : '新密码（留空不修改）') + '</label>' +
        '<div class="login-pw-wrap">' +
          '<input type="password" id="mu-password" class="login-input" placeholder="' + (isNew ? '' : '留空不修改') + '" autocomplete="new-password">' +
          '<button type="button" class="login-pw-toggle" id="mu-pw-toggle" title="显示/隐藏密码">👁</button>' +
        '</div></div>' +
      // 启用开关
      '<div class="admin-field"><label><input type="checkbox" id="mu-active"' + (u.is_active ? ' checked' : '') + '> 启用账号</label></div>' +
      // 角色多选
      '<div class="admin-field"><label>角色</label><div class="admin-check-group">' + roleChecks + '</div></div>' +
      // 操作按钮
      '<div class="admin-modal-actions">' +
        '<button class="btn-glass" onclick="Admin.saveUser(' + (isNew ? 0 : u.id) + ')">保存</button>' +
        '<button class="btn-glass" onclick="Admin.closeModal()">取消</button>' +
      '</div></div>';
    showModal(html);

    // 认证方式切换时，显示/隐藏密码字段
    var authSelect = document.getElementById('mu-auth-type');
    if (authSelect) {
      authSelect.addEventListener('change', function() {
        var pwField = document.getElementById('mu-pw-field');
        if (pwField) pwField.style.display = this.value === 'ldap' ? 'none' : 'block';
      });
    }
  }

  /** 保存用户（新建或编辑） */
  async function saveUser(id) {
    var username = $('#mu-username') ? $('#mu-username').value.trim() : '';
    var display_name = $('#mu-display') ? $('#mu-display').value.trim() : '';
    var auth_type = $('#mu-auth-type') ? $('#mu-auth-type').value : 'local';
    var is_active = $('#mu-active') ? $('#mu-active').checked : true;
    var password = $('#mu-password') ? $('#mu-password').value : '';

    // 收集选中的角色 ID
    var role_ids = [];
    document.querySelectorAll('#admin-modal .admin-check-label input:checked').forEach(function(cb) {
      role_ids.push(parseInt(cb.value));
    });

    var body = { username: username, display_name: display_name, auth_type: auth_type, is_active: is_active, role_ids: role_ids };
    if (password) body.password = password;   // 密码留空则不传

    try {
      var url = id ? '/api/users/' + id : '/api/users';
      var method = id ? 'PUT' : 'POST';
      var resp = await Auth.fetchWithAuth(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (resp.ok) { closeModal(); loadUsers(); }
      else { var err = await resp.json(); alert(err.detail || '保存失败'); }
    } catch (e) { console.error(e); }
  }

  // ================================================================
  // 角色管理
  // ================================================================

  /** 并行加载角色列表和权限列表 */
  async function loadRoles() {
    try {
      var _a = await Promise.all([Auth.fetchWithAuth('/api/roles'), Auth.fetchWithAuth('/api/permissions')]);
      var rolesResp = _a[0], permsResp = _a[1];
      rolesData = await rolesResp.json();
      allPermissions = await permsResp.json();
      renderRoleList();
    } catch (e) { console.error(e); }
  }

  /**
   * 渲染左侧角色列表 + 右侧权限编辑区。
   * 系统预置角色前有 🔒 图标，自定义角色前是 ○。
   */
  function renderRoleList() {
    var rolesTab = $('#admin-roles-tab');
    var selectedId = rolesTab ? rolesTab.getAttribute('data-selected-role-id') : '';
    var container = $('#roles-list');
    container.innerHTML = rolesData.map(function(r) {
      return '<div class="role-item' + (r.id == selectedId ? ' selected' : '') + '" onclick="Admin.selectRole(' + r.id + ')">' +
        (r.is_system ? '🔒 ' : '○ ') + esc(r.name) +
      '</div>';
    }).join('') + '<button class="btn-glass btn-sm" style="margin-top:8px" onclick="Admin.createRole()">+ 新建角色</button>';

    // 如果有选中的角色，渲染右侧权限编辑区
    if (selectedId) {
      var role = rolesData.find(function(r) { return r.id == selectedId; });
      if (role) renderRolePerms(role);
    }
  }

  /**
   * 渲染右侧角色详情: 角色名、描述、权限勾选列表、保存/删除按钮。
   * 系统角色名不可修改，但权限可调整。
   */
  function renderRolePerms(role) {
    var permIds = new Set(role.permissions.map(function(p) { return p.id; }));
    var permsHtml = allPermissions.map(function(p) {
      return '<label class="admin-check-label">' +
        '<input type="checkbox" value="' + p.id + '"' + (permIds.has(p.id) ? ' checked' : '') + '> ' + esc(p.name) +
        ' <small>(' + esc(p.code) + ')</small>' +
      '</label>';
    }).join('');

    var isSystem = role.is_system;
    $('#role-perms').innerHTML =
      '<div class="admin-field"><label>角色名</label>' +
        '<input type="text" id="mr-name" class="login-input" value="' + esc(role.name) + '"' + (isSystem ? ' disabled' : '') + '></div>' +
      '<div class="admin-field"><label>描述</label>' +
        '<input type="text" id="mr-desc" class="login-input" value="' + esc(role.description || '') + '"></div>' +
      '<div class="admin-field"><label>权限</label><div class="admin-check-group">' + permsHtml + '</div></div>' +
      '<div class="admin-modal-actions">' +
        '<button class="btn-glass" onclick="Admin.saveRole(' + role.id + ')">保存</button>' +
        (!isSystem ? '<button class="btn-glass btn-danger" onclick="Admin.deleteRole(' + role.id + ', \'' + esc(role.name) + '\')">删除</button>' : '') +
      '</div>';
  }

  /** 点击左侧角色列表中的角色名 → 选中 */
  function selectRole(id) {
    var rolesTab = $('#admin-roles-tab');
    if (rolesTab) rolesTab.setAttribute('data-selected-role-id', id);
    renderRoleList();
  }

  /** 新建角色: 清空选中，显示空白表单 */
  function createRole() {
    var rolesTab = $('#admin-roles-tab');
    if (rolesTab) rolesTab.setAttribute('data-selected-role-id', '');
    renderRoleList();
    $('#role-perms').innerHTML =
      '<div class="admin-field"><label>角色名</label>' +
        '<input type="text" id="mr-name" class="login-input" placeholder="新角色名称"></div>' +
      '<div class="admin-field"><label>描述</label>' +
        '<input type="text" id="mr-desc" class="login-input" placeholder="角色说明"></div>' +
      '<div class="admin-field"><label>权限</label><div class="admin-check-group">' +
        allPermissions.map(function(p) {
          return '<label class="admin-check-label"><input type="checkbox" value="' + p.id + '"> ' + esc(p.name) + ' <small>(' + esc(p.code) + ')</small></label>';
        }).join('') +
      '</div></div>' +
      '<div class="admin-modal-actions"><button class="btn-glass" onclick="Admin.saveRole(0)">创建</button></div>';
  }

  /** 保存角色（新建或编辑） */
  async function saveRole(id) {
    var name = $('#mr-name') ? $('#mr-name').value.trim() : '';
    var description = $('#mr-desc') ? $('#mr-desc').value.trim() : '';
    var permission_ids = [];
    document.querySelectorAll('#role-perms .admin-check-label input:checked').forEach(function(cb) {
      permission_ids.push(parseInt(cb.value));
    });

    if (!name) { alert('角色名不能为空'); return; }

    try {
      var url = id ? '/api/roles/' + id : '/api/roles';
      var method = id ? 'PUT' : 'POST';
      var resp = await Auth.fetchWithAuth(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name, description: description, permission_ids: permission_ids }) });
      if (resp.ok) {
        if (!id) { var rolesTab = $('#admin-roles-tab'); if (rolesTab) rolesTab.setAttribute('data-selected-role-id', ''); }
        loadRoles();
      } else { var err = await resp.json(); alert(err.detail || '保存失败'); }
    } catch (e) { console.error(e); }
  }

  /** 删除角色（需确认） */
  async function deleteRole(id, name) {
    if (!confirm('确定删除角色 "' + name + '" 吗？')) return;
    try {
      var resp = await Auth.fetchWithAuth('/api/roles/' + id, { method: 'DELETE' });
      if (resp.ok) { var rolesTab = $('#admin-roles-tab'); if (rolesTab) rolesTab.setAttribute('data-selected-role-id', ''); loadRoles(); }
      else { var err = await resp.json(); alert(err.detail || '删除失败'); }
    } catch (e) { console.error(e); }
  }

  // ================================================================
  // 模态框工具
  // ================================================================

  /** 显示模态框（用户编辑弹窗，注入内容后绑定密码显隐切换事件） */
  function showModal(innerHtml) {
    $('#admin-modal').innerHTML = innerHtml;
    $('#admin-modal').classList.remove('hidden');

    // 注入完成后绑定密码显隐切换（避免 innerHTML onclick 绑定不可靠）
    var pwToggle = document.getElementById('mu-pw-toggle');
    if (pwToggle) {
      pwToggle.addEventListener('click', toggleMuPassword);
    }
  }

  /** 关闭模态框 */
  function closeModal() {
    $('#admin-modal').classList.add('hidden');
  }

  /**
   * HTML 转义 — 防止 XSS 攻击。
   * 将 & < > " 转义为 HTML 实体。
   */
  function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ================================================================
  // 工具函数
  // ================================================================

  /**
   * 切换模态框中密码输入框的显隐状态。
   * 点击 👁 图标在密码（隐藏）和明文（显示）之间切换。
   */
  function toggleMuPassword() {
    var input = document.getElementById('mu-password');
    var btn = document.getElementById('mu-pw-toggle');
    if (!input) return;
    if (input.type === 'password') {
      input.type = 'text';
      if (btn) btn.textContent = '🙈';
    } else {
      input.type = 'password';
      if (btn) btn.textContent = '👁';
    }
  }

  // ================================================================
  // 对外暴露 API
  // ================================================================
  window.Admin = { open: open, close: close, switchAdminTab: switchTab, editUser: editUser, deleteUser: deleteUser, saveUser: saveUser,
    selectRole: selectRole, createRole: createRole, saveRole: saveRole, deleteRole: deleteRole, closeModal: closeModal, toggleMuPassword: toggleMuPassword };
})();
