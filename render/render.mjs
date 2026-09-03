// Renders grid squares of Google Photorealistic 3D Tiles with a fixed tilted orthographic camera.
// Usage: node render/render.mjs --grid grid.json --out renders/ [--only i,j] [--force]
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const args = Object.fromEntries(process.argv.slice(2).map((a,i,arr)=>a.startsWith('--')?[a.slice(2), (arr[i+1]&&!arr[i+1].startsWith('--'))?arr[i+1]:true]:null).filter(Boolean));
const env = Object.fromEntries(fs.readFileSync(new URL('../.env', import.meta.url)).toString().split('\n').filter(l=>l.includes('=')).map(l=>l.split('=')));
const KEY = env.MAPS_API_KEY;
const grid = JSON.parse(fs.readFileSync(args.grid,'utf8'));
const outDir = args.out || 'renders';
fs.mkdirSync(outDir,{recursive:true});
const SERVER = process.env.SERVER || 'http://127.0.0.1:8765';

const only = args.only ? String(args.only).split(';').map(s=>s.split(',').map(Number)) : null;
const squares = grid.squares.filter(s=>!only || only.some(([i,j])=>i===s.i&&j===s.j));

const browser = await chromium.launch({
  headless:true, executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist','--enable-webgl','--disable-features=PostQuantumKyber,EncryptedClientHello,UseMLKEM','--ssl-version-max=tls1.2','--no-sandbox','--disable-dev-shm-usage','--max-old-space-size=4096'],
  proxy: process.env.https_proxy ? {server: process.env.https_proxy, bypass:'127.0.0.1,localhost'} : undefined,
});
const ctx = await browser.newContext({viewport:{width:2048,height:2048}, deviceScaleFactor:1, ignoreHTTPSErrors:true});
const page = await ctx.newPage();
page.on('console', m=>{ if (m.type()==='error') console.log('[page]', m.text().slice(0,200)); });

const t0 = Date.now();
for (const s of squares){
  const file = path.join(outDir, `sq_${s.i}_${s.j}.png`);
  if (fs.existsSync(file) && !args.force){ console.log('skip', file); continue; }
  const p = new URLSearchParams({key:KEY, lon:grid.origin.lon, lat:grid.origin.lat, h0:grid.origin.h0, heading:grid.heading, pitch:grid.pitch, W:grid.W, u:s.u, v:s.v, D:grid.D||4000, sse:grid.sse||4});
  const url = `${SERVER}/render/render.html?${p}`;
  const ts = Date.now();
  await page.goto(url, {waitUntil:'load'});
  await page.waitForFunction(()=>window.STATUS && (window.STATUS.ready || window.STATUS.error), null, {timeout:120000});
  const err = await page.evaluate(()=>window.STATUS.error);
  if (err){ console.error('ERROR', s.i, s.j, err); continue; }
  // wait until tiles loaded and stable
  let stable = 0, waited = 0;
  const MAXWAIT = parseInt(process.env.MAXWAIT||'900000');
  while (stable < 6 && waited < MAXWAIT){
    await page.waitForTimeout(500); waited += 500;
    const st = await page.evaluate(()=>({loaded: window.STATUS.tilesLoaded, pending: window.STATUS.pending, proc: window.STATUS.processing, frames: window.STATUS.frames}));
    if (st.loaded && !st.pending && !st.proc) stable++; else stable = 0;
  }
  if (stable < 6){ console.error(`FAIL ${s.i},${s.j}: tiles never settled after ${waited/1000}s — not saved`); continue; }
  await page.waitForTimeout(1000);
  await page.screenshot({path:file, clip:{x:0,y:0,width:2048,height:2048}, timeout:120000});
  console.log(`rendered ${s.i},${s.j} in ${((Date.now()-ts)/1000).toFixed(1)}s (waited ${waited/1000}s)`);
}
console.log('total', ((Date.now()-t0)/1000).toFixed(0), 's');
await browser.close();
