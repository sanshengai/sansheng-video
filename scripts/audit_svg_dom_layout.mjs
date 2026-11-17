#!/usr/bin/env node
/**
 * Browser Chromium DOM & SVG geometry preflight gate for HyperFrames 1920x1080 plates.
 *
 * Detects visual collisions & overflows BEFORE spending minutes rendering video:
 *   1. Missing `.stage` root or overflowing `.stage` scrollHeight
 *   2. `.topbar` `.hdr-lockup` colliding with `.era-pill` (< 20px gap or multi-line wrap)
 *   3. SVG `<text>` extending beyond `<svg viewBox>` bounds
 *   4. SVG `<text>` overflowing an enclosing card/pill `<rect>` border
 *   5. Pairwise SVG `<text>` bounding-box overlaps & unmasked `<line>`/`<polygon>`/`<circle>`/`<ellipse>` collisions
 *
 * Usage:
 *   node audit_svg_dom_layout.mjs --html <file-or-dir> [--timeout-ms 15000] [--json]
 *   node audit_svg_dom_layout.mjs --self-test
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

function loadPlaywright(playwrightFrom) {
  const candidates = [];
  if (playwrightFrom) {
    const p = path.resolve(playwrightFrom);
    candidates.push(p.endsWith(".json") ? p : path.join(p, "package.json"));
  }
  if (process.env.SANSHENG_PLAYWRIGHT_FROM) {
    const p = path.resolve(process.env.SANSHENG_PLAYWRIGHT_FROM);
    candidates.push(p.endsWith(".json") ? p : path.join(p, "package.json"));
  }
  for (const base of [process.cwd(), path.dirname(new URL(import.meta.url).pathname)]) {
    let cur = path.resolve(base);
    while (true) {
      candidates.push(path.join(cur, "package.json"));
      const parent = path.dirname(cur);
      if (parent === cur) break;
      cur = parent;
    }
  }
  for (const pkg of candidates) {
    if (fs.existsSync(pkg)) {
      try {
        return createRequire(pkg)("playwright");
      } catch {
        // try next candidate
      }
    }
  }
  return createRequire(import.meta.url)("playwright");
}

function findChromiumExecutable(chromium) {
  try {
    const pwExec = chromium.executablePath();
    if (pwExec && fs.existsSync(pwExec)) return pwExec;
  } catch {
    // ignore missing default binary
  }
  const hfBase = path.join(os.homedir(), ".cache/hyperframes/chrome/chrome-headless-shell");
  if (fs.existsSync(hfBase)) {
    for (const ver of fs.readdirSync(hfBase).sort().reverse()) {
      const bin = path.join(hfBase, ver, "chrome-headless-shell-mac-arm64", "chrome-headless-shell");
      if (fs.existsSync(bin)) return bin;
    }
  }
  return undefined;
}

async function auditOnePage(page, htmlPath, timeoutMs) {
  await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: "load", timeout: timeoutMs });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
    if (window.__timelines && typeof window.__timelines === "object") {
      for (const tl of Object.values(window.__timelines)) {
        if (tl && typeof tl.progress === "function") tl.progress(1);
      }
    }
  });
  await page.waitForTimeout(40);

  return page.evaluate(() => {
    const issues = [];
    const stage = document.querySelector(".stage");
    if (!stage) {
      issues.push("missing required .stage container");
      return issues;
    }

    const lockup = document.querySelector(".topbar .hdr-lockup");
    const pill = document.querySelector(".topbar .era-pill");
    if (lockup && pill) {
      const lr = lockup.getBoundingClientRect();
      const pr = pill.getBoundingClientRect();
      if (lr.height > 88) {
        issues.push(`.topbar .hdr-lockup wrapped taller than 88px (${lr.height.toFixed(1)}px)`);
      }
      if (pr.left - lr.right < 20) {
        issues.push(`.topbar gap between .hdr-lockup and .era-pill is ${(pr.left - lr.right).toFixed(1)}px (< 20px)`);
      }
    }

    const sr = stage.getBoundingClientRect();
    if (stage.scrollHeight > stage.clientHeight + 4 && stage.clientHeight > 0) {
      issues.push(`.stage vertical overflow: scrollHeight=${stage.scrollHeight} > clientHeight=${stage.clientHeight}`);
    }
    if (sr.height > 810) {
      issues.push(`.stage height ${sr.height.toFixed(1)}px exceeds 810px safe zone`);
    }

    function segIntersectsRect(x1, y1, x2, y2, rx0, ry0, rx1, ry1) {
      if (Math.max(x1, x2) < rx0 || Math.min(x1, x2) > rx1 || Math.max(y1, y2) < ry0 || Math.min(y1, y2) > ry1) {
        return false;
      }
      const steps = 12;
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        const px = x1 + (x2 - x1) * t;
        const py = y1 + (y2 - y1) * t;
        if (px >= rx0 && px <= rx1 && py >= ry0 && py <= ry1) return true;
      }
      return false;
    }

    function isOpaqueFill(fill) {
      if (!fill || fill === "none" || fill === "transparent") return false;
      if (fill.startsWith("rgba(")) {
        const m = fill.match(/rgba\([^,]+,[^,]+,[^,]+,\s*([0-9.]+)\s*\)/);
        return !m || parseFloat(m[1]) >= 0.88;
      }
      return true;
    }

    const svgs = [...document.querySelectorAll("svg")];
    for (let si = 0; si < svgs.length; si++) {
      const svg = svgs[si];
      const svgRect = svg.getBoundingClientRect();
      if (svgRect.width <= 48 && svgRect.height <= 48) continue;
      const vb = svg.viewBox?.baseVal;
      if (!vb || vb.width <= 0 || vb.height <= 0) continue;

      const allNodes = [...svg.querySelectorAll("*")];
      const domOrder = new Map(allNodes.map((n, idx) => [n, idx]));
      const visible = (el) => {
        const cs = getComputedStyle(el);
        return cs.display !== "none" && cs.visibility !== "hidden" && parseFloat(cs.opacity || "1") > 0.05;
      };

      const rects = [...svg.querySelectorAll("rect")]
        .filter(visible)
        .map((r) => ({
          el: r,
          idx: domOrder.get(r) ?? 0,
          x: r.x.baseVal.value,
          y: r.y.baseVal.value,
          w: r.width.baseVal.value,
          h: r.height.baseVal.value,
          fill: r.getAttribute("fill") || getComputedStyle(r).fill,
        }));

      const texts = [...svg.querySelectorAll("text")]
        .filter((t) => visible(t) && (t.textContent || "").trim().length > 0)
        .map((t) => {
          const b = t.getBBox();
          return {
            el: t,
            idx: domOrder.get(t) ?? 0,
            label: (t.textContent || "").trim().slice(0, 32),
            x: b.x,
            y: b.y,
            w: b.width,
            h: b.height,
            cx: b.x + b.width / 2,
            cy: b.y + b.height / 2,
          };
        });

      const lines = [...svg.querySelectorAll("line")]
        .filter(visible)
        .map((l) => ({
          el: l,
          idx: domOrder.get(l) ?? 0,
          x1: l.x1.baseVal.value,
          y1: l.y1.baseVal.value,
          x2: l.x2.baseVal.value,
          y2: l.y2.baseVal.value,
        }));

      const polys = [...svg.querySelectorAll("polygon")]
        .filter(visible)
        .map((p) => {
          const pts = [...p.points].map((pt) => ({ x: pt.x, y: pt.y }));
          return { el: p, idx: domOrder.get(p) ?? 0, b: p.getBBox(), pts };
        });

      const circles = [...svg.querySelectorAll("circle")]
        .filter(visible)
        .map((c) => ({
          el: c,
          idx: domOrder.get(c) ?? 0,
          cx: c.cx.baseVal.value,
          cy: c.cy.baseVal.value,
          r: c.r.baseVal.value,
          fill: c.getAttribute("fill") || getComputedStyle(c).fill,
        }));

      const maskAfter = (obstacleIdx, cx, cy, textIdx) =>
        rects.some(
          (r) =>
            r.idx > obstacleIdx &&
            r.idx < textIdx &&
            isOpaqueFill(r.fill) &&
            cx >= r.x &&
            cx <= r.x + r.w &&
            cy >= r.y &&
            cy <= r.y + r.h
        ) ||
        circles.some(
          (c) =>
            c.idx > obstacleIdx &&
            c.idx < textIdx &&
            isOpaqueFill(c.fill) &&
            (cx - c.cx) ** 2 + (cy - c.cy) ** 2 <= c.r ** 2
        );

      for (const t of texts) {
        if (
          t.x < vb.x - 2 ||
          t.y < vb.y - 2 ||
          t.x + t.w > vb.x + vb.width + 2 ||
          t.y + t.h > vb.y + vb.height + 2
        ) {
          issues.push(
            `SVG#${si} text "${t.label}" [${t.x.toFixed(1)},${t.y.toFixed(1)}..${(t.x + t.w).toFixed(1)},${(t.y + t.h).toFixed(1)}] clips viewBox [0,0..${vb.width},${vb.height}]`
          );
        }

        // Find tightest card/pill <rect> that encloses text's center
        const enclosing = rects
          .filter(
            (r) =>
              r.w >= 40 &&
              r.h >= 24 &&
              r.w < vb.width * 0.94 &&
              t.cx >= r.x - 8 &&
              t.cx <= r.x + r.w + 8 &&
              t.cy >= r.y &&
              t.cy <= r.y + r.h
          )
          .sort((a, b) => a.w * a.h - b.w * b.h)[0];

        if (enclosing) {
          if (
            t.x < enclosing.x - 2.5 ||
            t.x + t.w > enclosing.x + enclosing.w + 2.5 ||
            t.y < enclosing.y - 2.5 ||
            t.y + t.h > enclosing.y + enclosing.h + 2.5
          ) {
            issues.push(
              `SVG#${si} text "${t.label}" [${t.x.toFixed(1)}..${(t.x + t.w).toFixed(1)}] overflows enclosing rect [${enclosing.x.toFixed(1)}..${(enclosing.x + enclosing.w).toFixed(1)}, y=${enclosing.y.toFixed(1)}..${(enclosing.y + enclosing.h).toFixed(1)}]`
            );
          }
        }

        // Unmasked line crossing inset text bbox (skip horizontal strikethroughs drawn after the text)
        const ix0 = t.x + 3;
        const iy0 = t.y + 3;
        const ix1 = t.x + t.w - 3;
        const iy1 = t.y + t.h - 3;
        if (ix1 > ix0 && iy1 > iy0) {
          for (const ln of lines) {
            const isStrikeAfterText = ln.idx > t.idx && Math.abs(ln.y2 - ln.y1) <= 2;
            if (!isStrikeAfterText && !maskAfter(ln.idx, t.cx, t.cy, t.idx) && segIntersectsRect(ln.x1, ln.y1, ln.x2, ln.y2, ix0, iy0, ix1, iy1)) {
              issues.push(
                `SVG#${si} line (${ln.x1},${ln.y1})->(${ln.x2},${ln.y2}) crosses text "${t.label}"`
              );
            }
          }
          for (const pg of polys) {
            if (maskAfter(pg.idx, t.cx, t.cy, t.idx)) continue;
            const pb = pg.b;
            const ow = Math.min(ix1, pb.x + pb.width) - Math.max(ix0, pb.x);
            const oh = Math.min(iy1, pb.y + pb.height) - Math.max(iy0, pb.y);
            if (ow > 4 && oh > 4) {
              issues.push(`SVG#${si} polygon overlaps text "${t.label}" by ${ow.toFixed(1)}x${oh.toFixed(1)}`);
            }
          }
        }
      }

      // Pairwise SVG text overlap (inset y by 3px per box to absorb SVG line-box ascender/descender padding)
      for (let i = 0; i < texts.length; i++) {
        for (let j = i + 1; j < texts.length; j++) {
          const a = texts[i];
          const b = texts[j];
          const ow = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
          const oh = Math.min(a.y + a.h - 3, b.y + b.h - 3) - Math.max(a.y + 3, b.y + 3);
          if (ow > 3 && oh > 2) {
            issues.push(`SVG#${si} texts overlap (${ow.toFixed(1)}x${oh.toFixed(1)}): "${a.label}" vs "${b.label}"`);
          }
        }
      }
    }

    return issues;
  });
}

async function runAudit(files, timeoutMs, playwrightFrom) {
  const { chromium } = loadPlaywright(playwrightFrom);
  const executablePath = findChromiumExecutable(chromium);
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const results = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
    const page = await context.newPage();
    for (const file of files) {
      const issues = await auditOnePage(page, file, timeoutMs);
      results.push({ file, ok: issues.length === 0, issues });
    }
    await context.close();
  } finally {
    await browser.close();
  }
  return results;
}

async function runSelfTest(playwrightFrom) {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "hf-dom-audit-test-"));
  const baseCss = `
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { width: 1920px; height: 1080px; background: #0D1015; font-family: "PingFang SC", sans-serif; }
    .topbar { display: flex; justify-content: space-between; align-items: center; padding: 24px 72px; }
    .hdr-lockup { display: flex; align-items: center; gap: 16px; white-space: nowrap; }
    .era-pill { padding: 8px 18px; border-radius: 99px; white-space: nowrap; }
    .stage { width: 1776px; height: 784px; margin: 0 auto; }
  `;
  const wrap = (topbar, body) => `<!doctype html><html><head><meta charset="utf-8"><style>${baseCss}</style></head><body>${topbar}<div class="stage">${body}</div></body></html>`;

  const cleanFile = path.join(tmpDir, "clean.html");
  fs.writeFileSync(
    cleanFile,
    wrap(
      `<div class="topbar"><div class="hdr-lockup"><span>一页 · L01 Short Title</span></div><div class="era-pill">第一幕</div></div>`,
      `<svg viewBox="0 0 800 200" style="width:800px;height:200px;"><rect x="20" y="20" width="260" height="80" rx="8" fill="#102922"/><text x="150" y="68" text-anchor="middle" fill="#fff" font-size="24">short label</text></svg>`
    )
  );

  const missingStageFile = path.join(tmpDir, "missing-stage.html");
  fs.writeFileSync(missingStageFile, `<!doctype html><html><body><div>No stage</div></body></html>`);

  const topbarCollideFile = path.join(tmpDir, "topbar-collide.html");
  fs.writeFileSync(
    topbarCollideFile,
    `<!doctype html><html><head><meta charset="utf-8"><style>${baseCss}</style></head><body><div class="topbar"><div class="hdr-lockup" style="width:1700px;overflow:visible;"><span>Very wide title colliding into pill</span></div><div class="era-pill">第一幕</div></div><div class="stage"></div></body></html>`
  );

  const svgOverflowFile = path.join(tmpDir, "svg-text-overflow.html");
  fs.writeFileSync(
    svgOverflowFile,
    wrap(
      `<div class="topbar"><div class="hdr-lockup"><span>L01</span></div><div class="era-pill">第一幕</div></div>`,
      `<svg viewBox="0 0 800 200" style="width:800px;height:200px;"><rect x="40" y="40" width="160" height="70" rx="8" fill="#102922"/><text x="120" y="82" text-anchor="middle" fill="#fff" font-size="28">make / let / have + us · see / hear</text></svg>`
    )
  );

  const lineCrossTextFile = path.join(tmpDir, "line-cross-text.html");
  fs.writeFileSync(
    lineCrossTextFile,
    wrap(
      `<div class="topbar"><div class="hdr-lockup"><span>L01</span></div><div class="era-pill">第一幕</div></div>`,
      `<svg viewBox="0 0 800 200" style="width:800px;height:200px;"><line x1="20" y1="80" x2="600" y2="80" stroke="#F2D492" stroke-width="5"/><text x="300" y="88" text-anchor="middle" fill="#3AEAB6" font-size="26">跨过去状态跃迁</text></svg>`
    )
  );

  try {
    const res = await runAudit([cleanFile, missingStageFile, topbarCollideFile, svgOverflowFile, lineCrossTextFile], 15000, playwrightFrom);
    const byName = Object.fromEntries(res.map((r) => [path.basename(r.file), r]));
    if (!byName["clean.html"].ok) {
      console.error("SELF-TEST FAIL: clean.html failed:", byName["clean.html"].issues);
      return 1;
    }
    for (const neg of ["missing-stage.html", "topbar-collide.html", "svg-text-overflow.html", "line-cross-text.html"]) {
      if (byName[neg].ok) {
        console.error(`SELF-TEST FAIL: ${neg} was NOT rejected!`);
        return 1;
      }
      console.log(`  [PASS rejected ${neg}]: ${byName[neg].issues[0]}`);
    }
    console.log("audit_svg_dom_layout --self-test PASSED (clean passed; 4/4 negative mutations rejected).");
    return 0;
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

function parseArgs(argv) {
  const out = { html: null, selfTest: false, timeoutMs: 15000, json: false, playwrightFrom: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--self-test") out.selfTest = true;
    else if (a === "--json") out.json = true;
    else if (a === "--html") out.html = argv[++i];
    else if (a === "--playwright-from") out.playwrightFrom = argv[++i];
    else if (a === "--timeout-ms") out.timeoutMs = parseInt(argv[++i], 10) || 15000;
    else throw new Error(`Unknown argument: ${a}`);
  }
  return out;
}

const args = parseArgs(process.argv);
if (args.selfTest) {
  process.exit(await runSelfTest(args.playwrightFrom));
}
if (!args.html) {
  console.error("Usage: audit_svg_dom_layout.mjs --html <file-or-dir> | --self-test");
  process.exit(2);
}

const target = path.resolve(args.html);
const st = fs.statSync(target);
const files = st.isDirectory()
  ? fs
      .readdirSync(target)
      .filter((f) => f.endsWith(".html"))
      .sort()
      .map((f) => path.join(target, f))
  : [target];

if (files.length === 0) {
  console.error(`No .html files found in ${target}`);
  process.exit(2);
}

const results = await runAudit(files, args.timeoutMs, args.playwrightFrom);
const failed = results.filter((r) => !r.ok);
if (args.json) {
  console.log(JSON.stringify({ total: results.length, failed: failed.length, results }, null, 2));
} else {
  for (const r of failed) {
    console.error(`FAIL ${path.basename(r.file)}:`);
    for (const iss of r.issues) console.error(`  - ${iss}`);
  }
  console.log(`DOM_SVG_AUDIT: ${results.length - failed.length}/${results.length} passed`);
}
process.exit(failed.length ? 1 : 0);
