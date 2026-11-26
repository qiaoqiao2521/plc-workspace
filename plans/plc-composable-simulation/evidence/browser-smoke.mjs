/**
 * Optional real-browser smoke test. No mocked simulation responses.
 * See README.md in this directory for dependency and environment setup.
 * Starts its own loopback service; Playwright is NOT a product dependency.
 */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtemp, mkdir, readFile, writeFile, rm} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createServer} from 'node:net';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const repo = fileURLToPath(new URL('../../../', import.meta.url));
const temporary = await mkdtemp(path.join(os.tmpdir(), 'plc-browser-smoke-'));
const output = process.env.PLC_BROWSER_EVIDENCE_DIR
  ? path.resolve(process.env.PLC_BROWSER_EVIDENCE_DIR)
  : await mkdtemp(path.join(os.tmpdir(), 'plc-browser-evidence-'));
await mkdir(output, {recursive: true});
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLC_BROWSER_PLAYWRIGHT || 'playwright');
const {makeRequest, conveyorAcceptanceBrief} = await import(pathToFileURL(path.join(repo, 'web/generation-model.js')));
const report = {schema: 'plc-browser-smoke/v1', status: 'running', timestamp: new Date().toISOString(),
  browser: '', checks: [], physical_review: 'not_run',
  scope: 'Real browser + native matiec/GCC simulation + optional OIP. No Siemens or hardware acceptance.'};
const passed = name => { report.checks.push({name, status: 'pass'}); console.log(`PASS ${name}`); };
const redactions = [repo, temporary, process.env.PLC_OIP_CHECKOUT, process.env.PLC_OIP_DIR,
  process.env.SIM_IEC2C, process.env.SIM_MATIEC_LIB].filter(Boolean).sort((a, b) => b.length - a.length);
