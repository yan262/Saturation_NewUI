/**
 * 电缆桥架饱和度监控 — 主应用逻辑
 * 职责: WebSocket 连接、Chart.js 图表、UI 更新、设置管理、CSV 导出
 */
(function () {
  'use strict';

  const state = {
    history: [],
    prevValue: null,
    alarmCount: 0,
    alarmMinutes: 0,
    alarming: false,
    settings: { refresh_rate: 2, alarm_threshold: 85 },
    ws: null,
    chart: null,
    chartInitialized: false,
  };

  const $ = (sel) => document.querySelector(sel);

  function initChart() {
    const ctx = $('#trend-chart').getContext('2d');
    state.chart = new Chart(ctx, {
      type: 'line',
      data: { labels: [], datasets: [{
        label: '饱和度',
        data: [],
        borderColor: '#00e5ff',
        backgroundColor: 'rgba(0, 229, 255, 0.10)',
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
      }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { color: '#5a7a9a', font: { size: 11, family: "'JetBrains Mono', monospace" }, maxTicksLimit: 8 },
            grid: { color: 'rgba(30, 60, 100, 0.3)' },
          },
          y: {
            min: 0, max: 100,
            ticks: { color: '#5a7a9a', font: { size: 11, family: "'JetBrains Mono', monospace" }, stepSize: 20,
              callback: (v) => v + '%' },
            grid: { color: 'rgba(30, 60, 100, 0.3)' },
          },
        },
      },
    });
    state.chartInitialized = true;
  }

  function updateClock() {
    const now = new Date();
    $('#clock').textContent = now.toLocaleTimeString('zh-CN', { hour12: false });
  }
  setInterval(updateClock, 1000);
  updateClock();

  function updateGauge(value, threshold, alarming) {
    GaugeRenderer.render($('#gauge-container'), value, threshold, alarming);
  }

  function updateValueCard(value, prevValue) {
    const el = $('#current-value');
    el.textContent = value.toFixed(1);
    const threshold = state.settings.alarm_threshold;
    el.classList.toggle('alarming', value >= threshold);

    const deltaEl = $('#delta-text');
    if (prevValue !== null) {
      const diff = value - prevValue;
      deltaEl.textContent = diff > 0 ? `▲ 较上次 +${diff.toFixed(1)}%` : `▼ 较上次 ${diff.toFixed(1)}%`;
      deltaEl.className = 'card-delta ' + (diff > 0 ? 'up' : 'down');
    } else {
      deltaEl.textContent = '首次采集';
      deltaEl.className = 'card-delta';
    }
  }

  function updateChart(history) {
    if (!state.chartInitialized) initChart();
    state.chart.data.labels = history.map(h => h.time);
    state.chart.data.datasets[0].data = history.map(h => h.value);
    state.chart.update('none');
  }

  function updateProgress(value, threshold) {
    // 填充宽度按 100% 计算（实际饱和度值），阈值刻度线作为报警参考
    var pct = Math.min(value, 100);
    var fill = $('#progress-fill');
    fill.style.width = pct + '%';
    // 超过阈值时变红
    fill.classList.toggle('warning', value >= threshold);
    $('#progress-text').textContent = value.toFixed(1) + '% / ' + threshold + '%';

    // 动态调整阈值刻度线位置
    var thresholdLine = $('#progress-threshold');
    if (thresholdLine) {
      thresholdLine.style.left = threshold + '%';
      var markerEl = document.getElementById('threshold-marker');
      if (markerEl) markerEl.textContent = threshold;
    }
  }

  function updateStats(stats, currentValue) {
    $('#stat-avg').innerHTML = `${stats.avg.toFixed(1)}<small>%</small>`;
    $('#stat-max').innerHTML = `${stats.max.toFixed(1)}<small>%</small>`;
    $('#stat-min').innerHTML = `${stats.min.toFixed(1)}<small>%</small>`;
    $('#stat-count').textContent = stats.count;

    // 趋势指示: 当前值 vs 平均值
    var trendEl = $('#stat-trend');
    if (trendEl && currentValue !== undefined) {
      var diff = currentValue - stats.avg;
      if (Math.abs(diff) < 0.3) {
        trendEl.className = 'stat-trend neutral';
        trendEl.textContent = '≈ 持平平均';
      } else if (diff > 0) {
        trendEl.className = 'stat-trend up';
        trendEl.textContent = '▲ 高于平均 ' + diff.toFixed(1) + '%';
      } else {
        trendEl.className = 'stat-trend down';
        trendEl.textContent = '▼ 低于平均 ' + Math.abs(diff).toFixed(1) + '%';
      }
    }
  }

  function addAlarmLog(entry) {
    const list = $('#log-list');
    const empty = list.querySelector('.log-empty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = 'log-entry alarm-high';
    const timeShort = entry.time.slice(-8);
    div.innerHTML = `<span class="time">${timeShort}</span> <span class="val">${entry.value.toFixed(1)}%</span> 🔴 超阈值`;
    list.insertBefore(div, list.firstChild);

    while (list.children.length > 5) list.removeChild(list.lastChild);
  }

  function updateAlarmState(alarming) {
    const bar = $('#alarm-glow-bar');
    bar.classList.toggle('active', alarming);
  }

  function updateBadges(online) {
    const badge = $('#online-badge');
    const wsBadge = $('#ws-badge');
    if (online) {
      badge.className = 'badge badge-normal';
      badge.textContent = '● 在线';
      wsBadge.className = 'badge badge-normal';
      wsBadge.textContent = '⬡ WebSocket';
    } else {
      badge.className = 'badge badge-danger';
      badge.textContent = '● 离线';
      wsBadge.className = 'badge badge-danger';
      wsBadge.textContent = '⬡ 断开';
    }
  }

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // 通过 Sec-WebSocket-Protocol 子协议传递 JWT token，避免在 URL 中暴露
    const token = Auth.getToken();
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    const subprotocols = token ? [`access_token.${token}`] : [];

    function connect() {
      state.ws = new WebSocket(wsUrl, subprotocols);
      state.ws.onopen = () => updateBadges(true);
      state.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'data') {
          handleData(msg);
          // 清除之前的错误状态
          var lastEl = $('#last-update');
          if (lastEl) lastEl.style.color = '';
        } else if (msg.type === 'error') {
          // 显示数据采集失败状态
          var lastEl = $('#last-update');
          if (lastEl) {
            lastEl.textContent = '⚠ 数据获取失败，请检查 OneNet 配置或设备连接';
            lastEl.style.color = '#f87171';
          }
          var wsBadge = $('#ws-badge');
          if (wsBadge) {
            wsBadge.className = 'badge badge-warn';
            wsBadge.textContent = '⬡ 无数据';
          }
        }
      };
      state.ws.onclose = () => {
        updateBadges(false);
        setTimeout(connect, 3000);
      };
      state.ws.onerror = () => state.ws.close();
    }
    connect();
  }

  function handleData(msg) {
    const { value, timestamp, alarming, stats } = msg;
    const threshold = state.settings.alarm_threshold;

    const timeShort = timestamp.slice(-8);
    // 更新"上次刷新"时间戳
    var lastEl = $('#last-update');
    if (lastEl) lastEl.textContent = '🕐 上次刷新: ' + timestamp;
    state.history.push({ time: timeShort, value });
    if (state.history.length > 50) state.history.shift();

    updateGauge(value, threshold, alarming);
    updateValueCard(value, state.prevValue);
    updateChart(state.history);
    updateProgress(value, threshold);
    updateStats(stats, value);
    updateAlarmState(alarming);

    if (alarming) {
      addAlarmLog({ time: timestamp, value });
    }

    if (alarming && !state.alarming) state.alarmCount++;
    state.alarming = alarming;
    state.prevValue = value;
  }

  function initSettings() {
    $('#btn-settings').addEventListener('click', () => {
      $('#settings-overlay').classList.remove('hidden');
      $('#setting-rate').value = state.settings.refresh_rate;
      $('#setting-threshold').value = state.settings.alarm_threshold;
      $('#setting-rate-val').textContent = state.settings.refresh_rate;
      $('#setting-threshold-val').textContent = state.settings.alarm_threshold;
    });

    $('#btn-close-settings').addEventListener('click', () => {
      $('#settings-overlay').classList.add('hidden');
    });

    $('#setting-rate').addEventListener('input', function () {
      $('#setting-rate-val').textContent = this.value;
    });
    $('#setting-threshold').addEventListener('input', function () {
      $('#setting-threshold-val').textContent = this.value;
    });

    $('#btn-save-settings').addEventListener('click', async () => {
      const rate = parseInt($('#setting-rate').value);
      const threshold = parseFloat($('#setting-threshold').value);
      try {
        // 使用 Auth.fetchWithAuth 而非普通 fetch — PUT /api/settings 需要鉴权
        const resp = await Auth.fetchWithAuth('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_rate: rate, alarm_threshold: threshold }),
        });
        if (!resp.ok) {
          const errData = await resp.json();
          console.error('保存设置失败:', errData.detail || resp.status);
          return;
        }
        state.settings.refresh_rate = rate;
        state.settings.alarm_threshold = threshold;
        $('#footer-rate').textContent = rate;
        $('#footer-threshold').textContent = threshold;
        $('#threshold-label').textContent = threshold;

        // 立即更新进度条上的阈值刻度线位置和文字
        var thresholdLine = $('#progress-threshold');
        if (thresholdLine) {
          thresholdLine.style.left = threshold + '%';
        }
        var markerEl = document.getElementById('threshold-marker');
        if (markerEl) markerEl.textContent = threshold;

        $('#settings-overlay').classList.add('hidden');
        if (state.ws) state.ws.close();
      } catch (e) { console.error('保存设置失败', e); }
    });

    $('#settings-overlay').addEventListener('click', function (e) {
      if (e.target === this) this.classList.add('hidden');
    });
  }

  function initExport() {
    $('#btn-export').addEventListener('click', async () => {
      // 使用 fetchWithAuth 带上 token，否则会被 AuthMiddleware 拦截返回 401
      try {
        var resp = await Auth.fetchWithAuth('/api/export/csv');
        if (!resp.ok) return;
        // 将响应内容转为 Blob 并触发浏览器下载
        var blob = await resp.blob();
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'saturation_data.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (e) { console.error('导出失败', e); }
    });
  }

  /**
   * 零权限用户: 清空所有仪表板内容，显示"无访问权限"提示。
   * 用户可正常登录但看不到任何监控数据和操作入口。
   */
  function showNoAccessPage() {
    // 清空主体内容区域
    var sections = [
      '#main-row', '#progress-section', '#stats-section',
      '#log-section', '#footer', '#settings-overlay'
    ];
    sections.forEach(function(sel) {
      var el = document.querySelector(sel);
      if (el) el.style.display = 'none';
    });

    // 更新顶栏状态
    var badge = document.getElementById('online-badge');
    if (badge) { badge.className = 'badge badge-danger'; badge.textContent = '● 无权限'; }
    var wsBadge = document.getElementById('ws-badge');
    if (wsBadge) { wsBadge.className = 'badge badge-danger'; wsBadge.textContent = '⬡ 已限制'; }
    var lastUpdate = document.getElementById('last-update');
    if (lastUpdate) { lastUpdate.textContent = '当前账号无访问权限'; }

    // 在页面中央插入提示卡片
    var body = document.body;
    var notice = document.createElement('div');
    notice.id = 'no-access-notice';
    notice.style.cssText =
      'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:100;' +
      'text-align:center;padding:40px 60px;border:1px solid rgba(255,170,0,0.25);' +
      'border-radius:12px;background:rgba(10,25,50,0.85);backdrop-filter:blur(10px);';
    notice.innerHTML =
      '<div style="font-size:48px;margin-bottom:16px;">🔒</div>' +
      '<h2 style="color:#ffaa00;font-size:22px;margin-bottom:8px;">无访问权限</h2>' +
      '<p style="color:#5a7a9a;font-size:15px;line-height:1.8;">' +
        '您的账号已成功登录，但未被分配任何角色和权限。<br>' +
        '请联系管理员为您分配适当的角色。' +
      '</p>' +
      '<button onclick="Auth.logout()" style="margin-top:20px;' +
        'background:rgba(255,170,0,0.1);border:1px solid rgba(255,170,0,0.3);' +
        'color:#ffaa00;padding:8px 20px;border-radius:6px;cursor:pointer;font-size:14px;">' +
        '↩ 返回登录</button>';
    body.appendChild(notice);
  }

  async function init() {
    // 零权限用户: 显示无权访问提示，不调用任何 API
    var user = Auth.getUser();
    if (!user || !user.permissions || user.permissions.length === 0) {
      showNoAccessPage();
      return;
    }

    // 如果用户拥有用户管理或角色管理权限，显示顶栏"🔑 管理"按钮
    if (Auth.hasPermission('users:manage') || Auth.hasPermission('roles:manage')) {
      var btnAdmin = $('#btn-admin');
      if (btnAdmin) btnAdmin.style.display = '';
    }

    // 从服务器拉取当前运行时设置（避免硬编码默认值）
    try {
      var resp = await Auth.fetchWithAuth('/api/settings');
      if (resp.ok) {
        var serverSettings = await resp.json();
        state.settings.refresh_rate = serverSettings.refresh_rate;
        state.settings.alarm_threshold = serverSettings.alarm_threshold;
      }
    } catch (e) { /* 获取失败使用默认值 */ }

    // 更新页面上所有依赖设置值的元素
    $('#footer-rate').textContent = state.settings.refresh_rate;
    $('#footer-threshold').textContent = state.settings.alarm_threshold;
    $('#threshold-label').textContent = state.settings.alarm_threshold;
    var tLine = $('#progress-threshold');
    if (tLine) tLine.style.left = state.settings.alarm_threshold + '%';
    var mEl = document.getElementById('threshold-marker');
    if (mEl) mEl.textContent = state.settings.alarm_threshold;

    Particles.init('particles-canvas');
    initChart();
    initSettings();
    initExport();
    connectWebSocket();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
