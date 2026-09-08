import * as THREE from './vendor/three.module.min.js';

// The scene decorates the ordinary HTML controls; it never owns family records.
let disposeCurrent = () => {};
function mount(host, children = []) {
  disposeCurrent();
  if (!host) return;
  let renderer;
  try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'low-power'}); }
  catch { host.classList.add('world-static'); return; }
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(35, 1, .1, 100);
  camera.position.set(0, 5.8, 12.8); camera.lookAt(0, .1, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.4;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  host.append(renderer.domElement); host.classList.add('world-ready');
  const ambient = new THREE.HemisphereLight(0xbdeaff, 0x2b175d, 2.8); scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xffe6ae, 4); sun.position.set(-4, 8, 5); scene.add(sun);
  const rim = new THREE.DirectionalLight(0x5fffe0, 3); rim.position.set(3, 1, -4); scene.add(rim);
  const world = new THREE.Group(); scene.add(world);
  const mat = (color, opts = {}) => new THREE.MeshStandardMaterial({color, roughness: .55, metalness: .14, ...opts});
  function mesh(geo, material, parent, pos = [0, 0, 0]) {
    const object = new THREE.Mesh(geo, material); object.position.set(...pos); parent.add(object); return object;
  }
  function ring(radius, color, parent, pos, tilt = Math.PI / 2) {
    const o = mesh(new THREE.TorusGeometry(radius, .017, 6, 96), mat(color, {emissive: color, emissiveIntensity: .45}), parent, pos);
    o.rotation.x = tilt; return o;
  }
  const floating = [], sprouts = [], accents = [0x83f0cb, 0xb59aff, 0xffc77a];
  const members = children.length ? children.slice(0, 4) : [{energy: 0, level: 0}, {energy: 0, level: 0}];
  members.forEach((child, i) => {
    const root = new THREE.Group(); world.add(root);
    const x = members.length === 1 ? 0 : (i - (members.length - 1) / 2) * 3.85;
    root.position.set(x, i % 2 ? -.12 : .05, i % 2 ? -.35 : .2);
    floating.push({root, y: root.position.y, phase: i * 2});
    const color = accents[i % accents.length];
    const earth = mat(i % 2 ? 0x514a83 : 0x286b69), grass = mat(i % 2 ? 0x9180ca : 0x63bea9);
    mesh(new THREE.CylinderGeometry(1.47, 1.35, .34, 7), grass, root, [0, 0, 0]);
    const rock = mesh(new THREE.ConeGeometry(1.37, 1.8, 7), earth, root, [0, -.97, 0]); rock.rotation.z = Math.PI;
    const mineral = mat(color, {emissive: color, emissiveIntensity: .25, roughness: .2});
    for (let j = 0; j < 5; j++) {
      const a = j * 1.25 + .3;
      const crystal = mesh(new THREE.OctahedronGeometry(.09 + j * .012), mineral, root, [Math.cos(a) * 1.16, -.45 - j * .1, Math.sin(a) * 1.02]);
      crystal.scale.y = 2;
    }
    ring(1.85, color, root, [0, -.8, 0]);
    const stage = mesh(new THREE.CylinderGeometry(.57, .65, .11, 32), mat(0xd7e8e8), root, [0, .23, 0]);
    const pedestal = mesh(new THREE.CylinderGeometry(.22, .28, .38, 12), mat(0x1c3e57), root, [0, .46, 0]);
    ring(.24, color, root, [0, .66, 0]);
    const sprout = new THREE.Group(); root.add(sprout); sprout.position.y = .69;
    const height = .24 + Math.min(Number(child.level) || 0, 6) * .09;
    mesh(new THREE.CylinderGeometry(.032, .042, height, 7), mat(0xb7e8bc), sprout, [0, height / 2, 0]);
    for (const side of [-1, 1]) {
      const leaf = mesh(new THREE.SphereGeometry(.19, 12, 8), mat(color, {emissive: color, emissiveIntensity: .12}), sprout, [side * .13, height * .83, 0]);
      leaf.scale.set(1.3, .32, .63); leaf.rotation.z = side * .5;
    }
    sprouts.push(sprout);
    // Permanent landscape is decoration; the central sprout reflects recorded energy.
    const trunk = mat(0x344859), crown = mat(i % 2 ? 0xc0a9eb : 0xa0e6c4);
    for (const [tx, tz, size] of [[-.85, .2, .65], [.75, -.35, .85], [-.3, -.85, .45]]) {
      mesh(new THREE.CylinderGeometry(.06, .08, size, 6), trunk, root, [tx, .17 + size / 2, tz]);
      mesh(new THREE.ConeGeometry(size * .36, size * .7, 5), crown, root, [tx, .35 + size, tz]);
      mesh(new THREE.ConeGeometry(size * .28, size * .55, 5), crown, root, [tx, .55 + size, tz]);
    }
    // A small observatory and its orbiting light make each island recognisable.
    mesh(new THREE.CylinderGeometry(.23, .23, .35, 10), mat(0xe4e8ea), root, [.63, .37, .65]);
    mesh(new THREE.SphereGeometry(.245, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), mat(color), root, [.63, .545, .65]);
    const scope = mesh(new THREE.CylinderGeometry(.055, .08, .4, 10), mat(0xf3d6a8), root, [.63, .72, .66]);
    scope.rotation.z = -.75;
    const orbit = ring(.56, 0xffd99b, root, [0, 1.45, 0], .3); orbit.rotation.y = .3;
    const moon = mesh(new THREE.IcosahedronGeometry(.09, 1), mat(0xffe2a3, {emissive: 0xffc681, emissiveIntensity: .8}), root, [.57, 1.45, 0]);
    sprouts.push(orbit); floating.push({root: moon, y: moon.position.y, phase: i + 1});
    stage.rotation.y = pedestal.rotation.y = i;
  });
  if (members.length > 1) {
    const path = new THREE.CatmullRomCurve3([new THREE.Vector3(-1.6, .16, .15),new THREE.Vector3(0, -.15, .8),new THREE.Vector3(1.6, .16, -.15)]);
    mesh(new THREE.TubeGeometry(path, 32, .017, 5, false), mat(0xf7d191, {emissive: 0xf7d191, emissiveIntensity: .5}), world);
    for (let i = 0; i < 9; i++) {
      const p = path.getPoint(i / 8); p.y -= .035;
      mesh(new THREE.BoxGeometry(.12, .06, .22), mat(0xb7b9c9), world, p.toArray());
    }
  }
  let seed = 17;
  const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  const vertices = [];
  for (let i = 0; i < 110; i++) vertices.push((rand() - .5) * 20, (rand() - .25) * 8, -3 - rand() * 6);
  const stars = new THREE.BufferGeometry(); stars.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  scene.add(new THREE.Points(stars, new THREE.PointsMaterial({color: 0xa4cdeb, size: .035, transparent: true, opacity: .7})));
  const satellite = new THREE.Group(); scene.add(satellite); satellite.position.set(4.3, 2.6, -3);
  mesh(new THREE.SphereGeometry(.28, 20, 12), mat(0xddb787), satellite);
  const satRing = ring(.48, 0xc8a6f8, satellite, [0, 0, 0], .85); satRing.rotation.y = -.5;
  let frame = 0, stopped = false, visible = true, targetX = 0, targetY = 0, last = 0;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduce.matches;
  try { paused ||= localStorage.getItem('family-world-motion') === 'off'; } catch {}
  const button = document.querySelector('[data-world-motion]');
  const labelButton = () => { if (button) { button.textContent = paused ? '开启动效' : '暂停动效'; button.setAttribute('aria-pressed', String(!paused)); } };
  const draw = () => renderer.render(scene, camera);
  function tick(time) {
    frame = 0;
    if (stopped || document.hidden || !visible || paused) return;
    if (time - last >= 33) {
      last = time; const t = time * .001;
      for (const item of floating) item.root.position.y = item.y + Math.sin(t * .6 + item.phase) * .045;
      for (const item of sprouts) item.rotation.y = Math.sin(t * .25) * .15;
      world.rotation.y += (targetX - world.rotation.y) * .045;
      world.rotation.x += (targetY - world.rotation.x) * .045;
      draw();
    }
    frame = requestAnimationFrame(tick);
  }
  const resume = () => { if (!stopped && !paused && !frame && visible && !document.hidden) frame = requestAnimationFrame(tick); };
  const resize = () => {
    if (stopped || !host.clientWidth || !host.clientHeight) return;
    camera.aspect = host.clientWidth / host.clientHeight;
    camera.position.z = camera.aspect < 1.15 ? 18 : 12.8; camera.position.y = camera.aspect < 1.15 ? 7.3 : 5.8;
    world.scale.setScalar(camera.aspect < 1.15 ? 1.05 : 1.5);
    camera.lookAt(0, .1, 0); camera.updateProjectionMatrix();
    renderer.setSize(host.clientWidth, host.clientHeight, false); draw();
  };
  const move = e => { if (e.pointerType !== 'mouse') return; const b = host.getBoundingClientRect(); targetX = ((e.clientX - b.left) / b.width - .5) * .26; targetY = ((e.clientY - b.top) / b.height - .5) * .045; };
  const leave = () => { targetX = targetY = 0; };
  const toggle = () => { paused = !paused; try { localStorage.setItem('family-world-motion', paused ? 'off' : 'on'); } catch {} labelButton(); draw(); resume(); };
  const reduced = () => { if (reduce.matches) { paused = true; labelButton(); draw(); } else resume(); };
  const resized = new ResizeObserver(resize); resized.observe(host);
  const observed = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? true; resume(); }); observed.observe(host);
  host.addEventListener('pointermove', move); host.addEventListener('pointerleave', leave);
  document.addEventListener('visibilitychange', resume); reduce.addEventListener('change', reduced); button?.addEventListener('click', toggle);
  labelButton(); resize(); resume();
  disposeCurrent = () => {
    stopped = true; cancelAnimationFrame(frame); resized.disconnect(); observed.disconnect();
    host.removeEventListener('pointermove', move); host.removeEventListener('pointerleave', leave);
    document.removeEventListener('visibilitychange', resume); reduce.removeEventListener('change', reduced); button?.removeEventListener('click', toggle);
    scene.traverse(object => { object.geometry?.dispose(); if (Array.isArray(object.material)) object.material.forEach(m => m.dispose()); else object.material?.dispose(); });
    renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
  };
}
window.FamilyWorld = {mount, destroy: () => disposeCurrent()};
window.dispatchEvent(new Event('family-world-ready'));
