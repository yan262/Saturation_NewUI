/**
 * 240° SVG 弧形仪表盘（底部开口）
 * ==================================
 * 用法: GaugeRenderer.render(container, value, threshold, alarming)
 *
 * 架构: 首次调用用 innerHTML 创建完整 SVG，后续调用只更新
 *       指针位置/颜色和中心数值/颜色（不移除 DOM），避免
 *       innerHTML 反复替换导致的 SVG 渲染异常和字符乱码。
 *
 * ★ 字号调整位置（搜索 "★ 可调字号"）:
 *   刻度数字 (0, 20, 40...) — font-size="12"
 *   中心大数值 (72.5%)     — font-size="44"
 *   中心标签 "饱和度"        — font-size="13"
 */
const GaugeRenderer = {
  _container: null,
  _initialized: false,

  render(container, value, threshold, alarming) {
    // 容错: 确保 value 是有效数字
    if (typeof value !== 'number' || isNaN(value)) { value = 0; }
    // 钳制到 0~100，防止极值导致显示异常
    value = Math.min(Math.max(value, 0), 100);

    // 容器变了 → 重新初始化
    if (this._container !== container) {
      this._container = container;
      this._initialized = false;
    }

    // ---------- 首次渲染: 创建完整 SVG ----------
    if (!this._initialized) {
      this._createSvg(container);
      this._initialized = true;
    }

    // ---------- 增量更新: 只改指针和数值 ----------
    this._updateNeedle(value, threshold, alarming);
  },

  /** 创建完整 SVG 结构，后续不再重建 */
  _createSvg(container) {
    var cx = 150, cy = 130;        // 圆心
    var trackR = 100, trackW = 18; // 轨道半径/线宽
    var viewW = 300, viewH = 280;  // 视口
    var startAngle = 210, totalArc = 240;

    // 极坐标 → 直角坐标
    function pt(angleDeg, dist) {
      var rad = (angleDeg * Math.PI) / 180;
      return {
        x: cx + dist * Math.cos(rad),
        y: cy + dist * Math.sin(rad),
      };
    }

    // 弧线端点
    var leftPt = pt(startAngle, trackR);
    var rightPt = pt(startAngle - totalArc, trackR);

    // 色区: 绿 0-60%, 黄 60-85%, 红 85-100%（固定，不随阈值变）
    var greenEnd  = pt(startAngle - 0.60 * totalArc, trackR);
    var yellowEnd = pt(startAngle - 0.85 * totalArc, trackR);
    var arcAttrs = trackR + ' ' + trackR + ' 0 0 0';  // sweep-flag=0 逆时针

    // 刻度线
    var ticksMarkup = '';
    for (var pct = 0; pct <= 100; pct += 20) {
      var a = startAngle - (pct / 100) * totalArc;
      var p1 = pt(a, trackR + 5);
      var p2 = pt(a, trackR + 16);
      var lb = pt(a, trackR + 34);
      ticksMarkup +=
        '<line x1="' + p1.x.toFixed(1) + '" y1="' + p1.y.toFixed(1) + '" ' +
        'x2="' + p2.x.toFixed(1) + '" y2="' + p2.y.toFixed(1) + '" ' +
        'stroke="#3a5a7a" stroke-width="1.5"/>' +
        '<text x="' + lb.x.toFixed(1) + '" y="' + lb.y.toFixed(1) + '" ' +
        'text-anchor="middle" fill="#5a7a9a" font-size="12" ' +  /* ★ 可调字号: 刻度数字 */
        'font-family="\'JetBrains Mono\', monospace">' + pct + '</text>';
    }

    container.innerHTML =
      '<svg width="100%" viewBox="0 0 ' + viewW + ' ' + viewH + '" style="max-width:340px;">' +
        // ---- 滤镜定义 ----
        '<defs>' +
          '<filter id="gauge-glow-green">' +
            '<feGaussianBlur stdDeviation="3" result="blur"/>' +
            '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>' +
          '</filter>' +
          '<filter id="gauge-glow-red">' +
            '<feGaussianBlur stdDeviation="4" result="blur"/>' +
            '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>' +
          '</filter>' +
          '<filter id="gauge-glow-needle">' +
            '<feGaussianBlur stdDeviation="3.5" result="blur"/>' +
            '<feMerge><feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>' +
          '</filter>' +
        '</defs>' +

        // ---- 灰色底轨 ----
        '<path d="M' + leftPt.x.toFixed(1) + ' ' + leftPt.y.toFixed(1) + ' ' +
          'A' + arcAttrs + ' ' + rightPt.x.toFixed(1) + ' ' + rightPt.y.toFixed(1) + '" ' +
          'fill="none" stroke="#1a2a40" stroke-width="' + trackW + '" stroke-linecap="round"/>' +

        // ---- 绿色安全区 (0-60%) ----
        '<path d="M' + leftPt.x.toFixed(1) + ' ' + leftPt.y.toFixed(1) + ' ' +
          'A' + arcAttrs + ' ' + greenEnd.x.toFixed(1) + ' ' + greenEnd.y.toFixed(1) + '" ' +
          'fill="none" stroke="#00ff88" stroke-width="' + (trackW - 4) + '" ' +
          'stroke-linecap="butt" filter="url(#gauge-glow-green)" opacity="0.9"/>' +

        // ---- 黄色警告区 (60-85%) ----
        '<path d="M' + greenEnd.x.toFixed(1) + ' ' + greenEnd.y.toFixed(1) + ' ' +
          'A' + arcAttrs + ' ' + yellowEnd.x.toFixed(1) + ' ' + yellowEnd.y.toFixed(1) + '" ' +
          'fill="none" stroke="#ffaa00" stroke-width="' + (trackW - 4) + '" ' +
          'stroke-linecap="butt" opacity="0.9"/>' +

        // ---- 红色危险区 (85-100%) ----
        '<path d="M' + yellowEnd.x.toFixed(1) + ' ' + yellowEnd.y.toFixed(1) + ' ' +
          'A' + arcAttrs + ' ' + rightPt.x.toFixed(1) + ' ' + rightPt.y.toFixed(1) + '" ' +
          'fill="none" stroke="#ff3333" stroke-width="' + (trackW - 4) + '" ' +
          'stroke-linecap="butt" filter="url(#gauge-glow-red)" opacity="0.9"/>' +

        // ---- 刻度线 ----
        ticksMarkup +

        // ---- 指针（动态更新）----
        '<line id="gauge-needle" x1="0" y1="0" x2="0" y2="0" ' +
          'stroke="#00ff66" stroke-width="4.5" stroke-linecap="round" ' +
          'filter="url(#gauge-glow-needle)"/>' +

        // ---- 圆心帽（动态更新）----
        '<circle id="gauge-dot" cx="' + cx + '" cy="' + cy + '" r="7" ' +
          'fill="#060b14" stroke="#00ff66" stroke-width="4" ' +
          'filter="url(#gauge-glow-needle)"/>' +

        // ---- 中心数值（动态更新）----
        '<text id="gauge-value" x="' + cx + '" y="' + (cy - 36) + '" ' +
          'text-anchor="middle" fill="#00e5ff" font-size="44" font-weight="900" ' +   /* ★ 可调字号: 中心大数值 */
          'font-family="\'Orbitron\', monospace">--.-%</text>' +

        // ---- 中心标签 ----
        '<text x="' + cx + '" y="' + (cy + 26) + '" text-anchor="middle" ' +
          'fill="#5a7a9a" font-size="13" font-family="\'Orbitron\', monospace" ' +   /* ★ 可调字号: 中心标签 */
          'letter-spacing="4">饱和度</text>' +
      '</svg>';
  },

  /** 增量更新指针位置/颜色和中心数值 */
  _updateNeedle(value, threshold, alarming) {
    var cx = 150, cy = 130;
    var trackR = 100;
    var startAngle = 210, totalArc = 240;

    // 极坐标
    function pt(angleDeg, dist) {
      var rad = (angleDeg * Math.PI) / 180;
      return {
        x: cx + dist * Math.cos(rad),
        y: cy + dist * Math.sin(rad),
      };
    }

    // 指针角度
    var valRatio = value / 100;
    var angle = startAngle - valRatio * totalArc;
    var base = pt(angle, 12);
    var tip  = pt(angle, trackR - 6);

    // 颜色
    var needleColor = alarming ? '#ff4444' : (value < 60 ? '#00ff66' : '#ffbb00');
    var textColor = alarming ? '#ff3333' : '#00e5ff';
    var textFilter = alarming ? 'url(#gauge-glow-red)' : '';

    // 更新指针线
    var needle = document.getElementById('gauge-needle');
    if (needle) {
      needle.setAttribute('x1', base.x.toFixed(1));
      needle.setAttribute('y1', base.y.toFixed(1));
      needle.setAttribute('x2', tip.x.toFixed(1));
      needle.setAttribute('y2', tip.y.toFixed(1));
      needle.setAttribute('stroke', needleColor);
    }

    // 更新圆心帽
    var dot = document.getElementById('gauge-dot');
    if (dot) {
      dot.setAttribute('stroke', needleColor);
    }

    // 更新中心数值
    var valEl = document.getElementById('gauge-value');
    if (valEl) {
      valEl.textContent = value.toFixed(1) + '%';
      valEl.setAttribute('fill', textColor);
      if (textFilter) {
        valEl.setAttribute('filter', textFilter);
      } else {
        valEl.removeAttribute('filter');
      }
    }
  },
};