function sanitize(value) {
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, sanitize(child)]));
  if (typeof value === 'string') {
    for (const prefix of redactions) value = value.split(prefix).join('<local-path>');
    return value.replace(/\/(?:tmp|home|workspace|opt|var|private)\/[^\s"'<>]+/g, '<runtime-path>');
  }
  return value;
}
const saveJson = (name, value) => writeFile(path.join(output, name), JSON.stringify(sanitize(value), null, 2) + '\n');
async function freePort() {
  if (process.env.PLC_BROWSER_PORT) return Number(process.env.PLC_BROWSER_PORT);
  const server = createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function service(mode = 'native') {
  const port = await freePort();
  const env = {...process.env, PYTHONUNBUFFERED: '1'};
  // The smoke service needs no generation provider or credentials.
  for (const key of Object.keys(env)) if (key.startsWith('PLC_API_')) delete env[key];
  if (mode !== 'native') { delete env.SIM_IEC2C; delete env.SIM_MATIEC_LIB; }
  const args = mode === 'static'
    ? ['-m', 'http.server', String(port), '--bind', '127.0.0.1', '--directory', 'web/dist']
    : ['web/scripts/local-server.py', '--port', String(port), '--runtime-root', path.join(temporary, `runtime-${mode}`)];
  const child = spawn(process.env.PLC_BROWSER_PYTHON || 'python3', args,
    {cwd: repo, env, detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe']});
  let logs = '';
  child.stderr.on('data', data => { logs = (logs + data).slice(-4000); });
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { child.kill(); reject(new Error('Test service startup timed out')); }, 25000);
    child.stdout.on('data', data => { if (/PLC Workspace:|Serving HTTP/.test(String(data))) { clearTimeout(timeout); resolve(); } });
    child.once('error', error => { clearTimeout(timeout); reject(error); });
    child.once('exit', code => { clearTimeout(timeout); reject(new Error(`Test service exited ${code}: ${logs}`)); });
  });
  return {url: `http://127.0.0.1:${port}`, async close() {
    if (child.exitCode !== null) return;
    await new Promise(resolve => {
      const timeout = setTimeout(() => {
        try { if (process.platform !== 'win32') process.kill(-child.pid, 'SIGKILL'); else child.kill('SIGKILL'); } catch {}
        resolve();
      }, 3000);
      child.once('exit', () => { clearTimeout(timeout); resolve(); }); child.kill('SIGINT');
    });
  }};
}

let browser, active;
try {
  assert.ok(process.env.SIM_IEC2C && process.env.SIM_MATIEC_LIB, 'Set SIM_IEC2C and SIM_MATIEC_LIB to the real native toolchain');
  await readFile(path.join(repo, 'web/dist/simulator.html')); // Run the repository build first.
  browser = await chromium.launch({headless: true,
    ...(process.env.PLC_BROWSER_CHROMIUM ? {executablePath: process.env.PLC_BROWSER_CHROMIUM} : {}),
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser = browser.version();
  active = await service();
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(active.url + '/simulator.html');
  await page.waitForFunction(() => !document.querySelector('#create-session').disabled);
  await page.waitForSelector('#scene canvas');
  assert.equal(await page.locator('#component-count').textContent(), '10 件');
  await page.screenshot({path: path.join(output, 'simulator-desktop.png'), fullPage: true});
  passed('ten component scene renders with actual WebGL');
  await page.locator('#create-session').click();
  await page.waitForFunction(() => !document.querySelector('#start').disabled);
  await page.locator('#start').click();
  await page.waitForFunction(() => document.querySelector('#scan-count').textContent === '1');
  assert.match(await page.locator('#plc-outputs').innerText(), /Motor\s+1/);
  await page.locator('#step').click();
  await page.waitForFunction(() => document.querySelector('#scan-count').textContent === '2');
  await page.locator('#fault-device').selectOption('belt');
  await page.locator('#fault-type').selectOption('jam');
  await page.locator('#inject-fault').click();
  await page.waitForFunction(() => document.querySelector('#active-faults').textContent.includes('jam'));
  await page.locator('#clear-fault').click();
  await page.waitForFunction(() => document.querySelector('#active-faults').textContent === '未施加故障');
  const pusherResponse = page.waitForResponse(response => response.url().endsWith('/api/sim/run_case'));
  await page.locator('#run-case').click();
  const pusherReport = await (await pusherResponse).json();
  await page.waitForFunction(() => document.querySelector('#case-result').classList.contains('pass'));
  assert.equal(pusherReport.status, 'pass');
  await saveJson('browser-pusher-case.json', pusherReport);
  await page.locator('.trace-row').first().click();
  assert.match(await page.locator('#view-tag').textContent(), /回看/);
  await page.locator('#show-live').click();
  assert.equal(await page.locator('#scan-count').textContent(), '2');
  passed('native pusher scans, fault injection, independent case and replay');

  await page.locator('#template-select').selectOption('latch-start-stop-v1');
  assert.equal(await page.locator('#test-case option').count(), 2);
  assert.equal(await page.locator('#input-reset').isVisible(), false);
  await page.locator('#create-session').click();
  await page.waitForFunction(() => !document.querySelector('#start').disabled);
  await page.locator('#start').click();
  await page.waitForFunction(() => document.querySelector('#scan-count').textContent === '1');
  assert.match(await page.locator('#plc-outputs').innerText(), /Motor\s+1/);
  await page.locator('#stop').click();
  await page.waitForFunction(() => document.querySelector('#scan-count').textContent === '2');
  assert.match(await page.locator('#plc-outputs').innerText(), /Motor\s+0/);
  assert.doesNotMatch(await page.locator('#scene-state').textContent(), /null/);
  passed('latch has supported controls and cases without invented State');

  await page.locator('#template-select').selectOption('conveyor-12-v1');
  await page.locator('#component-type').selectOption('lamp');
  await page.locator('#add-component').click();
  assert.equal(await page.locator('#start').isDisabled(), true);
  const motor = page.locator('#bindings-list .binding-row').filter({has: page.locator('label').filter({hasText: 'Motor'})});
  await motor.getByRole('button', {name: '添加设备目标'}).click();
  await page.getByLabel('PLC 输出 Motor 的第 3 个设备目标').selectOption('lamp1.value');
  const downloaded = page.waitForEvent('download'); await page.locator('#export-scene').click();
  const sceneFile = path.join(temporary, 'assembled-scene.json'); await (await downloaded).saveAs(sceneFile);
  await page.locator('#create-session').click();
  await page.waitForFunction(() => !document.querySelector('#start').disabled);
  await page.locator('#start').click();
  await page.waitForFunction(() => document.querySelector('#scan-count').textContent === '1');
  await page.locator('[data-component="lamp1"]').click();
  assert.match(await page.locator('#component-state').innerText(), /value\s+true/);
  await page.locator('.trace-row[data-scan="0"]').click();
  await page.locator('[data-component="lamp1"]').click();
  assert.match(await page.locator('#component-state').innerText(), /value\s+false/);
  await page.locator('#scene-file').setInputFiles(sceneFile);
  await page.waitForFunction(() => document.querySelector('#scene-state').textContent.includes('配置预览'));
  assert.equal(await page.locator('#start').isDisabled(), true);
  await page.locator('#create-session').click();
  await page.waitForFunction(() => !document.querySelector('#start').disabled);
  await page.locator('#start').click();
  await page.waitForFunction(() => document.querySelector('#scan-count').textContent === '1');
  await page.locator('[data-component="lamp1"]').click();
  assert.match(await page.locator('#component-state').innerText(), /value\s+true/);
  passed('added lamp receives typed PLC output, replay and scene JSON roundtrip');
  await page.locator('#remove-component').click();
  assert.equal(await page.locator('[data-component="lamp1"]').count(), 0);
  assert.equal(await page.locator('#start').isDisabled(), true);
  passed('component removal invalidates the old run');

  await page.locator('#template-select').selectOption('conveyor-pusher-v1');
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: path.join(output, 'simulator-mobile.png'), fullPage: true});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.goto(active.url + '/');
  assert.equal(await page.locator('.mobile-workspace-links a[href="./simulator.html"]').isVisible(), true);
  assert.equal(await page.locator('#simulate-current').isDisabled(), true);
  passed('390px mobile has no horizontal overflow and a visible generation entry');

  const source = await readFile(path.join(repo, 'web/data/simulation/conveyor-12.scl'), 'utf8');
  const sourceHash = createHash('sha256').update(source).digest('hex');
  const request = await makeRequest(conveyorAcceptanceBrief(source), []);
  const result = {schema_version: 1, request_id: request.request_id, request_fingerprint: request.request_fingerprint,
    summary: 'Browser handoff fixture', questions: [], states: [], io: [],
    scl_files: [{name: 'FB_ConveyorPack.scl', content: source}], lad_networks: [], checks: []};
  const engineering = {kind: 'agent_candidate', request, result,
    verification: {status: 'pass', files: [{name: 'FB_ConveyorPack.scl', sha256: sourceHash}], checks: []},
    workflow: {verdict: 'accepted'}};
  const file = path.join(temporary, 'engineering.json'); await writeFile(file, JSON.stringify(engineering));
  await page.locator('#project-file').setInputFiles(file);
  await page.waitForFunction(() => !document.querySelector('#simulate-current').disabled);
  await page.locator('#simulate-current').click();
  await page.waitForURL('**/simulator.html?engineering=1');
  await page.waitForFunction(() => document.querySelector('#program-detail').textContent.includes('当前工程'));
  const handoff = await page.evaluate(() => JSON.parse(sessionStorage.getItem('plc-workspace-simulation-engineering-v1')));
  assert.deepEqual(Object.keys(handoff).sort(), ['kind', 'request', 'result']);
  assert.equal(handoff.result.scl_files[0].content, source);
  assert.equal(await page.locator('#template-select').inputValue(), 'conveyor-12-v1');
  assert.equal(await page.locator('#scan-count').textContent(), '0');
  await page.locator('#create-session').click();
  await page.waitForFunction(() => !document.querySelector('#start').disabled);
  assert.match(await page.locator('#source-hash').textContent(), new RegExp(sourceHash));
  report.engineering_source_sha256 = sourceHash;
  passed('generation hands off exact source and request without acceptance');
  if (process.env.PLC_BROWSER_OIP === '1') {
    await page.waitForFunction(() => !document.querySelector('#run-oip').disabled, {timeout: 30000});
    const response = page.waitForResponse(response => response.url().endsWith('/api/sim/oip_test'), {timeout: 120000});
    await page.locator('#run-oip').click();
    const physical = await (await response).json();
    await page.waitForFunction(() => !document.querySelector('#oip-details').hidden);
    assert.equal(physical.status, 'pass'); assert.equal(physical.source_sha256, sourceHash);
    await saveJson('browser-oip-current-engineering.json', physical);
    report.physical_review = 'pass'; passed('current source executes in OIP physical review from UI');
  }
  const mutated = structuredClone(engineering); delete mutated.verification; delete mutated.workflow;
  mutated.result.scl_files[0].content = source.replace('nextWaitCount >= 12', 'nextWaitCount >= 8');
  assert.notEqual(mutated.result.scl_files[0].content, source);
  const mutantFile = path.join(temporary, 'mutated-engineering.json'); await writeFile(mutantFile, JSON.stringify(mutated));
  await page.locator('#engineering-file').setInputFiles(mutantFile);
  await page.waitForFunction(() => document.querySelector('#start').disabled && document.querySelector('#scan-count').textContent === '0');
  await page.locator('#test-case').selectOption('jam');
  const negativeResponse = page.waitForResponse(response => response.url().endsWith('/api/sim/run_case'));
  await page.locator('#run-case').click();
  const negative = await (await negativeResponse).json();
  await page.waitForFunction(() => document.querySelector('#case-result').classList.contains('fail'));
  assert.equal(negative.status, 'fail'); assert.equal(negative.first_failure.scan, 9);
  await page.locator('#show-failure').click();
  assert.match(await page.locator('#view-tag').textContent(), /回看 · 9/);
  assert.doesNotMatch(await page.locator('#scene-state').textContent(), /null/);
  assert.equal(await page.locator('.trace-row.failed').count(), 1);
  assert.equal(await page.locator('#export-trace').isDisabled(), false);
  await page.setViewportSize({width: 1440, height: 1100});
  await page.screenshot({path: path.join(output, 'simulator-counterexample.png'), fullPage: true});
  await saveJson('browser-counterexample.json', negative);
  passed('changed timeout produces a real first counterexample at scan 9');

  // Independently exercise the engineering page's error state after a successful import.
  await page.goto(active.url + '/');
  await page.waitForFunction(() => sessionStorage.getItem('plc-workspace-simulation-engineering-v1') === null);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('plc-workspace-simulation-engineering-v1')), null);
  await page.locator('#project-file').setInputFiles(file);
  await page.waitForFunction(() => !document.querySelector('#simulate-current').disabled);
  const tampered = structuredClone(engineering); tampered.request.brief.name += ' changed without updating fingerprint';
  const invalidFile = path.join(temporary, 'invalid-engineering.json'); await writeFile(invalidFile, JSON.stringify(tampered));
  await page.locator('#project-file').setInputFiles(invalidFile);
  await page.waitForFunction(() => document.querySelector('#message').classList.contains('error'));
  assert.match(await page.locator('#message').textContent(), /指纹不匹配/);
  assert.equal(await page.locator('#project-name').inputValue(), request.brief.name);
  await page.screenshot({path: path.join(output, 'generation-import-error.png'), fullPage: true});
  report.engineering_error_message = await page.locator('#message').textContent();
  await page.locator('#requirement').fill(request.brief.requirement + ' Edited process.');
  assert.equal(await page.locator('#simulate-current').isDisabled(), true);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('plc-workspace-simulation-engineering-v1')), null);
  passed('engineering import rejects tampered identity and edits invalidate handoff');
  assert.deepEqual(errors, []); passed('no uncaught browser errors during the complete flow');
  await page.close(); await active.close(); active = null;

  for (const mode of ['missing-native', 'static']) {
    active = await service(mode);
    const unavailable = await browser.newPage();
    await unavailable.goto(active.url + '/simulator.html');
    await unavailable.waitForFunction(() => !document.querySelector('#message').hidden);
    assert.equal(await unavailable.locator('#create-session').isDisabled(), true);
    assert.equal(await unavailable.locator('#run-case').isDisabled(), true);
    assert.equal(await unavailable.locator('#scan-count').textContent(), '0');
    report.checks.push({name: mode, status: 'pass', message: await unavailable.locator('#message').textContent()});
    await unavailable.close(); await active.close(); active = null;
  }
  report.status = 'pass';
} catch (error) {
  report.status = 'fail'; report.error = String(error.stack || error); process.exitCode = 1;
} finally {
  await active?.close(); await browser?.close();
  await saveJson('browser-smoke-result.json', report);
  await rm(temporary, {recursive: true, force: true});
  console.log(`Browser smoke ${report.status}; evidence: ${output}`);
}
