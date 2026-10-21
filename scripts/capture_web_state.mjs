// Call with an already authorized Playwright page. Does not launch a browser.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

const stable = value => Array.isArray(value) ? value.map(stable) :
  value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])])) : value;
const sha = value => crypto.createHash('sha256').update(value).digest('hex');

export async function captureWebState(page, {output, id, controls, copied = null}) {
  if (!id || !controls || typeof controls !== 'object' || Array.isArray(controls)) throw Error('id and controls required');
  const destination = path.resolve(output);
  const image = destination.replace(/\.json$/, '') + '.png';
  if (!destination.endsWith('.json')) throw Error('output must end with .json');
  for (const file of [destination, image]) {
    try { await fs.access(file); throw Error(`output exists: ${file}`); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  const measure = () => page.evaluate(selectors => {
    const result = {url: location.href, viewport: [innerWidth, innerHeight],
      scroll: [scrollX, scrollY], dpr: devicePixelRatio, controls: {}};
    for (const [name, selector] of Object.entries(selectors)) {
      const el = document.querySelector(selector);
      if (!el) throw Error(`missing control: ${name}`);
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) throw Error(`invisible control: ${name}`);
      result.controls[name] = {selector, rect: [r.x, r.y, r.width, r.height],
        text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim(),
        value: 'value' in el ? String(el.value) : null, href: el.href || null};
    }
    return result;
  }, controls);
  const before = await measure();
  const bytes = await page.screenshot({type: 'png', fullPage: false, scale: 'device'});
  const after = await measure();
  if (JSON.stringify(stable(before)) !== JSON.stringify(stable(after))) throw Error('page changed during capture; recapture stable state');
  const context = {url: before.url, viewport: before.viewport, scroll: before.scroll,
    dpr: before.dpr, image_sha256: sha(bytes)};
  const context_sha256 = sha(JSON.stringify(stable(context)));
  for (const control of Object.values(before.controls)) control.context_sha256 = context_sha256;
  if (copied && (!['intercepted_writeText', 'observed_copy_result'].includes(copied.method) || !copied.text)) {
    throw Error('copied requires an observed text and declared capture method');
  }
  const record = {kind: 'web-state/1', id, ...context, context_sha256,
    image: path.basename(image), captured_at: new Date().toISOString(),
    controls: before.controls, copied, method: 'real_state_synthetic_camera'};
  await fs.mkdir(path.dirname(destination), {recursive: true});
  await fs.writeFile(image, bytes, {flag: 'wx'});
  await fs.writeFile(destination, JSON.stringify(record, null, 2) + '\n', {flag: 'wx'});
  return record;
}
