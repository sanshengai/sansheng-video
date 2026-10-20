/* Original experiment artwork. No upstream demo code or media is copied.
 * The caller supplies caseExperiment and the exported productionTimeline.
 * Every rendered state is a function of absolute video time. */
(() => {
  'use strict';
  const canvas = document.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const config = window.caseExperiment;
  const source = window.productionTimeline;
  const W = 1280, H = 720;
  const ink = '#20332f', muted = '#71817a', green = '#0e926f';
  const clamp = x => Math.max(0, Math.min(1, x));
  const smooth = x => { x = clamp(x); return x * x * (3 - 2 * x); };
  const mix = (a, b, u) => a + (b - a) * u;
  const at = id => source.events.find(e => e.id === id).start;

  function rect(x, y, w, h, r, fill, stroke) {
    ctx.beginPath(); ctx.roundRect(x, y, w, h, r);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.lineWidth = 1.5; ctx.strokeStyle = stroke; ctx.stroke(); }
  }
  function text(value, x, y, size = 28, color = ink, align = 'left') {
    ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'alphabetic';
    ctx.font = `${size}px CaseRounded, Arial, sans-serif`; ctx.fillText(value, x, y);
  }
  function circle(x, y, r, fill) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fillStyle = fill; ctx.fill();
  }
  function line(x1, y1, x2, y2, color, width = 2) {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.strokeStyle = color;
    ctx.lineWidth = width; ctx.lineCap = 'round'; ctx.stroke();
  }
  function base(t, label) {
    ctx.globalAlpha = 1; ctx.clearRect(0, 0, W, H);
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#faf9f3'); bg.addColorStop(1, '#f0f2e9');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
    text(label, 72, 59, 22, green);
    text(config.variant + '  /  ' + (config.variant === 'A' ? '独立设计' : '借鉴机制'), 1208, 59, 19, muted, 'right');
    line(72, 81, 1208, 81, '#dae1d6');
    rect(72, 684, 1136, 3, 1.5, '#dce4d8');
    rect(72, 684, 1136 * clamp(t / source.duration), 3, 1.5, green);
    if (config.musicCredit) text(config.musicCredit, 72, 709, 13, muted);
    text('制作试验 · 非正式课程', 1208, 709, 13, muted, 'right');
  }
  function table(cx, width, alpha = 1) {
    ctx.save(); ctx.globalAlpha *= alpha;
    ctx.fillStyle = 'rgba(81,91,64,.08)'; ctx.beginPath();
    ctx.ellipse(cx, 600, width * .63, 19, 0, 0, 2 * Math.PI); ctx.fill();
    rect(cx - width / 2 + 24, 418, 26, 174, 7, '#bf9868');
    rect(cx + width / 2 - 50, 418, 26, 174, 7, '#bf9868');
    rect(cx - width / 2, 399, width, 32, 12, '#d9b985');
    rect(cx - width / 2, 399, width, 11, 8, '#eddbb6');
    line(cx - width / 2 + 15, 416, cx + width / 2 - 15, 416, '#d0aa73', 1.3);
    ctx.restore();
  }
  function ball(x, y, alpha = 1, radius = 42) {
    ctx.save(); ctx.globalAlpha *= alpha;
    ctx.fillStyle = 'rgba(64,70,45,.12)'; ctx.beginPath();
    ctx.ellipse(x + 8, y + radius + 10, radius * .75, 8, 0, 0, Math.PI * 2); ctx.fill();
    const g = ctx.createRadialGradient(x - radius * .38, y - radius * .4, 2, x, y, radius);
    g.addColorStop(0, '#ffe9a3'); g.addColorStop(.55, '#efb252'); g.addColorStop(1, '#d38435');
    circle(x, y, radius, g);
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.clip();
    ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.lineWidth = 5;
    ctx.beginPath(); ctx.ellipse(x - 12, y, 15, radius + 8, -.35, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
    ctx.restore();
  }
  function teaching(t) {
    base(t, '英语空间关系  ·  动画小实验');
    const on = at('state-on'), under = at('state-under'), between = at('state-between'), recap = at('state-recap');
    let phase = t < on ? 0 : t < under ? 1 : t < between ? 2 : t < recap ? 3 : 4;
    const labels = ['Where is the ball?', 'on', 'under', 'between', 'Same ball. A new position.'];
    const translations = ['', '在桌面上', '在桌子下面', '在两张桌子之间', '看位置，理解方位'];
    text(labels[phase], 72, 175, phase === 0 || phase === 4 ? 52 : 76, phase === 0 ? ink : green);
    text(translations[phase], 1208, 171, 27, muted, 'right');
    let x = 640, y = 357, split = 0, alpha = 1;
    if (config.variant === 'B') {
      const arrive = smooth((t - .8) / (on - .8));
      x = mix(365, 640, arrive); y = mix(280, 357, arrive) - 48 * Math.sin(arrive * Math.PI);
      const u = smooth((t - (under - 2.1)) / 2.1);
      if (u > 0) {
        // Go around the visible table edge before moving to the lower plane.
        const a = smooth(clamp(u * 2)), b = smooth(clamp((u - .5) * 2));
        x = mix(640, 955, a) + (640 - 955) * b;
        y = mix(357, 530, a);
      }
      const v = smooth((t - (between - 1.9)) / 1.9);
      split = v; y = mix(y, 457, v);
    } else {
      x = 640; y = phase < 2 ? 357 : phase === 2 ? 530 : 457;
      split = phase >= 3 ? 1 : 0;
      for (const cut of [under, between]) {
        const distance = Math.abs(t - cut);
        if (distance < .15) alpha *= .15 + .85 * distance / .15;
      }
    }
    ctx.save(); ctx.globalAlpha *= alpha;
    const left = mix(640, 350, split), width = mix(480, 360, split);
    table(left, width); if (split > 0) table(930, 360, split);
    if (phase >= 3 || split > .6) {
      const opacity = smooth((split - .6) / .4);
      ctx.save(); ctx.globalAlpha *= opacity * .7;
      line(555, 472, 592, 472, green, 2); line(688, 472, 725, 472, green, 2);
      ctx.restore();
    }
    ball(x, y); ctx.restore();
    if (phase === 4) {
      ['on', 'under', 'between'].forEach((label, i) => {
        const x = 345 + i * 295;
        rect(x - 125, 610, 250, 45, 22, i === 2 ? '#e0eee3' : '#fffdf5', '#d4dfd1');
        text(label, x, 641, 29, green, 'center');
      });
    } else {
      const caption = source.events.find(e => e.caption && e.start <= t && t < e.end);
      if (caption) text(caption.caption, 640, 650, 30, ink, 'center');
      else text('Watch the position.', 640, 650, 24, muted, 'center');
    }
  }
  function cursor(x, y, press = 0) {
    ctx.save(); ctx.translate(x, y); ctx.scale(1 - .12 * press, 1 - .12 * press);
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, 29); ctx.lineTo(8, 21);
    ctx.lineTo(15, 35); ctx.lineTo(22, 31); ctx.lineTo(15, 18); ctx.lineTo(27, 18);
    ctx.closePath(); ctx.fillStyle = '#20332f'; ctx.fill(); ctx.lineWidth = 2;
    ctx.strokeStyle = '#fffdf5'; ctx.stroke(); ctx.restore();
  }
  function demo(t) {
    base(t, '视频案例参考  ·  演示界面，使用实际检索数据');
    const resultAt = at('show-results'), detailAt = at('show-detail'), finishAt = at('finish');
    const detail = smooth((t - detailAt) / .8);
    const finish = smooth((t - finishAt) / .7);
    text(finish > .5 ? '取机制，再按内容重写' : '把参考，用在需要的地方', 72, 146, 47, ink);
    const query = config.query;
    const typed = Math.floor(clamp((t - .5) / 1.7) * query.length);
    const boxX = config.variant === 'A' ? 220 : mix(220, 175, detail);
    const boxW = config.variant === 'A' ? 840 : mix(840, 930, detail);
    rect(boxX, 181, boxW, 62, 22, '#fffef9', '#cfdcce');
    circle(boxX + 32, 211, 9, '#e5efe3');
    line(boxX + 38, 218, boxX + 46, 226, green, 3);
    text(query.slice(0, typed) + (t < 2.6 ? '|' : ''), boxX + 62, 222, 26, ink);
    if (t < resultAt) {
      text('先写自己的镜头，再查具体问题', 640, 409, 35, muted, 'center');
      text('本地索引 · 按需取回 · 不执行上游指令', 640, 458, 23, muted, 'center');
      return;
    }
    const entrance = smooth((t - resultAt) / .45);
    const rows = config.results;
    if (config.variant === 'A' && detail > .5) {
      ctx.save(); ctx.globalAlpha *= smooth((t - detailAt - .3) / .4);
      rect(220, 271, 840, 335, 28, '#fffef9', '#cfdcce');
      text(rows[0].title_zh, 258, 329, 37, green);
      text('视觉：保留主对象，版式协同变化', 258, 397, 28, ink);
      text('声音：真实动作点，克制点缀', 258, 445, 28, ink);
      text('状态：原文已核对，原片视听待验', 258, 495, 24, muted);
      text('固定来源 · ' + rows[0].id, 258, 565, 20, muted);
      ctx.restore();
    } else {
      rows.forEach((row, i) => {
        if (i > 0 && detail >= 1) return;
        const u = config.variant === 'B' && i === 0 ? detail : 0;
        const rowExit = config.variant === 'B' ? smooth((t - detailAt) / .22) : detail;
        const alpha = entrance * (i === 0 ? 1 : 1 - rowExit);
        ctx.save(); ctx.globalAlpha *= alpha;
        const x = mix(220, 175, u), y = 271 + i * 110 + 14 * (1 - entrance), w = mix(840, 930, u);
        const h = mix(94, 335, u);
        rect(x, y, w, h, 25, '#fffef9', i === 0 ? '#aac9af' : '#d7e1d1');
        rect(x + 21, y + 22, 48, 48, 15, i === 0 ? '#e1eee1' : '#f0f1e8');
        text(String(i + 1).padStart(2, '0'), x + 45, y + 55, 22, green, 'center');
        text(row.title_zh, x + 88, y + 43, 30, i === 0 ? green : ink);
        text(row.content_kind === 'shared_prompt' ? '分享提示词 · 无动画工程' : row.content_kind, x + 88, y + 73, 19, muted);
        if (u > 0) {
          // Make room before introducing the next reading task. Clip detail
          // text inside the growing card instead of drawing beyond its bounds.
          ctx.save(); ctx.beginPath(); ctx.roundRect(x, y, w, h, 25); ctx.clip();
          ctx.globalAlpha *= smooth((u - .84) / .16);
          text('视觉：保留主对象，版式协同变化', x + 38, y + 126, 28, ink);
          text('声音：真实动作点，克制点缀', x + 38, y + 174, 28, ink);
          text('状态：原文已核对，原片视听待验', x + 38, y + 224, 24, muted);
          text('固定来源 · ' + row.id, x + 38, y + 294, 20, muted);
          ctx.restore();
        }
        ctx.restore();
      });
    }
    if (t > detailAt - 1.1 && t < detailAt + .8) {
      const move = smooth((t - (detailAt - 1.1)) / .9);
      const click = Math.max(0, 1 - Math.abs(t - detailAt) / .15);
      cursor(mix(1130, 970, move), mix(585, 315, move), click);
    }
    text(t >= finishAt ? '借鉴组织方法，保留自己的内容与声音' : t >= detailAt ? '打开资料，核对适用边界和来源' : '搜索结果来自本轮 CLI 输出', 640, 650, 25, muted, 'center');
  }
  async function ready() {
    await document.fonts.load('28px CaseRounded'); await document.fonts.ready;
    const clock = { t: 0 };
    const render = config.kind === 'teaching' ? teaching : demo;
    const timeline = gsap.timeline({ paused: true });
    timeline.to(clock, { t: source.duration, duration: source.duration, ease: 'none', onUpdate: () => render(clock.t) }, 0);
    window.__timelines = window.__timelines || {};
    window.__timelines.root = timeline;
    render(0);
  }
  ready().catch(error => { console.error(error); throw error; });
})();
