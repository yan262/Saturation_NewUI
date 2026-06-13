/**
 * 背景粒子动画 — 缓慢飘动的微小光点，营造科技感氛围。
 */
const Particles = {
  _particles: [],
  _canvas: null,
  _ctx: null,
  _animId: null,

  init(canvasId) {
    this._canvas = document.getElementById(canvasId);
    this._ctx = this._canvas.getContext('2d');
    this._resize();
    window.addEventListener('resize', () => this._resize());

    const count = 50;
    for (let i = 0; i < count; i++) {
      this._particles.push({
        x: Math.random() * this._canvas.width,
        y: Math.random() * this._canvas.height,
        r: Math.random() * 1.5 + 0.5,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        alpha: Math.random() * 0.4 + 0.1,
      });
    }
    this._animate();
  },

  _resize() {
    this._canvas.width = window.innerWidth;
    this._canvas.height = window.innerHeight;
  },

  _animate() {
    this._ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);

    for (const p of this._particles) {
      p.x += p.vx;
      p.y += p.vy;

      if (p.x < 0 || p.x > this._canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > this._canvas.height) p.vy *= -1;

      this._ctx.beginPath();
      this._ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      this._ctx.fillStyle = `rgba(0, 229, 255, ${p.alpha})`;
      this._ctx.fill();
    }

    this._ctx.strokeStyle = 'rgba(0, 229, 255, 0.04)';
    this._ctx.lineWidth = 0.5;
    for (let i = 0; i < this._particles.length; i++) {
      for (let j = i + 1; j < this._particles.length; j++) {
        const a = this._particles[i], b = this._particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          this._ctx.beginPath();
          this._ctx.moveTo(a.x, a.y);
          this._ctx.lineTo(b.x, b.y);
          this._ctx.stroke();
        }
      }
    }

    this._animId = requestAnimationFrame(() => this._animate());
  },
};
