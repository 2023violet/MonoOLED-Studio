// G2 spike (throwaway): mirrors spike/slint workload; latency = input to the next presented frame.
const invoke = window.__TAURI__.core.invoke;
const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function summary(samples) {
  const v = [...samples].sort((a, b) => a - b);
  const pick = (q) => v[Math.round((v.length - 1) * q)] ?? 0;
  return { n: v.length, p50_ms: +pick(0.5).toFixed(3), p95_ms: +pick(0.95).toFixed(3), max_ms: +pick(1).toFixed(3) };
}

function codeText() {
  let text = '#pragma once\n#include <stdint.h>\n\nstatic const uint8_t frames[] = {\n';
  let n = 0;
  while (text.length < 256 * 1024) {
    let line = '    ';
    for (let i = 0; i < 16; i++, n++) line += '0x' + ((n * 37) % 251).toString(16).toUpperCase().padStart(2, '0') + ', ';
    text += line + '\n';
  }
  return text + '};\n';
}

async function run() {
  const started = performance.now();
  await wait(1500);
  const idle = await invoke('idle_memory');

  const canvas = document.getElementById('canvas');
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(256, 128);
  for (let i = 3; i < image.data.length; i += 4) image.data[i] = 255;
  ctx.putImageData(image, 0, 0);
  const stroke = [];
  for (let step = 1; step < 400; step++) {
    const t0 = performance.now();
    const i = step % 256, j = Math.floor(step / 2) % 128, o = (j * 256 + i) * 4;
    image.data[o] = image.data[o + 1] = image.data[o + 2] = 255;
    ctx.putImageData(image, 0, 0, i, j, 1, 1);
    await nextFrame();
    stroke.push(performance.now() - t0);
    await wait(2);
  }

  canvas.style.display = 'none';
  const code = document.getElementById('code');
  code.style.display = 'block';
  let t0 = performance.now();
  code.textContent = codeText();
  await nextFrame();
  const textFirst = performance.now() - t0;

  code.style.display = 'none';
  const scene = document.getElementById('scene');
  scene.style.display = 'block';
  const items = [];
  for (let k = 0; k < 50; k++) {
    const el = document.createElement('div');
    el.className = 'item';
    el.style.left = (20 + (k % 10) * 110) + 'px';
    el.style.top = (20 + Math.floor(k / 10) * 150) + 'px';
    scene.appendChild(el);
    items.push({ el, x: 20 + (k % 10) * 110 });
  }
  await nextFrame();
  const drag = [];
  for (let step = 0; step < 200; step++) {
    t0 = performance.now();
    for (const item of items) { item.x += 1; item.el.style.left = item.x + 'px'; }
    await nextFrame();
    drag.push(performance.now() - t0);
    await wait(2);
  }

  await invoke('report', { json: JSON.stringify({
    framework: 'tauri 2.12.0 (WebView2)',
    idle_private_bytes_tree: idle,
    canvas_stroke: summary(stroke),
    text_256k_first_frame_ms: +textFirst.toFixed(3),
    scene_50_drag: summary(drag),
    total_s: +((performance.now() - started) / 1000).toFixed(2),
  }) });
}

run();
