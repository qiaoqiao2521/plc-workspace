import * as THREE from 'three';
import {OrbitControls} from './vendor/three/OrbitControls.js';

// Presentation only: no PLC calls or plant integration in the render loop.
export function createConveyorView(container) {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const renderer = new THREE.WebGLRenderer({antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.domElement.setAttribute('aria-label','可旋转的三维输送设备');
  container.append(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#e7edf0');
  scene.fog = new THREE.Fog('#e7edf0',16,42);
  const camera = new THREE.PerspectiveCamera(38,1,.1,80);
  const controls = new OrbitControls(camera,renderer.domElement);
  controls.enableDamping = !reducedMotion;
  controls.enablePan = false;
  controls.minDistance = 5; controls.maxDistance = 18;
  controls.maxPolarAngle = Math.PI * .48;
  controls.target.set(0,1,0);
  function cameraView(top = false) {
    camera.position.set(...(top ? [0,11,.1] : [6.2,4.6,6.8]));
    controls.target.set(0,1,0); controls.update();
  }
  cameraView();
  const ambient = new THREE.HemisphereLight('#ffffff','#9aa8b8',2.5); scene.add(ambient);
  const key = new THREE.DirectionalLight('#ffffff',3.4); key.position.set(-3,9,5);
  key.castShadow = true; key.shadow.mapSize.set(2048,2048);
  Object.assign(key.shadow.camera,{left:-8,right:8,top:8,bottom:-8,near:.1,far:25});
  key.shadow.bias = -.0003; key.shadow.normalBias = .04; scene.add(key);
  const fill = new THREE.DirectionalLight('#c0d9f0',1.7);fill.position.set(5,4,-5);scene.add(fill);
  const steel = new THREE.MeshStandardMaterial({color:'#a6b2bd',metalness:.65,roughness:.36});
  const dark = new THREE.MeshStandardMaterial({color:'#33475b',metalness:.5,roughness:.38});
  const blue = new THREE.MeshStandardMaterial({color:'#386d98',metalness:.45,roughness:.3});
  const rubber = new THREE.MeshStandardMaterial({color:'#253749',roughness:.85});
  const orange = new THREE.MeshStandardMaterial({color:'#cc873c',roughness:.72});
  const tape = new THREE.MeshStandardMaterial({color:'#f1d6a0',roughness:.65});
  const model = new THREE.Group(); scene.add(model);
  function box(w,h,d,x,y,z,material,parent=model) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material);
    m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;
  }
  function cylinder(radius,length,x,y,z,material,parent=model) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,length,32),material);
    m.rotation.x=Math.PI/2;m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;
  }
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(120,120),new THREE.MeshStandardMaterial({color:'#e0e6e9',roughness:1}));
  ground.rotation.x=-Math.PI/2;ground.receiveShadow=true;scene.add(ground);
  const grid = new THREE.GridHelper(28,28,'#bac7cd','#ced8dd');grid.position.y=.002;scene.add(grid);
  // Frame, feet and cross braces.
  for (const z of [-.76,.76]) {
    box(6.6,.23,.14,0,1.48,z,steel);
    box(6.3,.035,.09,0,1.62,z,blue);
    for (const x of [-2.65,2.65]) {
      box(.15,1.38,.15,x,.74,z,steel);
      box(.3,.06,.3,x,.045,z,dark);
      cylinder(.035,.012,x,1.47,z+Math.sign(z)*.08,dark);
    }
    box(5.35,.12,.09,0,.43,z,steel);
  }
  for (const x of [-2.65,2.65]) box(.12,.12,1.55,x,.43,0,steel);
  box(6.1,.18,1.36,0,1.4,0,rubber);
  const rollers=[];
  for(let i=0;i<23;i++) {
    const x=-3+i*6/22;
    const roller=cylinder(.095,1.32,x,1.535,0,steel);
    box(.018,1.3,.008,0,0,.095,dark,roller);rollers.push(roller);
  }
  cylinder(.2,1.54,-3.12,1.47,0,dark);cylinder(.2,1.54,3.12,1.47,0,dark);
  const motor=cylinder(.23,.55,-2.65,1.22,1.08,blue);
  for(let i=0;i<7;i++) cylinder(.245,.025,-2.65,1.22,.85+i*.07,blue);
  box(.4,.2,.35,-2.65,1.54,1.08,blue);
  box(.3,.2,.15,-2.65,1.25,.74,dark);
  // Physical beam and sensor bracket, with live feedback highlight.
  box(.08,1.02,.08,2.55,1.8,-.9,steel);
  box(.17,.23,.16,2.55,2.22,-.9,dark);
  const lensMaterial=new THREE.MeshStandardMaterial({color:'#5ca4cc',emissive:'#286c98',emissiveIntensity:.25});
  const lens=cylinder(.055,.025,2.55,2.22,-.8,lensMaterial);
  const beam=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(2.55,2.2,-.8),new THREE.Vector3(2.55,1.75,.6)]),new THREE.LineBasicMaterial({color:'#3da7c3',transparent:true,opacity:.3}));model.add(beam);
  box(.38,.95,.3,-3.9,.52,-.75,steel);
  box(.055,.3,.25,-3.68,.81,-.75,dark);
  const lights=[];
  for(const [index,color] of ['#d86551','#dfb33d','#43a17e'].entries()) {
    const material=new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:.06,roughness:.35});
    const light=new THREE.Mesh(new THREE.CylinderGeometry(.095,.095,.11,24),material);
    light.position.set(-3.9,2.16-index*.13,-.75);model.add(light);lights.push(material);
  }
  box(.045,.89,.045,-3.9,1.44,-.75,steel);
  const parcel=new THREE.Group();model.add(parcel);
  box(.73,.59,.67,0,.3,0,orange,parcel);
  box(.73,.012,.085,0,.601,0,tape,parcel);
  box(.085,.6,.012,0,.3,.34,tape,parcel);
  box(.26,.15,.012,.17,.38,.346,new THREE.MeshStandardMaterial({color:'#f6f1e7'}),parcel);
  const arrow=new THREE.ArrowHelper(new THREE.Vector3(1,0,0),new THREE.Vector3(-1.3,.02,1.8),2.6,'#628397',.22,.14);scene.add(arrow);
  function label(text, position) {
    const canvas=document.createElement('canvas');canvas.width=512;canvas.height=96;
    const context=canvas.getContext('2d');context.font='500 36px "Noto Sans CJK SC", sans-serif';context.textAlign='center';
    context.fillStyle='#3c5768';context.fillText(text,256,60);
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
    const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false}));
    sprite.position.set(...position);sprite.scale.set(2.1,.4,1);scene.add(sprite);
  }
  label('上料位置',[-2.65,.15,1.65]);label('到位 AtEnd',[2.6,2.65,-.8]);
  let target=0, position=0, playback=false, output={};
  parcel.position.set(-2.7,1.65,0);
  const observer=new ResizeObserver(()=>{
    const w=container.clientWidth,h=container.clientHeight;
    if(!w||!h)return;camera.aspect=w/h;camera.zoom=Math.min(1,camera.aspect/1.5);camera.updateProjectionMatrix();renderer.setSize(w,h,false);
  });observer.observe(container);
  let previous=performance.now();
  renderer.setAnimationLoop(now=>{
    const dt=Math.min((now-previous)/1000,.1);previous=now;
    position = reducedMotion ? target : THREE.MathUtils.damp(position,target,14,dt);
    parcel.position.x=-2.7+position*5.4;
    // Roller animation is visual only and never updates parcel position or PLC state.
    if(playback&&output.Motor&&!reducedMotion)for(const roller of rollers)roller.rotation.y+=dt*2;
    controls.update();renderer.render(scene,camera);
  });
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();container.dispatchEvent(new Event('scene-lost'));});
  return {
    update(result) {
      target=result.position;output=result.outputs;
      const on=result.inputs.AtEnd;
      lensMaterial.emissiveIntensity=on?2.3:.25;beam.material.opacity=on ? .9 : .25;
      lights.forEach((material,i)=>material.emissiveIntensity=[output.Error,output.Busy,output.Done][i]?1.8:.06);
      motor.material.color.set(output.Motor?'#367baf':'#386d98');
      container.dataset.position=String(target);container.dataset.motor=String(output.Motor);container.dataset.error=String(output.Error);
    },
    reset(){position=target=0;output={};motor.material.color.set('#386d98');parcel.position.x=-2.7;lights.forEach(m=>m.emissiveIntensity=.06);lensMaterial.emissiveIntensity=.25;beam.material.opacity=.25;container.dataset.position='0';container.dataset.motor='0';container.dataset.error='0';},
    setPlayback(value){playback=value;},
    cameraView,
    dispose(){observer.disconnect();controls.dispose();renderer.setAnimationLoop(null);scene.traverse(o=>{o.geometry?.dispose();const materials=Array.isArray(o.material)?o.material:[o.material];for(const m of materials)if(m){m.map?.dispose();m.dispose();}});renderer.dispose();renderer.domElement.remove();}
  };
}
