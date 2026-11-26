import * as THREE from 'three';
import {OrbitControls} from './vendor/three/OrbitControls.js';

// Every pose comes from a scene definition or an executed snapshot. Rendering
// never advances the PLC, moves the plant, or predicts a sensor result.
export function createAssemblyView(container, {onSelect = () => {}} = {}) {
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 1.7));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.16;
  renderer.domElement.setAttribute('aria-label', '设备三维场景，点击组件可查看状态');
  renderer.domElement.tabIndex = 0;
  container.prepend(renderer.domElement);
  const world = new THREE.Scene();
  world.background = new THREE.Color('#e6edf2');
  world.fog = new THREE.Fog('#e6edf2', 17, 43);
  const camera = new THREE.PerspectiveCamera(36, 1, 0.05, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  controls.dampingFactor = 0.09;
  controls.minDistance = 3;
  controls.maxDistance = 35;
  controls.maxPolarAngle = Math.PI * 0.49;
  const focus = new THREE.Vector3(0, 0.7, 0);
  let viewDistance = 8;
  world.add(new THREE.HemisphereLight('#f6fcff', '#a8b1b8', 2.7));
  const key = new THREE.DirectionalLight('#fff4e5', 3.1);
  key.position.set(-3, 8, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, {left: -10, right: 10, top: 10, bottom: -10, near: .1, far: 30});
  key.shadow.normalBias = .025;
  key.shadow.bias = -.0002;
  key.shadow.radius = 4;
  world.add(key);
  const rim = new THREE.DirectionalLight('#c6e6f8', 1.8);
  rim.position.set(5, 3, -6);
  world.add(rim);
  const materials = {
    steel: new THREE.MeshStandardMaterial({color: '#a4b1bc', metalness: .58, roughness: .32}),
    polished: new THREE.MeshStandardMaterial({color: '#c7d3db', metalness: .8, roughness: .22}),
    frame: new THREE.MeshStandardMaterial({color: '#465e6e', metalness: .5, roughness: .43}),
    teal: new THREE.MeshStandardMaterial({color: '#387987', metalness: .35, roughness: .38}),
    black: new THREE.MeshStandardMaterial({color: '#243b4b', roughness: .8}),
    rubber: new THREE.MeshStandardMaterial({color: '#344752', roughness: .93}),
    orange: new THREE.MeshStandardMaterial({color: '#cf9b56', roughness: .78}),
    tape: new THREE.MeshStandardMaterial({color: '#e9d6ad', roughness: .66}),
    ivory: new THREE.MeshStandardMaterial({color: '#e7ebeb', metalness: .15, roughness: .56}),
  };
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.MeshStandardMaterial({color: '#dce6eb', roughness: .95}));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -.018;
  ground.receiveShadow = true;
  world.add(ground);
  const grid = new THREE.GridHelper(36, 72, '#b7c8d1', '#c8d6dd');
  grid.position.y = -.012;
  grid.material.transparent = true;
  grid.material.opacity = .4;
  world.add(grid);
  const deck = new THREE.Group();
  const wires = new THREE.Group();
  world.add(deck, wires);
  const registry = new Map();
  let definition, selection, signalsVisible = true, disposed = false;
  const selectionRing = new THREE.Mesh(new THREE.RingGeometry(.34, .37, 64), new THREE.MeshBasicMaterial({color: '#318c99', side: THREE.DoubleSide, transparent: true, opacity: .8, depthWrite: false}));
  selectionRing.rotation.x = -Math.PI / 2;
  selectionRing.visible = false;
  world.add(selectionRing);

  function box(parent, dimensions, position, material = materials.steel) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...dimensions), material);
    mesh.position.set(...position); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh);
    return mesh;
  }
  function cylinder(parent, radius, length, position, material = materials.steel, axis = 'y') {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, 24), material);
    if (axis === 'z') mesh.rotation.x = Math.PI / 2;
    if (axis === 'x') mesh.rotation.z = Math.PI / 2;
    mesh.position.set(...position); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh);
    return mesh;
  }
  function lampMaterial(color) {
    return new THREE.MeshStandardMaterial({color, emissive: color, emissiveIntensity: .08, roughness: .3, metalness: .1});
  }
  function label(parent, text, y = 1.6) {
    const canvas = document.createElement('canvas');
    canvas.width = 512; canvas.height = 96;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, 512, 96);
    ctx.fillStyle = '#f7fbfbea';
    ctx.beginPath(); ctx.roundRect(32, 9, 448, 72, 12); ctx.fill();
    ctx.font = '600 52px system-ui, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#355b6d';
    ctx.fillText(text.slice(0, 24), 256, 47);
    const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: texture, transparent: true, depthWrite: false, depthTest: false, toneMapped: false}));
    sprite.position.set(0, y, 0); sprite.scale.set(1.35, .253, 1); sprite.userData.label = true; sprite.visible = false; sprite.renderOrder = 5;
    parent.add(sprite);
  }
  function buildDevice(component) {
    const group = new THREE.Group();
    group.position.fromArray(component.position || [0, 0, 0]);
    group.userData.component = component.id;
    deck.add(group);
    const entry = {group, component, activeMaterial: null, moving: null, rollers: []};
    const p = component.parameters || {};
    switch (component.type) {
      case 'conveyor': {
        const length = Math.max(1, Math.min(10, Number(p.length) || 4.4));
        entry.length = length;
        for (const z of [-.58, .58]) {
          box(group, [length + .18, .18, .12], [0, .82, z], materials.steel);
          box(group, [length, .025, .08], [0, .925, z], materials.teal);
          for (const x of [-length * .39, length * .39]) {
            box(group, [.1, .76, .1], [x, .42, z], materials.steel);
            box(group, [.24, .035, .24], [x, .02, z], materials.black);
            cylinder(group, .027, .017, [x, .83, z + Math.sign(z) * .065], materials.frame, 'z');
          }
          box(group, [length * .81, .08, .07], [0, .3, z], materials.steel);
        }
        for (const x of [-length * .39, length * .39]) box(group, [.08, .08, 1.1], [x, .3, 0], materials.steel);
        box(group, [length, .09, 1.05], [0, .78, 0], materials.rubber);
        const count = Math.round(length * 4.6);
        for (let i = 0; i <= count; i++) {
          const roller = cylinder(group, .065, 1.05, [-length / 2 + i * length / count, .885, 0], materials.polished, 'z');
          entry.rollers.push(roller);
        }
        cylinder(group, .12, 1.16, [-length / 2, .84, 0], materials.frame, 'z');
        cylinder(group, .12, 1.16, [length / 2, .84, 0], materials.frame, 'z');
        label(group, component.id, 1.6);
        break;
      }
      case 'motor': {
        const body = cylinder(group, .17, .38, [0, .72, 0], materials.teal, 'z');
        for (let i = 0; i < 7; i++) cylinder(group, .185, .015, [0, .72, -.16 + i * .054], materials.teal, 'z');
        box(group, [.23, .14, .21], [0, .96, 0], materials.teal);
        box(group, [.3, .08, .4], [0, .49, 0], materials.frame);
        cylinder(group, .07, .34, [0, .72, -.3], materials.polished, 'z');
        entry.activeMaterial = lampMaterial('#48aa96');
        cylinder(group, .025, .012, [.13, .96, 0], entry.activeMaterial, 'x');
        entry.body = body;
        label(group, component.id, 1.42);
        break;
      }
      case 'photoeye': {
        box(group, [.055, 1.15, .055], [0, .575, 0], materials.steel);
        box(group, [.21, .03, .2], [0, .02, 0], materials.frame);
        box(group, [.15, .2, .13], [0, 1.13, 0], materials.black);
        entry.activeMaterial = lampMaterial('#dc7660');
        cylinder(group, .046, .02, [0, 1.13, .078], entry.activeMaterial, 'z');
        const beam = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 1.13, .09), new THREE.Vector3(0, 1.13, 1.3)]), new THREE.LineBasicMaterial({color: '#d8765a', transparent: true, opacity: .25}));
        group.add(beam); entry.beam = beam;
        label(group, component.id, 1.62);
        break;
      }
      case 'cylinder': {
        box(group, [.34, .11, .55], [0, .86, 0], materials.frame);
        cylinder(group, .115, .55, [0, 1, 0], materials.steel, 'z');
        for (const z of [-.3, .3]) box(group, [.28, .28, .075], [0, 1, z], materials.teal);
        for (const x of [-.09, .09]) for (const y of [.91, 1.09]) cylinder(group, .013, .65, [x, y, 0], materials.polished, 'z');
        const rod = new THREE.Group(); group.add(rod);
        cylinder(rod, .044, .58, [0, 1, .38], materials.polished, 'z');
        box(rod, [.47, .29, .055], [0, 1, .69], materials.frame);
        entry.moving = rod;
        entry.activeMaterial = lampMaterial('#53acaa');
        box(group, [.035, .03, .055], [.147, 1.04, .2], entry.activeMaterial);
        label(group, component.id, 1.65);
        break;
      }
      case 'lamp': {
        cylinder(group, .11, .06, [0, .05, 0], materials.frame);
        cylinder(group, .022, 1.1, [0, .58, 0], materials.polished);
        cylinder(group, .085, .05, [0, 1.15, 0], materials.frame);
        entry.activeMaterial = lampMaterial('#4ca58c');
        cylinder(group, .075, .19, [0, 1.27, 0], entry.activeMaterial);
        cylinder(group, .083, .03, [0, 1.38, 0], materials.frame);
        label(group, component.id, 1.77);
        break;
      }
      case 'switch': {
        box(group, [.32, .62, .28], [0, .32, 0], materials.steel);
        box(group, [.34, .055, .3], [0, .65, 0], materials.ivory);
        cylinder(group, .063, .025, [0, .69, 0], materials.frame);
        entry.activeMaterial = lampMaterial(/stop/i.test(component.id) ? '#c95e4c' : '#3e9e8c');
        cylinder(group, .048, .037, [0, .72, 0], entry.activeMaterial);
        label(group, component.id, 1.06);
        break;
      }
      case 'workpiece': {
        const parcel = new THREE.Group(); group.add(parcel); entry.moving = parcel;
        box(parcel, [.46, .36, .43], [0, .18, 0], materials.orange);
        box(parcel, [.46, .006, .06], [0, .363, 0], materials.tape);
        box(parcel, [.07, .36, .006], [0, .18, .218], materials.tape);
        box(parcel, [.17, .1, .006], [.12, .23, .22], materials.ivory);
        for (let i = 0; i < 7; i++) box(parcel, [.006 + (i % 2) * .003, .065, .002], [.06 + i * .014, .23, .224], materials.frame);
        label(group, component.id, .72);
        break;
      }
      default:
        box(group, [.4, .4, .4], [0, .2, 0], materials.teal);
        label(group, component.id, .75);
    }
    group.traverse(object => { object.userData.component = component.id; });
    registry.set(component.id, entry);
  }
  function disposeObject(group) {
    group.traverse(object => {
      object.geometry?.dispose();
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        if (!material || Object.values(materials).includes(material)) continue;
        material.map?.dispose(); material.dispose();
      }
    });
    group.removeFromParent();
  }
  function connectDevices(scene) {
    for (const wire of [...wires.children]) disposeObject(wire);
    const pairs = scene.connections || [];
    for (const edge of pairs) {
      const first = registry.get(String(edge.from).split('.')[0]);
      const second = registry.get(String(edge.to).split('.')[0]);
      if (!first || !second) continue;
      const a = first.group.position.clone().add(new THREE.Vector3(0, .03, 0));
      const b = second.group.position.clone().add(new THREE.Vector3(0, .03, 0));
      a.z += .83; b.z += .83;
      const points = [a, new THREE.Vector3(a.x, .03, Math.max(a.z, b.z) + .14), new THREE.Vector3(b.x, .03, Math.max(a.z, b.z) + .14), b];
      wires.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineDashedMaterial({color: '#73a1ae', dashSize: .06, gapSize: .05, transparent: true, opacity: .65})).computeLineDistances());
    }
    wires.visible = signalsVisible;
  }
  function stateValue(state, ...keys) {
    for (const k of keys) if (state?.[k] !== undefined) return state[k];
    return undefined;
  }
  function update(snapshot) {
    for (const component of snapshot?.components || []) {
      const entry = registry.get(component.id);
      if (!entry) continue;
      const state = component.state || {};
      const active = stateValue(state, 'running', 'detected', 'value', 'on', 'extended');
      if (entry.activeMaterial) entry.activeMaterial.emissiveIntensity = active ? 1.8 : .08;
      if (entry.beam) entry.beam.material.opacity = active ? .85 : .2;
      if (component.type === 'cylinder' && entry.moving) entry.moving.position.z = Math.max(0, Math.min(1, Number(state.position) || 0)) * .68;
      if (component.type === 'workpiece' && entry.moving) {
        const wire = definition?.connections?.find(edge => edge.to === `${component.id}.position`);
        const belt = wire ? registry.get(wire.from.split('.')[0]) : [...registry.values()].find(e => e.component.type === 'conveyor');
        const progress = Math.max(0, Math.min(1, Number(state.position) || 0));
        const span = (belt?.length || 4.4) - .6;
        const beltPosition = belt?.group.position || new THREE.Vector3();
        const offset = new THREE.Vector3().fromArray(entry.component.position || [0, 0, 0]);
        const base = new THREE.Vector3(beltPosition.x - span / 2 + progress * span, beltPosition.y + .965, beltPosition.z).add(offset);
        entry.group.position.copy(base);
        if (state.ejected) entry.group.position.z += .8;
      }
      // Rollers use the actual accumulated plant position, never a render timer.
      if (component.type === 'conveyor') for (const roller of entry.rollers) roller.rotation.y = (Number(state.position) || 0) * Math.PI * 14;
    }
    if (selection) select(selection);
    container.dataset.scan = String(snapshot?.scan ?? 0);
  }
  function cameraView(mode = 'home') {
    const d = viewDistance;
    camera.position.copy(focus).add(mode === 'top' ? new THREE.Vector3(0, d * 1.25, .02) : new THREE.Vector3(d * .66, d * .62, d * .83));
    controls.target.copy(focus); controls.update();
  }
  function setScene(scene) {
    definition = scene;
    for (const child of [...deck.children]) disposeObject(child);
    registry.clear();
    for (const component of scene?.components || []) buildDevice(component);
    connectDevices(scene || {});
    const bounds = new THREE.Box3().setFromObject(deck);
    if (!bounds.isEmpty()) {
      bounds.getCenter(focus); focus.y = .75;
      const size = bounds.getSize(new THREE.Vector3());
      viewDistance = Math.max(6.2, Math.min(30, Math.max(size.x, size.z) * 1.12));
    }
    cameraView();
    update({components: (scene?.components || []).map(c => ({...c, state: {position: c.parameters?.initial_position || 0, value: c.parameters?.initial || false}}))});
    select(selection);
  }
  function select(id) {
    selection = registry.has(id) ? id : undefined;
    deck.traverse(object => { if (object.userData.label) object.visible = object.userData.component === selection; });
    const entry = registry.get(selection);
    selectionRing.visible = !!entry;
    if (entry) {
      selectionRing.position.set(entry.group.position.x, .006, entry.group.position.z);
      const radius = entry.component.type === 'conveyor' ? 2.2 : .75;
      selectionRing.scale.set(radius, radius, radius);
    }
  }
  const raycaster = new THREE.Raycaster();
  let pointerStart;
  renderer.domElement.addEventListener('pointerdown', event => { pointerStart = [event.clientX, event.clientY]; });
  renderer.domElement.addEventListener('pointerup', event => {
    if (!pointerStart || Math.hypot(event.clientX - pointerStart[0], event.clientY - pointerStart[1]) > 5) return;
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
    const hit = raycaster.intersectObjects(deck.children, true).find(x => x.object.userData.component && !x.object.userData.label);
    if (hit) onSelect(hit.object.userData.component);
  });
  const resize = new ResizeObserver(() => {
    const width = container.clientWidth, height = container.clientHeight;
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.zoom = Math.min(1, camera.aspect / 1.25);
    camera.updateProjectionMatrix(); renderer.setSize(width, height, false);
  });
  resize.observe(container);
  renderer.setAnimationLoop(() => {
    if (disposed || document.hidden) return;
    controls.update(); renderer.render(world, camera);
  });
  renderer.domElement.addEventListener('webglcontextlost', event => {
    event.preventDefault(); container.dispatchEvent(new Event('scene-lost'));
  });
  cameraView();
  return {
    setScene, update, select, cameraView,
    showSignals(value) { signalsVisible = !!value; wires.visible = signalsVisible; },
    dispose() {
      disposed = true; resize.disconnect(); controls.dispose(); renderer.setAnimationLoop(null);
      for (const child of [...deck.children, ...wires.children]) disposeObject(child);
      ground.geometry.dispose(); ground.material.dispose(); grid.geometry.dispose(); grid.material.dispose();
      selectionRing.geometry.dispose(); selectionRing.material.dispose();
      Object.values(materials).forEach(m => m.dispose()); renderer.dispose(); renderer.domElement.remove();
    },
  };
}
