// Pinned, headless plant bridge. It never attaches OIP's PLC engine: the caller owns every PLC scan.
import { createRequire } from 'node:module';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';

const [checkoutArg, projectArg] = process.argv.slice(2);
if (!checkoutArg || !projectArg) throw new Error('usage: node bridge.mjs <pinned-oip-checkout> <assembled-project>');
const checkout = resolve(checkoutArg);
const projectFolder = resolve(projectArg);
const requireOip = createRequire(join(checkout, 'package.json'));
const { createServer } = await import(pathToFileURL(requireOip.resolve('vite')).href);
const { declareBuiltIns } = await import(pathToFileURL(join(checkout, 'scripts/lib/builtIns.mjs')).href);
const { readProjectFolder } = await import(pathToFileURL(join(checkout, 'scripts/lib/projectFolderFiles.mjs')).href);
const vite = await createServer({
  configFile: false, root: checkout, logLevel: 'error',
  server: { middlewareMode: true, hmr: false, ws: false, watch: null },
  appType: 'custom', optimizeDeps: { noDiscovery: true },
});
let world;
const emit = (value) => process.stdout.write(JSON.stringify(value) + '\n');
try {
  const built = await declareBuiltIns(vite);
  if (built.failures.length) throw new Error(JSON.stringify(built.failures));
  const { folderFilesToProject } = await vite.ssrLoadModule('/src/core/project/projectFolder.ts');
  const { validatePart, formatPartDiagnostics } = await vite.ssrLoadModule('/src/sim/validatePart.ts');
  const { registerPackage } = await vite.ssrLoadModule('/src/core/parts/partRegistry.ts');
  const { SimWorld } = await vite.ssrLoadModule('/src/sim/world.ts');
  const initJolt = (await vite.ssrLoadModule('jolt-physics')).default;
  const loaded = folderFilesToProject(readProjectFolder(projectFolder), {
    bakePart(manifestJson, behaviorJs) {
      const result = validatePart(JSON.parse(manifestJson), behaviorJs);
      return result.ok && result.package ? { package: result.package } : { error: formatPartDiagnostics(result.diagnostics) };
    },
  });
  if (!loaded.ok) throw new Error('Project rejected: ' + JSON.stringify(loaded.errors));
  const project = loaded.project;
  if ((project.stProgram ?? '').trim()) throw new Error('Native bridge refuses a project with a second PLC program');
  for (const pkg of project.packages ?? []) registerPackage(pkg, true);
  for (const pkg of project.scene.packages ?? []) registerPackage(pkg, false);
  const scene = project.scene;
  const Jolt = await initJolt();
  let jammed = false;
  let bodyId;
  let logicalSteps = 0;
  const snapshot = () => {
    const f = world.frame();
    return {
      physics_hz: 60, physics_steps: logicalSteps, sim_time_s: logicalSteps / 60,
      plant_time_s: f.simTime, tags: world.behaviorTagWrites(),
      conveyor_speeds: f.conveyorSpeeds ?? {}, beam_hits: f.beamHits ?? {}, jammed,
      cargo: Array.from(f.ids, (id, i) => ({
        id, part: f.partIds[i], position: Array.from(f.positions.slice(i * 3, i * 3 + 3)),
        quaternion: Array.from(f.quats.slice(i * 4, i * 4 + 4)),
        half_extents: Array.from(f.halfExtents.slice(i * 3, i * 3 + 3)),
      })),
    };
  };
  const reset = () => {
    world?.dispose();
    world = new SimWorld(Jolt, scene, { hz: 60 });
    world.setBehaviorDrivenTags(['Motor']);
    world.setBehaviorInputTags({ Motor: false });
    // Settle the initially placed cargo before the first PLC scan; this is recorded, not PLC time.
    for (let i = 0; i < 30; i++) world.step();
    logicalSteps = 0;
    jammed = false;
    const f = world.frame();
    const row = f.partIds.findIndex((name) => name === 'cargo');
    if (row < 0) throw new Error('Assembled cargo was not found in the real physics world');
    bodyId = f.ids[row];
    return snapshot();
  };
  emit({ ok: true, ready: true, native_plc_attached: false, startup_settle_steps: 30, state: reset() });
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    try {
      if (line.length > 4096) throw new Error('Request too large');
      const request = JSON.parse(line);
      if (request.op === 'close') { emit({ ok: true, closed: true }); break; }
      if (request.op === 'reset') { emit({ ok: true, state: reset() }); continue; }
      if (request.op !== 'step' || typeof request.motor !== 'boolean' || typeof request.jam !== 'boolean'
          || !Number.isInteger(request.steps) || request.steps < 1 || request.steps > 60) {
        throw new Error('Expected step with motor/jam booleans and 1..60 physics steps');
      }
      if (request.jam !== jammed) {
        if (!world.pinBody(bodyId, request.jam)) throw new Error('Jam did not act on the cargo; refusing a silent no-op');
        jammed = request.jam;
      }
      world.setBehaviorInputTags({ Motor: request.motor });
      for (let i = 0; i < request.steps; i++) { world.step(); logicalSteps++; }
      emit({ ok: true, state: snapshot() });
    } catch (error) {
      emit({ ok: false, error: error instanceof Error ? error.message : String(error) });
    }
  }
} catch (error) {
  emit({ ok: false, error: error instanceof Error ? error.stack : String(error) });
  process.exitCode = 1;
} finally {
  world?.dispose();
  await vite.close();
}
