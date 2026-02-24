/* Nova Web Dashboard — avatar.js
   Three.js GPU particle system with GLSL shaders for Nova's visual form.
   ~20,000 particles, 80+ palettes, 35+ abstract forms, 15 real-world morph forms,
   floor grid, two-point perspective, hue shifting, turbulence — Nova controls it all. */

const NovaAvatar = (function () {
  "use strict";

  let scene, camera, renderer, particles, glowMeshes = [], floorGrid;
  let clock, uniforms;
  let canvas, animId;
  const COUNT = 20000;
  const ORB_COUNT = 999;
  const ORB_TEX_WIDTH = 1024;

  // Per-orb state
  let orbDataTexture;
  let orbPositions = new Float32Array(ORB_COUNT * 3);
  let orbTargetPositions = new Float32Array(ORB_COUNT * 3);
  let orbColors = new Float32Array(ORB_COUNT * 3);
  let orbSizes = new Float32Array(ORB_COUNT).fill(1.0);
  let orbBrightness = new Float32Array(ORB_COUNT).fill(1.0);
  let currentOrbMode = 0, targetOrbMode = 0;

  // ── Environment particle system ──────────────────────────────────────────
  const ENV_COUNT = 5000;
  let envParticles;
  let envUniforms;

  const ENV_TYPES = {
    off: 0, stars: 1, rain: 2, snow: 3, fireflies: 4,
    embers: 5, dust: 6, bubbles: 7, sparks: 8, leaves: 9, energy: 10
  };

  let currentEnv = {
    envType: 0, envDensity: 0.5, envSpeed: 0.5,
    envColorR: 1, envColorG: 1, envColorB: 1,
    envIntensity: 0.5, envScale: 1.0,
  };
  let targetEnv = { ...currentEnv };

  // ── Color palettes ─────────────────────────────────────────────────────────
  const PALETTES = {
    // Core
    ember:   { pri: [0.83, 0.63, 0.15], sec: [0.91, 0.77, 0.28], acc: [0.28, 0.78, 0.78] },
    nova:    { pri: [0.83, 0.63, 0.15], sec: [0.91, 0.77, 0.28], acc: [0.28, 0.78, 0.78] },
    aurora:  { pri: [0.15, 0.75, 0.45], sec: [0.28, 0.82, 0.78], acc: [0.55, 0.30, 0.80] },
    ocean:   { pri: [0.10, 0.35, 0.70], sec: [0.18, 0.62, 0.65], acc: [0.45, 0.85, 0.75] },
    void:    { pri: [0.25, 0.12, 0.50], sec: [0.15, 0.10, 0.35], acc: [0.85, 0.85, 0.95] },
    bloom:   { pri: [0.82, 0.35, 0.55], sec: [0.90, 0.50, 0.65], acc: [0.95, 0.80, 0.40] },
    storm:   { pri: [0.70, 0.72, 0.78], sec: [0.85, 0.87, 0.92], acc: [0.30, 0.55, 0.95] },
    sunset:  { pri: [0.88, 0.35, 0.18], sec: [0.92, 0.55, 0.25], acc: [0.80, 0.25, 0.50] },
    forest:  { pri: [0.18, 0.55, 0.22], sec: [0.35, 0.65, 0.20], acc: [0.80, 0.72, 0.30] },
    ice:     { pri: [0.65, 0.82, 0.95], sec: [0.80, 0.90, 0.98], acc: [0.95, 0.98, 1.00] },
    // Art history
    monet:         { pri: [0.55, 0.70, 0.50], sec: [0.72, 0.65, 0.82], acc: [0.85, 0.72, 0.78] },
    rothko:        { pri: [0.65, 0.12, 0.10], sec: [0.50, 0.08, 0.15], acc: [0.82, 0.40, 0.12] },
    klimt:         { pri: [0.85, 0.72, 0.15], sec: [0.18, 0.50, 0.25], acc: [0.72, 0.15, 0.15] },
    hokusai:       { pri: [0.12, 0.18, 0.55], sec: [0.20, 0.35, 0.70], acc: [0.92, 0.95, 0.98] },
    vangogh:       { pri: [0.20, 0.30, 0.65], sec: [0.85, 0.75, 0.20], acc: [0.15, 0.55, 0.35] },
    caravaggio:    { pri: [0.12, 0.08, 0.05], sec: [0.75, 0.55, 0.30], acc: [0.90, 0.78, 0.55] },
    mondrian:      { pri: [0.90, 0.15, 0.15], sec: [0.15, 0.15, 0.75], acc: [0.95, 0.85, 0.15] },
    mucha:         { pri: [0.75, 0.60, 0.45], sec: [0.55, 0.70, 0.50], acc: [0.85, 0.65, 0.55] },
    kandinsky:     { pri: [0.85, 0.30, 0.20], sec: [0.20, 0.35, 0.70], acc: [0.90, 0.80, 0.15] },
    vermeer:       { pri: [0.15, 0.25, 0.55], sec: [0.85, 0.78, 0.45], acc: [0.65, 0.55, 0.40] },
    okeefe:        { pri: [0.90, 0.45, 0.40], sec: [0.95, 0.85, 0.70], acc: [0.35, 0.55, 0.45] },
    basquiat:      { pri: [0.90, 0.20, 0.15], sec: [0.15, 0.15, 0.80], acc: [0.95, 0.90, 0.20] },
    pollock:       { pri: [0.15, 0.15, 0.15], sec: [0.85, 0.82, 0.75], acc: [0.70, 0.30, 0.20] },
    warhol:        { pri: [0.95, 0.20, 0.50], sec: [0.20, 0.90, 0.85], acc: [0.95, 0.90, 0.15] },
    rembrandt:     { pri: [0.18, 0.12, 0.08], sec: [0.65, 0.48, 0.25], acc: [0.88, 0.75, 0.50] },
    picasso_blue:  { pri: [0.10, 0.15, 0.45], sec: [0.20, 0.30, 0.55], acc: [0.50, 0.55, 0.70] },
    frida:         { pri: [0.85, 0.20, 0.25], sec: [0.20, 0.60, 0.30], acc: [0.90, 0.75, 0.15] },
    turner:        { pri: [0.90, 0.80, 0.55], sec: [0.85, 0.60, 0.35], acc: [0.70, 0.75, 0.85] },
    // Science & cosmos
    nebula:        { pri: [0.45, 0.15, 0.55], sec: [0.75, 0.25, 0.50], acc: [0.90, 0.85, 0.95] },
    supernova:     { pri: [0.95, 0.90, 0.80], sec: [0.90, 0.50, 0.15], acc: [0.30, 0.20, 0.70] },
    deep_sea:      { pri: [0.02, 0.05, 0.18], sec: [0.05, 0.15, 0.30], acc: [0.20, 0.85, 0.70] },
    bioluminescence: { pri: [0.02, 0.08, 0.20], sec: [0.10, 0.60, 0.50], acc: [0.30, 0.95, 0.85] },
    solar_flare:   { pri: [0.95, 0.60, 0.10], sec: [0.90, 0.30, 0.08], acc: [0.98, 0.92, 0.70] },
    northern_lights: { pri: [0.15, 0.80, 0.40], sec: [0.30, 0.50, 0.80], acc: [0.70, 0.25, 0.65] },
    quantum:       { pri: [0.10, 0.10, 0.25], sec: [0.30, 0.70, 0.90], acc: [0.90, 0.30, 0.60] },
    dna:           { pri: [0.20, 0.55, 0.80], sec: [0.80, 0.35, 0.50], acc: [0.92, 0.90, 0.85] },
    electromagnetic: { pri: [0.85, 0.20, 0.20], sec: [0.20, 0.20, 0.85], acc: [0.90, 0.90, 0.90] },
    black_hole:    { pri: [0.02, 0.02, 0.05], sec: [0.15, 0.08, 0.30], acc: [0.90, 0.50, 0.10] },
    prism:         { pri: [0.90, 0.20, 0.20], sec: [0.20, 0.85, 0.30], acc: [0.30, 0.30, 0.90] },
    cosmic_dust:   { pri: [0.45, 0.35, 0.30], sec: [0.60, 0.50, 0.45], acc: [0.75, 0.70, 0.65] },
    plasma:        { pri: [0.60, 0.10, 0.80], sec: [0.90, 0.30, 0.60], acc: [0.40, 0.80, 0.95] },
    // Nature
    sakura:        { pri: [0.92, 0.70, 0.75], sec: [0.98, 0.85, 0.88], acc: [0.55, 0.72, 0.50] },
    coral_reef:    { pri: [0.90, 0.45, 0.35], sec: [0.20, 0.75, 0.70], acc: [0.92, 0.82, 0.40] },
    volcanic:      { pri: [0.70, 0.15, 0.05], sec: [0.92, 0.50, 0.10], acc: [0.10, 0.08, 0.08] },
    rainforest:    { pri: [0.08, 0.40, 0.15], sec: [0.15, 0.55, 0.20], acc: [0.75, 0.68, 0.25] },
    desert:        { pri: [0.85, 0.70, 0.50], sec: [0.72, 0.45, 0.30], acc: [0.55, 0.75, 0.88] },
    tundra:        { pri: [0.75, 0.78, 0.80], sec: [0.60, 0.65, 0.70], acc: [0.40, 0.55, 0.50] },
    wildfire:      { pri: [0.92, 0.40, 0.08], sec: [0.80, 0.20, 0.05], acc: [0.98, 0.80, 0.20] },
    tidepools:     { pri: [0.25, 0.50, 0.55], sec: [0.50, 0.70, 0.45], acc: [0.82, 0.55, 0.40] },
    midnight:      { pri: [0.05, 0.05, 0.15], sec: [0.10, 0.10, 0.25], acc: [0.80, 0.80, 0.90] },
    autumn:        { pri: [0.85, 0.45, 0.12], sec: [0.75, 0.25, 0.10], acc: [0.60, 0.55, 0.15] },
    moss:          { pri: [0.25, 0.40, 0.15], sec: [0.35, 0.50, 0.22], acc: [0.55, 0.65, 0.35] },
    lightning:     { pri: [0.90, 0.90, 0.95], sec: [0.50, 0.55, 0.85], acc: [0.95, 0.95, 1.00] },
    lavender:      { pri: [0.60, 0.50, 0.75], sec: [0.75, 0.65, 0.85], acc: [0.88, 0.82, 0.92] },
    amber:         { pri: [0.90, 0.65, 0.10], sec: [0.80, 0.50, 0.08], acc: [0.95, 0.80, 0.30] },
    pearl:         { pri: [0.90, 0.88, 0.85], sec: [0.85, 0.83, 0.82], acc: [0.92, 0.90, 0.88] },
    obsidian:      { pri: [0.08, 0.08, 0.10], sec: [0.15, 0.14, 0.18], acc: [0.30, 0.28, 0.35] },
    // World cultures
    kintsugi:      { pri: [0.20, 0.18, 0.15], sec: [0.35, 0.30, 0.25], acc: [0.85, 0.72, 0.15] },
    rangoli:       { pri: [0.90, 0.45, 0.10], sec: [0.85, 0.15, 0.45], acc: [0.20, 0.75, 0.65] },
    aboriginal:    { pri: [0.65, 0.25, 0.10], sec: [0.80, 0.60, 0.20], acc: [0.92, 0.88, 0.75] },
    stained_glass: { pri: [0.70, 0.12, 0.18], sec: [0.12, 0.20, 0.70], acc: [0.15, 0.65, 0.25] },
    moroccan:      { pri: [0.15, 0.45, 0.65], sec: [0.85, 0.55, 0.20], acc: [0.75, 0.18, 0.22] },
    zen:           { pri: [0.35, 0.33, 0.30], sec: [0.50, 0.48, 0.45], acc: [0.65, 0.63, 0.58] },
    ukiyo_e:       { pri: [0.55, 0.20, 0.25], sec: [0.20, 0.40, 0.55], acc: [0.90, 0.82, 0.60] },
    byzantine:     { pri: [0.55, 0.15, 0.50], sec: [0.75, 0.60, 0.15], acc: [0.15, 0.35, 0.55] },
    mayan:         { pri: [0.20, 0.55, 0.45], sec: [0.75, 0.35, 0.15], acc: [0.85, 0.78, 0.35] },
    celtic:        { pri: [0.15, 0.40, 0.25], sec: [0.55, 0.50, 0.30], acc: [0.80, 0.75, 0.60] },
    batik:         { pri: [0.30, 0.15, 0.50], sec: [0.70, 0.45, 0.15], acc: [0.15, 0.55, 0.45] },
    sumi_e:        { pri: [0.10, 0.10, 0.10], sec: [0.30, 0.28, 0.25], acc: [0.70, 0.68, 0.62] },
    henna:         { pri: [0.55, 0.20, 0.08], sec: [0.72, 0.35, 0.12], acc: [0.90, 0.75, 0.45] },
    persian:       { pri: [0.15, 0.30, 0.60], sec: [0.70, 0.25, 0.25], acc: [0.85, 0.72, 0.25] },
    aztec:         { pri: [0.75, 0.20, 0.15], sec: [0.25, 0.60, 0.50], acc: [0.90, 0.82, 0.25] },
    nordic:        { pri: [0.25, 0.35, 0.50], sec: [0.55, 0.58, 0.62], acc: [0.80, 0.78, 0.72] },
    silk_road:     { pri: [0.80, 0.55, 0.20], sec: [0.55, 0.15, 0.40], acc: [0.20, 0.55, 0.60] },
  };

  // ── Abstract form presets ────────────────────────────────────────────────
  const F0 = { spread: 0, stretch: 0, ring: 0, spiral: 0, flatten: 0, split: 0 };
  const FORMS = {
    sphere:        { ...F0 },
    ring:          { ...F0, ring: 1.0, spread: 0.1 },
    cloud:         { ...F0, spread: 0.8, stretch: 0.2 },
    spiral:        { ...F0, spread: 0.2, stretch: 0.3, ring: 0.3, spiral: 1.0 },
    stream:        { ...F0, stretch: 0.9, spread: 0.1, spiral: 0.2 },
    scatter:       { ...F0, spread: 1.0, stretch: 0.3 },
    helix:         { ...F0, stretch: 0.7, ring: 0.4, spiral: 0.9, spread: 0.15 },
    wave:          { ...F0, spread: 0.5, ring: 0.3, spiral: 0.4, flatten: 0.4 },
    constellation: { ...F0, spread: 0.95, stretch: 0.2 },
    vortex:        { ...F0, ring: 0.7, spiral: 0.8, spread: 0.3 },
    filament:      { ...F0, stretch: 1.0, spiral: 0.5, spread: 0.05 },
    bloom:         { ...F0, spread: 0.6, ring: 0.2, spiral: 0.3 },
    nebula:        { ...F0, spread: 0.7, stretch: 0.4, spiral: 0.2 },
    flame:         { ...F0, stretch: 0.7, spread: 0.15, spiral: 0.1 },
    rain:          { ...F0, stretch: 1.0, spread: 0.5 },
    fountain:      { ...F0, stretch: 0.6, spread: 0.4, spiral: 0.3 },
    tornado:       { ...F0, stretch: 0.8, ring: 0.4, spiral: 0.9, spread: 0.3 },
    tree:          { ...F0, stretch: 0.6, spread: 0.5, split: 0.3, spiral: 0.2 },
    coral:         { ...F0, spread: 0.5, split: 0.4, spiral: 0.15 },
    roots:         { ...F0, stretch: 0.8, spread: 0.3, split: 0.5, spiral: 0.3 },
    disk:          { ...F0, flatten: 1.0, ring: 0.5, spread: 0.3 },
    halo:          { ...F0, ring: 1.0, flatten: 0.8 },
    wings:         { ...F0, split: 0.9, flatten: 0.3, spread: 0.3, stretch: 0.2 },
    cocoon:        { ...F0, stretch: 0.3, spread: -0.1 },
    explosion:     { ...F0, spread: 1.0 },
    implosion:     { ...F0, spread: -0.2 },
    lattice:       { ...F0, spread: 0.5, flatten: 0.5, split: 0.5 },
    galaxy:        { ...F0, ring: 0.6, spiral: 0.7, flatten: 0.7, spread: 0.4 },
    orbit:         { ...F0, ring: 0.8, spiral: 0.6, spread: 0.2 },
    pulsar:        { ...F0, stretch: 0.5, flatten: 0.6, spiral: 0.3 },
    accretion:     { ...F0, ring: 0.9, flatten: 0.9, spread: 0.2, spiral: 0.4 },
    heartbeat:     { ...F0 },
    breath:        { ...F0, spread: 0.1 },
    swarm:         { ...F0, spread: 0.6, spiral: 0.4, split: 0.2 },
    flock:         { ...F0, spread: 0.7, flatten: 0.4, spiral: 0.3 },
    jellyfish:     { ...F0, stretch: 0.4, spread: 0.3, flatten: 0.2, ring: 0.2 },
    amoeba:        { ...F0, spread: 0.3, spiral: 0.1 },
  };

  // ── Real-world morph system ──────────────────────────────────────────────
  let morphBuffer = null;
  let currentMorph = 0, targetMorph = 0;
  let _morphState = "idle";
  let _pendingMorphGen = null;
  let _morphHoldTimer = 0;     // seconds the form has been stable
  const MORPH_HOLD_MIN = 3.0;  // minimum seconds to hold a form before allowing change

  // Scatter / constellation transition state
  let currentScatter = 0, targetScatter = 0;
  let currentColorSep = 0, targetColorSep = 0;
  let _constellationTimer = 0;

  // Body-parts helper: distribute particles across ellipsoid body parts
  // Each part: [cx, cy, cz, rx, ry, rz, weight]
  function _bp(parts, n) {
    const tw = parts.reduce(function(s,p){return s+p[6];}, 0);
    var o = new Float32Array(n * 3), idx = 0;
    for (var pi = 0; pi < parts.length; pi++) {
      var p = parts[pi];
      var c = Math.round(n * p[6] / tw);
      for (var j = 0; j < c && idx < n; j++, idx++) {
        var t = Math.random() * 6.2832, ph = Math.acos(2*Math.random()-1);
        var r = Math.pow(Math.random(), 0.4);
        o[idx*3]   = p[0] + p[3]*r*Math.sin(ph)*Math.cos(t);
        o[idx*3+1] = p[1] + p[4]*r*Math.sin(ph)*Math.sin(t);
        o[idx*3+2] = p[2] + p[5]*r*Math.cos(ph);
      }
    }
    while (idx < n) {
      var s = Math.floor(Math.random()*idx);
      o[idx*3]=o[s*3]; o[idx*3+1]=o[s*3+1]; o[idx*3+2]=o[s*3+2]; idx++;
    }
    return o;
  }

  // Real-world morph form generators
  var MORPH_GENS = {
    heart: function(n) {
      var o = new Float32Array(n*3);
      for (var i=0; i<n; i++) {
        var t=Math.random()*6.2832, r=0.7+Math.random()*0.3;
        o[i*3]   = 16*Math.pow(Math.sin(t),3)*0.065*r;
        o[i*3+1] = (13*Math.cos(t)-5*Math.cos(2*t)-2*Math.cos(3*t)-Math.cos(4*t))*0.065*r;
        o[i*3+2] = (Math.random()-0.5)*0.35;
      }
      return o;
    },
    human: function(n) { return _bp([
      [0,1.4,0,.18,.2,.18,.08],[0,1.15,0,.08,.1,.08,.02],[0,.75,0,.28,.42,.16,.26],
      [-.42,.9,0,.08,.08,.08,.03],[.42,.9,0,.08,.08,.08,.03],
      [-.5,.7,0,.07,.22,.07,.06],[.5,.7,0,.07,.22,.07,.06],
      [-.52,.4,0,.06,.2,.06,.04],[.52,.4,0,.06,.2,.06,.04],
      [0,.22,0,.24,.1,.12,.04],
      [-.14,-.15,0,.1,.35,.1,.13],[.14,-.15,0,.1,.35,.1,.13],
      [-.14,-.58,0,.07,.22,.07,.06],[.14,-.58,0,.07,.22,.07,.06],
    ], n); },
    bird: function(n) { return _bp([
      // Perching bird — compact body, visible beak, folded wings, tail
      [0,0,0,.16,.24,.13,.16],              // Body — round, upright
      [0,.3,0,.09,.09,.08,.05],             // Head — small, round
      [0,.3,.14,.03,.02,.08,.02],           // Beak — pointed forward
      [0,.18,.06,.1,.04,.08,.03],           // Throat/chest
      [-.14,.06,-.02,.08,.18,.06,.06],      // Left folded wing
      [.14,.06,-.02,.08,.18,.06,.06],       // Right folded wing
      [-.2,-.04,-.04,.04,.1,.03,.02],       // Left wing tip
      [.2,-.04,-.04,.04,.1,.03,.02],        // Right wing tip
      [0,-.2,-.1,.04,.12,.03,.04],          // Tail — fanned down
      [-.04,-.32,0,.025,.06,.02,.01],       // Left leg
      [.04,-.32,0,.025,.06,.02,.01],        // Right leg
      [-.04,-.38,0,.03,.01,.03,.005],       // Left foot
      [.04,-.38,0,.03,.01,.03,.005],        // Right foot
    ], n); },
    toucan: function(n) { return _bp([
      // Toucan — oversized curved beak is the defining feature
      [0,0,0,.14,.22,.12,.14],              // Body — compact, pear-shaped, upright
      [0,.26,0,.08,.08,.07,.05],            // Head — small, round
      [0,.16,.04,.1,.06,.08,.04],           // Throat/chest — white patch area
      // Beak — massive, curved, nearly body-length
      [0,.28,.16,.04,.04,.06,.03],          // Beak base (thick)
      [0,.26,.28,.035,.035,.05,.03],        // Beak mid section
      [0,.22,.38,.03,.03,.04,.025],         // Beak outer section
      [0,.18,.44,.02,.025,.03,.015],        // Beak tip (curves down)
      // Wings — folded against body
      [-.12,.04,-.02,.07,.16,.06,.05],      // Left wing
      [.12,.04,-.02,.07,.16,.06,.05],       // Right wing
      // Tail — short, squared
      [0,-.16,-.08,.05,.08,.04,.03],        // Tail
      // Legs/feet — gripping branch
      [-.035,-.28,0,.02,.06,.02,.008],      // Left leg
      [.035,-.28,0,.02,.06,.02,.008],       // Right leg
      [-.035,-.34,.02,.025,.01,.03,.005],   // Left foot
      [.035,-.34,.02,.025,.01,.03,.005],    // Right foot
    ], n); },
    butterfly: function(n) {
      var o = new Float32Array(n*3), idx = 0, bodyN = Math.floor(n*0.08);
      for (var i=0; i<bodyN && idx<n; i++, idx++) {
        o[idx*3]=(Math.random()-.5)*.06; o[idx*3+1]=(Math.random()-.5)*.7; o[idx*3+2]=(Math.random()-.5)*.04;
      }
      for (; idx<n; idx++) {
        var t=Math.random()*6.2832, side=Math.random()<.5?-1:1;
        var r=Math.exp(Math.sin(t))-2*Math.cos(4*t)+Math.pow(Math.sin((2*t-3.14159)/24),5);
        var sc=0.3*(0.7+Math.random()*0.3);
        o[idx*3]=Math.abs(Math.cos(t)*r)*sc*side; o[idx*3+1]=Math.sin(t)*r*sc; o[idx*3+2]=(Math.random()-.5)*.08;
      }
      return o;
    },
    cat: function(n) { return _bp([
      [0,.9,0,.2,.2,.18,.1],[-.13,1.12,0,.04,.1,.03,.02],[.13,1.12,0,.04,.1,.03,.02],
      [0,.35,0,.25,.42,.2,.34],
      [-.14,-.15,.1,.09,.12,.08,.05],[.14,-.15,.1,.09,.12,.08,.05],
      [-.14,-.15,-.1,.09,.12,.08,.05],[.14,-.15,-.1,.09,.12,.08,.05],
      [.28,.5,0,.06,.38,.05,.1],[.36,.8,0,.05,.1,.04,.06],
      [0,.9,.14,.03,.03,.05,.03],
    ], n); },
    dolphin: function(n) { return _bp([
      [0,.15,0,.15,.22,.48,.34],[0,.2,.52,.08,.1,.12,.08],[0,.22,.66,.04,.05,.06,.04],
      [0,.08,-.42,.08,.08,.24,.12],[0,.12,-.7,.2,.03,.1,.1],
      [0,.36,-.04,.02,.14,.08,.06],
      [-.17,.08,.1,.13,.03,.08,.06],[.17,.08,.1,.13,.03,.08,.06],
    ], n); },
    rose: function(n) {
      var o = new Float32Array(n*3), idx = 0;
      var cN = Math.floor(n*0.1);
      for (var i=0; i<cN && idx<n; i++, idx++) {
        var a=Math.random()*6.2832, r=Math.random()*0.15;
        o[idx*3]=Math.cos(a)*r; o[idx*3+1]=Math.random()*0.1; o[idx*3+2]=Math.sin(a)*r;
      }
      for (var layer=0; layer<3; layer++) {
        var pN=Math.floor(n*0.27), rBase=0.3+layer*0.3, yOff=-layer*0.12;
        for (var j=0; j<pN && idx<n; j++, idx++) {
          var petal=Math.floor(Math.random()*5), pa=petal*1.2566+layer*0.4;
          var spread=Math.random()*0.4, ang=pa+(Math.random()-.5)*0.6, rad=rBase*(0.5+spread);
          o[idx*3]=Math.cos(ang)*rad; o[idx*3+1]=yOff-spread*0.25; o[idx*3+2]=Math.sin(ang)*rad;
        }
      }
      for (; idx<n; idx++) {
        o[idx*3]=(Math.random()-.5)*0.04; o[idx*3+1]=-(Math.random()*0.7+0.4); o[idx*3+2]=(Math.random()-.5)*0.04;
      }
      return o;
    },
    starform: function(n) {
      var o = new Float32Array(n*3);
      for (var i=0; i<n; i++) {
        var a=Math.random()*6.2832, arm=Math.floor(a/(6.2832/5));
        var armA=arm*6.2832/5, off=a-armA-6.2832/10;
        var r=0.4+0.8*Math.exp(-Math.abs(off)*3)*(0.7+Math.random()*0.3);
        o[i*3]=Math.cos(armA+off*0.3)*r; o[i*3+1]=Math.sin(armA+off*0.3)*r; o[i*3+2]=(Math.random()-.5)*0.15;
      }
      return o;
    },
    crescent: function(n) {
      var o = new Float32Array(n*3);
      for (var i=0; i<n; i++) {
        var a = -1.8+Math.random()*3.6;
        var rOuter=0.8+Math.random()*0.2, rInner=0.5+Math.random()*0.15;
        var r=rInner+Math.random()*(rOuter-rInner);
        o[i*3]=Math.cos(a)*r; o[i*3+1]=Math.sin(a)*r; o[i*3+2]=(Math.random()-.5)*0.15;
      }
      return o;
    },
    skull: function(n) { return _bp([
      [0,.5,0,.35,.38,.3,.34],[0,-.02,0,.26,.18,.2,.14],
      [-.15,.55,.25,.08,.08,.05,.05],[.15,.55,.25,.08,.08,.05,.05],
      [0,.35,.26,.05,.12,.03,.04],
      [-.18,.15,.18,.05,.05,.04,.03],[.18,.15,.18,.05,.05,.04,.03],
      [0,-.28,0,.22,.08,.18,.08],
      [0,-.15,.2,.06,.04,.04,.03],
      [0,-.4,.12,.04,.03,.03,.02],
    ], n); },
    hand: function(n) { return _bp([
      [0,-.15,0,.28,.32,.07,.24],
      [-.24,.35,0,.045,.32,.035,.1],[-.1,.38,0,.04,.38,.035,.12],
      [.05,.4,0,.04,.4,.035,.12],[.2,.36,0,.04,.36,.035,.12],
      [.34,.12,0,.04,.18,.035,.06],[0,.06,0,.2,.07,.05,.07],
    ], n); },
    dragon: function(n) {
      // Winged dragon — bat-like wings dominate the silhouette (ref photo 3),
      // reptilian head with frills/horns (ref photo 2), serpentine body (ref photo 1)
      var o = _bp([
        // === HEAD (reptilian, wedge-shaped) ===
        [0,1.12,.16,.12,.1,.13,.035],       // Cranium
        [0,1.06,.32,.06,.05,.12,.015],       // Snout/muzzle
        [0,1.02,.26,.05,.03,.1,.01],         // Lower jaw
        [-.06,1.16,.22,.04,.02,.06,.004],    // Brow ridges
        [.06,1.16,.22,.04,.02,.06,.004],
        [-.09,1.12,.22,.03,.03,.03,.003],    // Eye sockets
        [.09,1.12,.22,.03,.03,.03,.003],
        [-.05,1.28,.08,.02,.08,.02,.004],    // Horns — swept back
        [.05,1.28,.08,.02,.08,.02,.004],
        [-.1,1.06,.16,.03,.02,.06,.003],     // Jaw frills
        [.1,1.06,.16,.03,.02,.06,.003],

        // === NECK (thick S-curve) ===
        [0,.96,.08,.08,.07,.08,.025],
        [0,.84,.0,.09,.08,.09,.025],
        [0,.72,-.06,.1,.09,.1,.03],
        [0,.58,-.08,.1,.1,.1,.035],

        // === TORSO ===
        [0,.38,-.1,.16,.18,.2,.08],          // Main body
        [0,.24,-.02,.14,.12,.14,.04],        // Chest/belly

        // === LEGS ===
        [-.12,.04,-.14,.11,.14,.11,.03],     // Haunches
        [.12,.04,-.14,.11,.14,.11,.03],
        [-.14,.12,.1,.05,.14,.05,.015],      // Front legs
        [.14,.12,.1,.05,.14,.05,.015],
        [-.14,-.04,.17,.04,.03,.05,.005],    // Front claws
        [.14,-.04,.17,.04,.03,.05,.005],
        [-.14,-.1,-.1,.04,.03,.05,.005],     // Rear claws
        [.14,-.1,-.1,.04,.03,.05,.005],

        // === TAIL (6 segments, curling) ===
        [0,.16,-.32,.07,.07,.12,.02],
        [0,.1,-.46,.06,.06,.1,.015],
        [.07,.08,-.58,.05,.05,.08,.012],
        [.13,.1,-.68,.04,.04,.07,.008],
        [.17,.15,-.74,.03,.04,.05,.006],
        [.19,.22,-.76,.02,.03,.03,.004],

        // === WINGS — dominant feature, bat-like (ref photo 3) ===
        // Wing arm bones — from shoulders outward and up
        [-.18,.56,-.06,.1,.03,.05,.015],     // L upper arm
        [.18,.56,-.06,.1,.03,.05,.015],      // R upper arm
        [-.36,.64,-.04,.12,.025,.04,.012],   // L forearm
        [.36,.64,-.04,.12,.025,.04,.012],    // R forearm

        // Wing finger bones — thin struts radiating outward
        [-.54,.74,-.01,.14,.015,.02,.008],   // L outer finger
        [.54,.74,-.01,.14,.015,.02,.008],    // R outer finger
        [-.50,.60,-.04,.13,.015,.02,.006],   // L mid finger
        [.50,.60,-.04,.13,.015,.02,.006],    // R mid finger
        [-.42,.48,-.06,.11,.015,.02,.005],   // L inner finger
        [.42,.48,-.06,.11,.015,.02,.005],    // R inner finger

        // Wing membrane — large flat panels filling between bones
        // Inner membrane (near body, thickest)
        [-.28,.52,-.06,.16,.012,.1,.05],     // L inner membrane
        [.28,.52,-.06,.16,.012,.1,.05],      // R inner membrane
        // Mid membrane (main wing area, largest)
        [-.46,.62,-.03,.2,.01,.12,.07],      // L mid membrane
        [.46,.62,-.03,.2,.01,.12,.07],       // R mid membrane
        // Outer membrane (thinner, tapers to wing tip)
        [-.64,.70,-.01,.14,.008,.08,.035],   // L outer membrane
        [.64,.70,-.01,.14,.008,.08,.035],    // R outer membrane
        // Trailing edge — thin strip along bottom of wing
        [-.38,.44,-.08,.18,.006,.06,.02],    // L trailing edge
        [.38,.44,-.08,.18,.006,.06,.02],     // R trailing edge
      ], Math.floor(n * 0.84));

      // Spines along neck and back
      var idx = Math.floor(n * 0.84);
      var spinePoints = [
        [0,1.22,.1, .12],[0,1.08,.02, .1],[0,.96,-.04, .09],[0,.84,-.08, .08],
        [0,.72,-.12, .08],[0,.6,-.14, .07],
        [0,.48,-.16, .06],[0,.38,-.16, .05],[0,.28,-.16, .04],
        [0,.18,-.24, .03],[0,.12,-.36, .025],[0,.1,-.48, .02]
      ];
      for (var si = 0; si < spinePoints.length && idx < n; si++) {
        var sp = spinePoints[si];
        var spikeH = sp[3];
        var spikeN = Math.floor(n * 0.013);
        for (var j = 0; j < spikeN && idx < n; j++, idx++) {
          var h = Math.random() * spikeH + 0.01;
          var spread = 0.015;
          o[idx*3]   = sp[0] + (Math.random() - 0.5) * spread;
          o[idx*3+1] = sp[1] + h;
          o[idx*3+2] = sp[2] + (Math.random() - 0.5) * spread;
        }
      }
      while (idx < n) {
        var s = Math.floor(Math.random() * idx);
        o[idx*3]=o[s*3]; o[idx*3+1]=o[s*3+1]; o[idx*3+2]=o[s*3+2]; idx++;
      }
      return o;
    },
    horse: function(n) { return _bp([
      [0,.7,.32,.07,.14,.07,.05],[0,.78,.28,.06,.06,.05,.03],[0,.82,.35,.03,.03,.06,.01],
      [0,.55,.18,.06,.12,.06,.04],[0,.35,0,.2,.24,.32,.24],
      [-.12,-.08,.18,.06,.32,.06,.08],[.12,-.08,.18,.06,.32,.06,.08],
      [-.12,-.08,-.18,.06,.32,.06,.08],[.12,-.08,-.18,.06,.32,.06,.08],
      [0,.18,-.38,.07,.05,.1,.05],[0,.12,-.52,.04,.04,.08,.03],
      [0,.88,.32,.03,.07,.02,.02],
    ], n); },
    whale: function(n) { return _bp([
      [0,0,0,.28,.32,.65,.44],[0,.04,.6,.14,.18,.14,.08],[0,-.04,.76,.07,.09,.07,.04],
      [0,-.04,-.55,.07,.07,.18,.08],[0,0,-.8,.22,.03,.09,.08],
      [-.18,-.08,-.08,.14,.03,.09,.05],[.18,-.08,-.08,.14,.03,.09,.05],
      [0,.22,0,.03,.1,.07,.04],
    ], n); },
    phoenix: function(n) { return _bp([
      [0,.1,0,.14,.24,.11,.14],[0,.38,0,.07,.07,.06,.04],[0,.42,.07,.03,.03,.05,.02],
      [-.58,.14,0,.48,.035,.24,.19],[.58,.14,0,.48,.035,.24,.19],
      [0,-.08,0,.07,.09,.28,.09],
      [0,-.22,-.28,.14,.035,.22,.09],[0,-.32,-.5,.18,.03,.18,.07],
      [0,-.38,-.7,.12,.02,.12,.05],
    ], n); },
  };

  function _setMorphTargets(positions) {
    if (!morphBuffer) return;
    morphBuffer.set(positions);
    if (particles) particles.geometry.attributes.aMorphTarget.needsUpdate = true;
  }

  function _setOrbTargets(positions) {
    orbTargetPositions.set(positions);
  }

  function _applyOrbColors() {
    const pri = [currentVisual.priR, currentVisual.priG, currentVisual.priB];
    const sec = [currentVisual.secR, currentVisual.secG, currentVisual.secB];
    const acc = [currentVisual.accR, currentVisual.accG, currentVisual.accB];
    for (let i = 0; i < ORB_COUNT; i++) {
      const group = i % 3;
      const c = group === 0 ? pri : group === 1 ? sec : acc;
      orbColors[i * 3] = c[0];
      orbColors[i * 3 + 1] = c[1];
      orbColors[i * 3 + 2] = c[2];
    }
  }

  function computeOrbLighting() {
    for (let i = 0; i < ORB_COUNT; i++) {
      let light = 0.0;
      const ix = orbPositions[i * 3], iy = orbPositions[i * 3 + 1], iz = orbPositions[i * 3 + 2];
      for (let j = 0; j < ORB_COUNT; j++) {
        if (i === j) continue;
        const dx = orbPositions[j * 3] - ix;
        const dy = orbPositions[j * 3 + 1] - iy;
        const dz = orbPositions[j * 3 + 2] - iz;
        const d2 = dx * dx + dy * dy + dz * dz;
        light += 1.0 / (1.0 + d2 * 20.0);
      }
      orbBrightness[i] = 0.3 + Math.min(light * 0.12, 1.2);
    }
  }

  function _updateOrbTexture() {
    if (!orbDataTexture) return;
    const data = orbDataTexture.image.data;
    for (let i = 0; i < ORB_COUNT; i++) {
      // Row 0: position + size
      const idx0 = i * 4;
      data[idx0] = orbPositions[i * 3];
      data[idx0 + 1] = orbPositions[i * 3 + 1];
      data[idx0 + 2] = orbPositions[i * 3 + 2];
      data[idx0 + 3] = orbSizes[i];
      // Row 1: color + brightness
      const idx1 = (ORB_TEX_WIDTH + i) * 4;
      data[idx1] = orbColors[i * 3];
      data[idx1 + 1] = orbColors[i * 3 + 1];
      data[idx1 + 2] = orbColors[i * 3 + 2];
      data[idx1 + 3] = orbBrightness[i];
    }
    orbDataTexture.needsUpdate = true;
  }

  // ── Tone presets ─────────────────────────────────────────────────────────
  const TONE_PRESETS = {
    neutral:    { breath: 0.30, speed: 0.50, expansion: 1.00, glow: 0.50 },
    excited:    { breath: 0.80, speed: 1.50, expansion: 1.30, glow: 1.00 },
    cheerful:   { breath: 0.60, speed: 1.00, expansion: 1.15, glow: 0.80 },
    empathetic: { breath: 0.35, speed: 0.40, expansion: 0.90, glow: 0.45 },
    sad:        { breath: 0.20, speed: 0.20, expansion: 0.75, glow: 0.30 },
    curious:    { breath: 0.50, speed: 0.80, expansion: 1.10, glow: 0.70 },
    loud:       { breath: 0.90, speed: 1.40, expansion: 1.40, glow: 1.20 },
    soft:       { breath: 0.20, speed: 0.30, expansion: 0.85, glow: 0.35 },
    whisper:    { breath: 0.15, speed: 0.15, expansion: 0.70, glow: 0.20 },
    serious:    { breath: 0.25, speed: 0.35, expansion: 0.95, glow: 0.40 },
    thoughtful: { breath: 0.35, speed: 0.60, expansion: 1.00, glow: 0.55 },
    caps_emphasis: { breath: 0.85, speed: 1.40, expansion: 1.35, glow: 1.10 },
  };

  // ── Current & target state ───────────────────────────────────────────────
  let currentTone = { breath: 0.3, speed: 0.5, expansion: 1.0, glow: 0.5 };
  let targetTone  = { breath: 0.3, speed: 0.5, expansion: 1.0, glow: 0.5 };

  let currentVisual = {
    priR: 0.83, priG: 0.63, priB: 0.15,
    secR: 0.91, secG: 0.77, secB: 0.28,
    accR: 0.28, accG: 0.78, accB: 0.78,
    spread: 0, stretch: 0, ring: 0, spiral: 0, flatten: 0, split: 0,
    chaos: 0, shimmer: 0, density: 0.5, sizeMul: 1.0, pulse: 0.3,
    turbulence: 0, gravity: 0, ripple: 0, flow: 0,
    hueShift: 0, saturation: 1.0,
    orbEnergy: 0.3,
    orbSpread: 0,
    orbSize: 1.0,
    orbSizeVar: 0,
    viscosity: 0.5,
    posX: 0, posY: 0, posZ: 0,
    fogDensity: 0, fogColorR: 0, fogColorG: 0, fogColorB: 0,
    mood: 0.5, ambientR: 0.12, ambientG: 0.12, ambientB: 0.2,
  };
  let targetVisual = { ...currentVisual };

  const LERP_SPEED = 2.0;
  const VIS_LERP_SPEED = 1.5;
  const MORPH_LERP_SPEED = 0.7;

  // ── Simplex noise GLSL ───────────────────────────────────────────────────
  const NOISE_GLSL = `
    vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
    float snoise(vec3 v){
      const vec2 C=vec2(1.0/6.0,1.0/3.0);const vec4 D=vec4(0.0,0.5,1.0,2.0);
      vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
      vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.0-g;
      vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);
      vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;
      i=mod289(i);
      vec4 p=permute(permute(permute(
        i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
      float n_=0.142857142857;vec3 ns=n_*D.wyz-D.xzx;
      vec4 j=p-49.0*floor(p*ns.z*ns.z);
      vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.0*x_);
      vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.0-abs(x)-abs(y);
      vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);
      vec4 s0=floor(b0)*2.0+1.0;vec4 s1=floor(b1)*2.0+1.0;vec4 sh=-step(h,vec4(0.0));
      vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
      vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);
      vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
      vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
      p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
      vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);m=m*m;
      return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
    }`;

  // ── Vertex shader ────────────────────────────────────────────────────────
  const vertexShader = `
    ${NOISE_GLSL}
    uniform float uTime, uBreath, uSpeed, uExpansion, uAudioLevel;
    uniform float uSpread, uStretch, uRing, uSpiral, uFlatten, uSplit;
    uniform float uChaos, uShimmer, uDensity, uSizeMul, uPulse;
    uniform float uTurbulence, uGravity, uRipple, uFlow;
    uniform float uMorph;
    uniform float uScatter;
    uniform sampler2D uOrbData;
    uniform float uOrbMode;
    uniform float uOrbEnergy;
    uniform float uOrbSpread;
    uniform float uOrbSize;
    uniform float uViscosity;

    attribute float aRandom, aSize, aTheta, aPhi;
    attribute vec3 aMorphTarget;
    attribute float aOrbIndex;
    varying float vDepth, vRandom, vShimmer, vCenterDist, vScatter;
    varying vec3 vOrbColor;
    varying float vOrbBrightness;

    void main(){
      float t = uTime * uSpeed;
      vec3 pos = position;

      // ── Form morphing ──
      vec3 rp = pos;
      rp.y *= (1.0 - uRing * 0.7);
      float rd = length(rp.xz);
      float rr = 1.0 + 0.2 * sin(aTheta * 3.0);
      rp.xz *= mix(1.0, rr / max(rd, 0.01), uRing * 0.5);
      pos = mix(pos, rp, uRing);

      pos.y *= (1.0 - uFlatten * 0.85);

      float splitPush = uSplit * 0.6 * sign(pos.x + 0.001);
      pos.x += splitPush;

      pos.y *= (1.0 + uStretch * 1.5);

      vec3 sd = normalize(pos + vec3(aRandom * 0.1));
      pos += sd * uSpread * aRandom * 1.2;

      float sa = uSpiral * (aRandom * 6.28 + t * 0.8);
      float sc = cos(sa * 0.3), ss = sin(sa * 0.3);
      pos.xz = mat2(sc, -ss, ss, sc) * pos.xz;
      pos.y += uSpiral * sin(aRandom * 12.0 + t * 0.5) * 0.3;

      // ── Noise displacement ──
      float ns = 1.5 + uChaos * 2.0 + uTurbulence * 3.0;
      float n1 = snoise(pos * ns + t * 0.3) * (0.3 + uChaos * 0.5);
      float n2 = snoise(pos * 3.0 + t * 0.5) * 0.15;
      float n3 = uTurbulence * snoise(pos * 6.0 + t * 0.7) * 0.2;
      float n4 = uTurbulence * snoise(pos * 12.0 + t * 0.9) * 0.1;
      float noiseD = n1 + n2 + n3 + n4;

      float distFromCenter = length(pos);
      noiseD += uRipple * 0.3 * sin(distFromCenter * 8.0 - t * 3.0);
      noiseD *= (0.3 + uViscosity * 1.4);

      float bAmt = mix(uBreath, uPulse, 0.5);
      float bCycle = sin(t * 1.2 + aRandom * 6.28) * bAmt * 0.3;
      bCycle *= (0.2 + uViscosity * 1.6);

      float dAmt = 1.0 + uChaos * 3.0;
      vec3 drift = vec3(
        sin(t * 0.7 + aRandom * 12.0) * 0.08,
        cos(t * 0.5 + aRandom * 8.0) * 0.06,
        sin(t * 0.9 + aRandom * 10.0) * 0.07
      ) * uSpeed * dAmt;

      drift += vec3(uFlow * 0.3, 0.0, 0.0);
      drift.y -= uGravity * 0.15;
      drift *= (0.2 + uViscosity * 1.6);

      float aP = uAudioLevel * 0.5 * sin(t * 8.0 + aRandom * 6.28);

      vec3 nm = normalize(pos);
      float totalD = noiseD + bCycle + aP;
      float denScale = mix(1.3, 0.8, uDensity);
      vec3 displaced = pos * uExpansion * denScale + nm * totalD + drift;

      // ── Morph toward real-world shape ──
      float morphT = clamp(uMorph * 1.5 - aRandom * 0.5, 0.0, 1.0);
      morphT = smoothstep(0.0, 1.0, morphT);

      // When morphed, particles settle toward their target positions
      // but stay organic — gentle noise drift keeps shapes alive and fluid.
      vec3 mTarget = aMorphTarget * uExpansion;
      float aliveBreath = bCycle * mix(0.25, 0.06, morphT);
      mTarget += normalize(aMorphTarget + vec3(0.001)) * aliveBreath;

      // Organic wobble — each particle drifts gently around its morph target
      // so forms feel like living sculptures, not rigid frozen shapes
      vec3 wobbleSeed = vec3(aRandom * 73.0, aTheta * 41.0, aPhi * 23.0);
      vec3 organicDrift = vec3(
        snoise(wobbleSeed + t * 0.3) * 0.025,
        snoise(wobbleSeed + vec3(11.0) + t * 0.25) * 0.025,
        snoise(wobbleSeed + vec3(29.0) + t * 0.35) * 0.025
      ) * morphT * (0.1 + uViscosity * 1.8);
      mTarget += organicDrift;

      // Blend toward morph target — form emerges but stays fluid
      displaced = mix(displaced, mTarget, morphT);

      // ── Scatter displacement — particles fly outward into constellation ──
      if (uScatter > 0.0) {
        // Each particle gets a unique noise-based scatter direction
        vec3 scatterSeed = vec3(aRandom * 137.0, aTheta * 59.0, aPhi * 97.0);
        vec3 scatterDir = normalize(vec3(
          snoise(scatterSeed),
          snoise(scatterSeed + vec3(31.0)),
          snoise(scatterSeed + vec3(67.0))
        ));
        // Fly outward up to 3x radius
        float scatterDist = (1.5 + aRandom * 1.5) * 3.0 * uScatter;
        // Gentle orbital drift during constellation pause
        float driftAngle = t * 0.15 + aRandom * 6.28;
        vec3 drift2 = vec3(
          sin(driftAngle + aTheta) * 0.08,
          cos(driftAngle * 0.7 + aPhi) * 0.06,
          sin(driftAngle * 1.3) * 0.07
        ) * uScatter;
        displaced += scatterDir * scatterDist + drift2;
      }

      // ── Orb mode ──
      float orbU = (aOrbIndex + 0.5) / 1024.0;
      vec4 orbPosSize = texture2D(uOrbData, vec2(orbU, 0.25));
      vec4 orbColBright = texture2D(uOrbData, vec2(orbU, 0.75));
      vec3 orbCenter = orbPosSize.xyz;
      float orbSz = orbPosSize.w * uOrbSize;

      // Per-orb independent animation — each orb drifts, pulses, orbits on its own
      float orbPhase = aOrbIndex * 0.37;
      float energy = uOrbEnergy;

      // Noise-driven drift — each orb wanders on a unique path
      vec3 orbSeed = vec3(orbPhase * 1.7, orbPhase * 2.3, orbPhase * 3.1);
      vec3 orbDrift = vec3(
        snoise(orbSeed + t * 0.2) * 0.08,
        snoise(orbSeed + vec3(17.0) + t * 0.18) * 0.08,
        snoise(orbSeed + vec3(31.0) + t * 0.22) * 0.08
      ) * energy;

      // Orbital motion — orbs slowly circle their home position
      float orbitSpeed = 0.4 + orbPhase * 0.1;
      float orbitRadius = 0.03 * energy;
      orbDrift.x += sin(t * orbitSpeed + orbPhase * 6.28) * orbitRadius;
      orbDrift.z += cos(t * orbitSpeed + orbPhase * 6.28) * orbitRadius;

      // Per-orb breathing — size pulses independently
      float orbPulse = 1.0 + sin(t * 1.5 + orbPhase * 4.3) * 0.25 * energy;
      orbSz *= orbPulse;

      orbCenter += orbDrift;

      // Orb spread — push orbs apart from the centroid
      orbCenter *= (1.0 + uOrbSpread * 2.0);

      // Particle offset within its orb cluster
      vec3 orbLocal = normalize(position) * aRandom * orbSz * 0.06;
      vec3 orbDisplaced = orbCenter * uExpansion + orbLocal;
      displaced = mix(displaced, orbDisplaced, uOrbMode);
      vOrbColor = orbColBright.rgb;
      vOrbBrightness = orbColBright.a;

      vec4 mvPos = modelViewMatrix * vec4(displaced, 1.0);
      gl_Position = projectionMatrix * mvPos;

      float audioSize = 1.0 + uAudioLevel * 2.0;
      float scatterSizeBoost = 1.0 + uScatter * 2.5;
      gl_PointSize = aSize * uSizeMul * audioSize * scatterSizeBoost * (200.0 / -mvPos.z);

      vDepth = -mvPos.z;
      vRandom = aRandom;
      vScatter = uScatter;
      vShimmer = uShimmer * (0.5 + 0.5 * sin(t * 12.0 + aRandom * 50.0));
      vCenterDist = length(displaced);
    }`;

  // ── Fragment shader (improved color rendering) ───────────────────────────
  const fragmentShader = `
    uniform float uGlow, uTime, uHueShift, uSaturation;
    uniform float uColorSeparation;
    uniform float uOrbMode;
    uniform float uFogDensity, uSceneMood;
    uniform vec3 uFogColor, uAmbientColor;
    uniform vec3 uColorPri, uColorSec, uColorAcc;
    varying float vDepth, vRandom, vShimmer, vCenterDist, vScatter;
    varying vec3 vOrbColor;
    varying float vOrbBrightness;

    vec3 hueRotate(vec3 c, float angle){
      float a = angle * 3.14159265 / 180.0;
      float s = sin(a), co = cos(a);
      vec3 k = vec3(0.57735);
      return c * co + cross(k, c) * s + k * dot(k, c) * (1.0 - co);
    }

    vec3 adjustSat(vec3 c, float sat){
      float grey = dot(c, vec3(0.2126, 0.7152, 0.0722));
      return mix(vec3(grey), c, sat);
    }

    void main(){
      vec2 center = gl_PointCoord - 0.5;
      float dist = length(center);
      if(dist > 0.5) discard;

      // Tighter particle edges during scatter — crisp points of light
      float edgeInner = mix(0.2, 0.05, vScatter);
      float alpha = smoothstep(0.5, edgeInner, dist);

      // Color blend — tri-color separation during scatter
      // Particles split into 3 groups by aRandom value
      float b1 = vRandom;
      float b2 = clamp(vRandom * 2.0 - 0.5 + sin(uTime * 0.4 + vRandom * 6.28) * 0.15, 0.0, 1.0);
      vec3 warm = mix(uColorPri, uColorSec, b1);
      vec3 blended = mix(warm, uColorAcc, b2 * 0.55);

      // During scatter: each particle locks onto one palette color
      vec3 separated;
      if (vRandom < 0.333) {
        separated = uColorPri;
      } else if (vRandom < 0.666) {
        separated = uColorSec;
      } else {
        separated = uColorAcc;
      }
      vec3 color = mix(blended, separated, uColorSeparation);

      // Orb mode: use per-orb color
      color = mix(color, vOrbColor, uOrbMode);

      if(uHueShift != 0.0) color = hueRotate(color, uHueShift);

      // Push saturation hard — color is king, not brightness
      color = adjustSat(color, uSaturation * 1.4);

      // ── Chiaroscuro ──
      float surfaceLight = smoothstep(0.0, 0.9, vCenterDist);
      float shadow = mix(0.15, 1.0, surfaceLight);
      // Reduce shadow effect during scatter — all particles self-illuminate
      shadow = mix(shadow, 1.0, vScatter * 0.8);
      // Each orb self-illuminates — no shadow darkening in orb mode
      shadow = mix(shadow, 1.0, uOrbMode * 0.7);
      color *= shadow;
      // Apply inter-orb brightness
      color *= mix(1.0, vOrbBrightness, uOrbMode);

      // Subtle rim-light on surface particles for form definition
      float rimBoost = smoothstep(0.5, 1.2, vCenterDist) * uGlow * 0.25;
      color += color * rimBoost;

      // Self-illumination — starlight glow during scatter
      color += color * vScatter * 0.4;

      // Gentle shimmer — modulates color, not brightness
      color *= (1.0 + vShimmer * 0.15);

      // Depth fade
      float depthFade = smoothstep(10.0, 2.0, vDepth);

      // Alpha: increases from ~0.07 to ~0.35 during scatter
      alpha *= depthFade;
      float baseAlpha = 0.07 + uGlow * 0.04;
      float scatterAlpha = mix(baseAlpha, 0.35, vScatter);
      alpha *= scatterAlpha;

      // Fog
      float fogFactor = 1.0 - exp(-uFogDensity * vDepth * 0.3);
      color = mix(color, uFogColor, fogFactor * uSceneMood);

      gl_FragColor = vec4(color, alpha);
    }`;

  // ── Floor grid shader ────────────────────────────────────────────────────
  const floorVS = `
    varying vec2 vUv;
    void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
  const floorFS = `
    varying vec2 vUv;
    uniform vec3 uFloorColor;
    uniform vec3 uAmbientColor;
    uniform float uSceneMood;
    void main(){
      vec2 g = abs(fract(vUv * 12.0 - 0.5) - 0.5);
      float line = min(g.x, g.y);
      float a = 1.0 - smoothstep(0.0, 0.04, line);
      float fade = 1.0 - smoothstep(0.25, 0.5, length(vUv - 0.5));
      vec3 gridColor = mix(uFloorColor, uAmbientColor, 0.3);
      float moodAlpha = a * fade * 0.18 * (0.5 + uSceneMood * 0.5);
      gl_FragColor = vec4(gridColor, moodAlpha);
    }`;

  // ── Environment particle shaders ────────────────────────────────────────
  const envVertexShader = `
    uniform float uTime, uEnvType, uEnvSpeed, uEnvScale;
    attribute float aRandom;
    attribute float aPhase;
    varying float vAlpha;
    varying float vRandom;

    void main(){
      float t = uTime * uEnvSpeed;
      vec3 pos = position;
      float type = uEnvType;
      float r = aRandom;
      float phase = aPhase;

      // Default: no movement (off)
      vAlpha = 0.0;

      if (type > 0.5 && type < 1.5) {
        // Stars: stationary, twinkle
        vAlpha = 0.3 + 0.7 * (0.5 + 0.5 * sin(t * (0.5 + r * 1.5) + phase));
      }
      else if (type > 1.5 && type < 2.5) {
        // Rain: fast downward drift
        pos.y = mod(pos.y - t * (1.5 + r * 1.0), 6.0) - 3.0;
        pos.x += sin(r * 20.0 + t * 0.3) * 0.05;
        vAlpha = 0.6 + 0.3 * r;
      }
      else if (type > 2.5 && type < 3.5) {
        // Snow: slow downward with wobble
        pos.y = mod(pos.y - t * (0.3 + r * 0.2), 6.0) - 3.0;
        pos.x += sin(t * 0.8 + phase) * 0.15 * r;
        pos.z += cos(t * 0.6 + phase * 1.3) * 0.1 * r;
        vAlpha = 0.5 + 0.3 * r;
      }
      else if (type > 3.5 && type < 4.5) {
        // Fireflies: slow 3D wander with pulse
        pos.x += sin(t * 0.3 + phase) * 0.4 * r;
        pos.y += cos(t * 0.25 + phase * 1.7) * 0.3 * r;
        pos.z += sin(t * 0.35 + phase * 2.3) * 0.4 * r;
        float pulse = pow(0.5 + 0.5 * sin(t * (1.0 + r * 3.0) + phase), 3.0);
        vAlpha = pulse * 0.9;
      }
      else if (type > 4.5 && type < 5.5) {
        // Embers: rise from bottom, wander
        pos.y = mod(pos.y + t * (0.4 + r * 0.6), 6.0) - 3.0;
        pos.x += sin(t * 0.7 + phase) * 0.2;
        pos.z += cos(t * 0.5 + phase * 1.5) * 0.2;
        float life = 1.0 - (pos.y + 3.0) / 6.0;
        vAlpha = life * (0.5 + 0.5 * r);
      }
      else if (type > 5.5 && type < 6.5) {
        // Dust: very slow drift
        pos.x += sin(t * 0.1 + phase) * 0.15;
        pos.y += cos(t * 0.08 + phase * 1.3) * 0.1;
        pos.z += sin(t * 0.12 + phase * 2.1) * 0.12;
        vAlpha = 0.15 + 0.15 * (0.5 + 0.5 * sin(t * 0.3 + phase));
      }
      else if (type > 6.5 && type < 7.5) {
        // Bubbles: rise with wobble
        pos.y = mod(pos.y + t * (0.2 + r * 0.3), 6.0) - 3.0;
        pos.x += sin(t * 0.6 + phase) * 0.2 * r;
        pos.z += cos(t * 0.5 + phase * 1.4) * 0.15 * r;
        vAlpha = 0.3 + 0.3 * r;
      }
      else if (type > 7.5 && type < 8.5) {
        // Sparks: burst outward from center, short life
        float life = fract(t * 0.4 + r);
        vec3 dir = normalize(position);
        pos = dir * life * 3.0;
        pos.y += life * 0.5;
        vAlpha = (1.0 - life) * 0.8;
      }
      else if (type > 8.5 && type < 9.5) {
        // Leaves: downward with horizontal sine, tumble
        pos.y = mod(pos.y - t * (0.2 + r * 0.15), 6.0) - 3.0;
        pos.x += sin(t * 0.4 + phase) * 0.4;
        pos.z += cos(t * 0.3 + phase * 1.6) * 0.2;
        vAlpha = 0.5 + 0.2 * r;
      }
      else if (type > 9.5) {
        // Energy: orbit around center, pulsing
        float orbitR = length(position.xz);
        float angle = atan(position.z, position.x) + t * (0.5 + r * 0.5);
        pos.x = cos(angle) * orbitR;
        pos.z = sin(angle) * orbitR;
        pos.y += sin(t * 1.5 + phase) * 0.2;
        vAlpha = 0.5 + 0.4 * (0.5 + 0.5 * sin(t * 2.0 + phase));
      }

      vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
      gl_Position = projectionMatrix * mvPos;
      gl_PointSize = uEnvScale * (2.0 + r * 3.0) * (150.0 / -mvPos.z);

      vRandom = r;
    }`;

  const envFragmentShader = `
    uniform vec3 uEnvColor;
    uniform float uEnvIntensity, uEnvDensity;
    varying float vAlpha;
    varying float vRandom;

    void main(){
      vec2 center = gl_PointCoord - 0.5;
      float dist = length(center);
      if(dist > 0.5) discard;
      float alpha = smoothstep(0.5, 0.1, dist);
      alpha *= vAlpha * uEnvIntensity;
      // Density controls visibility threshold
      alpha *= step(1.0 - uEnvDensity, vRandom);
      gl_FragColor = vec4(uEnvColor * (1.0 + uEnvIntensity * 0.5), alpha);
    }`;

  // ── Initialise ───────────────────────────────────────────────────────────
  function init(canvasEl) {
    canvas = canvasEl;
    clock = new THREE.Clock();
    scene = new THREE.Scene();

    // Two-point perspective: camera elevated and slightly offset
    const aspect = canvas.clientWidth / canvas.clientHeight;
    camera = new THREE.PerspectiveCamera(55, aspect, 0.1, 100);
    camera.position.set(0.4, 0.9, 4.5);
    camera.lookAt(0, 0.1, 0);

    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);

    uniforms = {
      uTime: { value: 0 }, uBreath: { value: 0.3 }, uSpeed: { value: 0.5 },
      uExpansion: { value: 1.0 }, uGlow: { value: 0.5 }, uAudioLevel: { value: 0 },
      uSpread: { value: 0 }, uStretch: { value: 0 }, uRing: { value: 0 },
      uSpiral: { value: 0 }, uFlatten: { value: 0 }, uSplit: { value: 0 },
      uChaos: { value: 0 }, uShimmer: { value: 0 }, uDensity: { value: 0.5 },
      uSizeMul: { value: 1 }, uPulse: { value: 0.3 },
      uTurbulence: { value: 0 }, uGravity: { value: 0 },
      uRipple: { value: 0 }, uFlow: { value: 0 },
      uMorph: { value: 0 },
      uScatter: { value: 0 }, uColorSeparation: { value: 0 },
      uHueShift: { value: 0 }, uSaturation: { value: 1.0 },
      uColorPri: { value: new THREE.Vector3(0.83, 0.63, 0.15) },
      uColorSec: { value: new THREE.Vector3(0.91, 0.77, 0.28) },
      uColorAcc: { value: new THREE.Vector3(0.28, 0.78, 0.78) },
      uOrbData: { value: null },
      uOrbMode: { value: 0 },
      uOrbEnergy: { value: 0.3 },
      uOrbSpread: { value: 0 },
      uOrbSize: { value: 1.0 },
      uViscosity: { value: 0.5 },
      uFogDensity: { value: 0 },
      uFogColor: { value: new THREE.Vector3(0.0, 0.0, 0.0) },
      uAmbientColor: { value: new THREE.Vector3(0.12, 0.12, 0.2) },
      uSceneMood: { value: 0.5 },
    };

    // Particle geometry
    const pos = new Float32Array(COUNT * 3), rnd = new Float32Array(COUNT),
          sz = new Float32Array(COUNT), th = new Float32Array(COUNT), ph = new Float32Array(COUNT);
    morphBuffer = new Float32Array(COUNT * 3);

    // Orb DataTexture (1024 x 2, RGBA Float32)
    const orbTexData = new Float32Array(ORB_TEX_WIDTH * 2 * 4);
    orbDataTexture = new THREE.DataTexture(orbTexData, ORB_TEX_WIDTH, 2, THREE.RGBAFormat, THREE.FloatType);
    orbDataTexture.magFilter = THREE.NearestFilter;
    orbDataTexture.minFilter = THREE.NearestFilter;
    orbDataTexture.needsUpdate = true;
    uniforms.uOrbData.value = orbDataTexture;

    for (let i = 0; i < COUNT; i++) {
      const theta = Math.random() * Math.PI * 2, phi = Math.acos(2 * Math.random() - 1);
      const r = 0.8 + Math.random() * 0.4;
      pos[i*3] = r*Math.sin(phi)*Math.cos(theta);
      pos[i*3+1] = r*Math.sin(phi)*Math.sin(theta);
      pos[i*3+2] = r*Math.cos(phi);
      rnd[i] = Math.random(); sz[i] = 1.5 + Math.random()*3.5;
      th[i] = theta; ph[i] = phi;
    }

    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geom.setAttribute("aRandom", new THREE.BufferAttribute(rnd, 1));
    geom.setAttribute("aSize", new THREE.BufferAttribute(sz, 1));
    geom.setAttribute("aTheta", new THREE.BufferAttribute(th, 1));
    geom.setAttribute("aPhi", new THREE.BufferAttribute(ph, 1));
    geom.setAttribute("aMorphTarget", new THREE.BufferAttribute(morphBuffer, 3));

    // Orb index — assign each particle to one of 999 orbs
    const orbIdx = new Float32Array(COUNT);
    for (let i = 0; i < COUNT; i++) {
      orbIdx[i] = Math.floor(i * ORB_COUNT / COUNT);
    }
    geom.setAttribute("aOrbIndex", new THREE.BufferAttribute(orbIdx, 1));

    particles = new THREE.Points(geom, new THREE.ShaderMaterial({
      uniforms, vertexShader, fragmentShader,
      transparent: true, depthWrite: false, blending: THREE.NormalBlending,
    }));
    scene.add(particles);

    // Floor grid
    const floorGeo = new THREE.PlaneGeometry(10, 10, 1, 1);
    const floorMat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
      uniforms: {
        uFloorColor: { value: new THREE.Vector3(0.12, 0.12, 0.2) },
        uAmbientColor: { value: new THREE.Vector3(0.12, 0.12, 0.2) },
        uSceneMood: { value: 0.5 },
      },
      vertexShader: floorVS, fragmentShader: floorFS,
    });
    floorGrid = new THREE.Mesh(floorGeo, floorMat);
    floorGrid.rotation.x = -Math.PI / 2;
    floorGrid.position.y = -1.5;
    scene.add(floorGrid);

    // ── Environment particle system ──
    const envGeom = new THREE.BufferGeometry();
    const envPos = new Float32Array(ENV_COUNT * 3);
    const envRandom = new Float32Array(ENV_COUNT);
    const envPhase = new Float32Array(ENV_COUNT);
    for (let i = 0; i < ENV_COUNT; i++) {
      envPos[i*3]   = (Math.random() - 0.5) * 8;
      envPos[i*3+1] = (Math.random() - 0.5) * 6;
      envPos[i*3+2] = (Math.random() - 0.5) * 8;
      envRandom[i] = Math.random();
      envPhase[i] = Math.random() * 6.2832;
    }
    envGeom.setAttribute("position", new THREE.BufferAttribute(envPos, 3));
    envGeom.setAttribute("aRandom", new THREE.BufferAttribute(envRandom, 1));
    envGeom.setAttribute("aPhase", new THREE.BufferAttribute(envPhase, 1));

    envUniforms = {
      uTime: uniforms.uTime,
      uEnvType: { value: 0 },
      uEnvDensity: { value: 0.5 },
      uEnvSpeed: { value: 0.5 },
      uEnvColor: { value: new THREE.Vector3(1, 1, 1) },
      uEnvIntensity: { value: 0.5 },
      uEnvScale: { value: 1.0 },
    };

    envParticles = new THREE.Points(envGeom, new THREE.ShaderMaterial({
      uniforms: envUniforms,
      vertexShader: envVertexShader,
      fragmentShader: envFragmentShader,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    scene.add(envParticles);

    _rebuildGlow();
    window.addEventListener("resize", onResize);
    onResize();
    animate();
  }

  function _rebuildGlow() {
    glowMeshes.forEach(function(m){ scene.remove(m); }); glowMeshes = [];
    [[currentVisual.priR, currentVisual.priG, currentVisual.priB, 2.0, 0.008],
     [currentVisual.accR, currentVisual.accG, currentVisual.accB, 2.5, 0.004],
     [currentVisual.secR, currentVisual.secG, currentVisual.secB, 1.5, 0.010]].forEach(function(d) {
      var m = new THREE.Mesh(new THREE.SphereGeometry(1,32,32),
        new THREE.MeshBasicMaterial({color: new THREE.Color(d[0],d[1],d[2]), transparent:true, opacity:d[4], side:THREE.BackSide}));
      m.scale.setScalar(d[3]); m._baseOpacity = d[4];
      scene.add(m); glowMeshes.push(m);
    });
  }

  function onResize() {
    if (!canvas||!renderer) return;
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    camera.aspect = canvas.clientWidth / canvas.clientHeight;
    camera.updateProjectionMatrix();
  }

  // ── Animation loop ───────────────────────────────────────────────────────
  let glowTimer = 0;
  function animate() {
    animId = requestAnimationFrame(animate);
    const dt = clock.getDelta(), elapsed = clock.getElapsedTime();

    // Lerp tone
    const tL = 1 - Math.exp(-LERP_SPEED * dt);
    for (const k in currentTone) currentTone[k] += (targetTone[k] - currentTone[k]) * tL;

    // Lerp visual — viscosity modulates snappiness
    const viscLerp = 0.5 + (1.0 - currentVisual.viscosity) * 1.0;
    const vL = 1 - Math.exp(-VIS_LERP_SPEED * viscLerp * dt);
    for (const k in currentVisual) currentVisual[k] += (targetVisual[k] - currentVisual[k]) * vL;

    // Lerp morph
    const mL = 1 - Math.exp(-MORPH_LERP_SPEED * viscLerp * dt);
    currentMorph += (targetMorph - currentMorph) * mL;

    // Scatter / color separation lerp
    const scL = 1 - Math.exp(-2.0 * dt);
    currentScatter += (targetScatter - currentScatter) * scL;
    currentColorSep += (targetColorSep - currentColorSep) * scL;

    // Orb mode lerp
    const orbL = 1 - Math.exp(-1.5 * dt);
    currentOrbMode += (targetOrbMode - currentOrbMode) * orbL;

    // Lerp orb positions and update lighting/texture when orbs active
    if (currentOrbMode > 0.001 || targetOrbMode > 0) {
      const opL = 1 - Math.exp(-1.2 * dt);
      for (let i = 0; i < ORB_COUNT * 3; i++) {
        orbPositions[i] += (orbTargetPositions[i] - orbPositions[i]) * opL;
      }
      _applyOrbColors();
      computeOrbLighting();
      _updateOrbTexture();
    }

    // 5-phase morph state machine:
    // holding → dissolving → scattering → constellation → gathering → reforming → holding
    if (_morphState === "dissolving" && currentMorph < 0.05) {
      // Form fully dissolved — scatter outward
      _setMorphTargets(_pendingMorphGen(COUNT));
      _pendingMorphGen = null;
      targetScatter = 1.0;
      targetColorSep = 1.0;
      _morphState = "scattering";
    }
    if (_morphState === "scattering" && currentScatter > 0.95) {
      // Particles fully scattered — hold as constellation
      _constellationTimer = 0;
      _morphState = "constellation";
    }
    if (_morphState === "constellation") {
      _constellationTimer += dt;
      if (_constellationTimer >= 0.6) {
        // Constellation pause done — gather back
        targetScatter = 0.0;
        targetColorSep = 0.0;
        _morphState = "gathering";
      }
    }
    if (_morphState === "gathering" && currentScatter < 0.05) {
      // Particles converged — reform into new shape
      targetMorph = 1.0;
      _morphState = "reforming";
    }
    if (_morphState === "reforming" && currentMorph > 0.95) {
      _morphState = "holding";
      _morphHoldTimer = 0;
    }
    if (_morphState === "holding") {
      _morphHoldTimer += dt;
      if (_morphHoldTimer >= MORPH_HOLD_MIN) {
        if (_pendingMorphGen) {
          // A new form was requested while holding — dissolve and reform
          targetMorph = 0.0;
          _morphState = "dissolving";
        } else {
          _morphState = "idle";
        }
      }
    }

    // Tone uniforms
    uniforms.uTime.value = elapsed;
    uniforms.uBreath.value = currentTone.breath;
    uniforms.uSpeed.value = currentTone.speed;
    uniforms.uExpansion.value = currentTone.expansion;
    uniforms.uGlow.value = currentTone.glow;

    // Visual uniforms
    uniforms.uSpread.value = currentVisual.spread;
    uniforms.uStretch.value = currentVisual.stretch;
    uniforms.uRing.value = currentVisual.ring;
    uniforms.uSpiral.value = currentVisual.spiral;
    uniforms.uFlatten.value = currentVisual.flatten;
    uniforms.uSplit.value = currentVisual.split;
    uniforms.uChaos.value = currentVisual.chaos;
    uniforms.uShimmer.value = currentVisual.shimmer;
    uniforms.uDensity.value = currentVisual.density;
    uniforms.uSizeMul.value = currentVisual.sizeMul;
    uniforms.uPulse.value = currentVisual.pulse;
    uniforms.uTurbulence.value = currentVisual.turbulence;
    uniforms.uGravity.value = currentVisual.gravity;
    uniforms.uRipple.value = currentVisual.ripple;
    uniforms.uFlow.value = currentVisual.flow;
    uniforms.uMorph.value = currentMorph;
    uniforms.uScatter.value = currentScatter;
    uniforms.uColorSeparation.value = currentColorSep;
    uniforms.uHueShift.value = currentVisual.hueShift;
    uniforms.uSaturation.value = currentVisual.saturation;

    uniforms.uColorPri.value.set(currentVisual.priR, currentVisual.priG, currentVisual.priB);
    uniforms.uColorSec.value.set(currentVisual.secR, currentVisual.secG, currentVisual.secB);
    uniforms.uColorAcc.value.set(currentVisual.accR, currentVisual.accG, currentVisual.accB);

    // Orb + ambiance uniforms
    uniforms.uOrbMode.value = currentOrbMode;
    uniforms.uOrbEnergy.value = currentVisual.orbEnergy;
    uniforms.uOrbSpread.value = currentVisual.orbSpread;
    uniforms.uOrbSize.value = currentVisual.orbSize;
    uniforms.uViscosity.value = currentVisual.viscosity;
    uniforms.uFogDensity.value = currentVisual.fogDensity;
    uniforms.uFogColor.value.set(currentVisual.fogColorR, currentVisual.fogColorG, currentVisual.fogColorB);
    uniforms.uAmbientColor.value.set(currentVisual.ambientR, currentVisual.ambientG, currentVisual.ambientB);
    uniforms.uSceneMood.value = currentVisual.mood;

    // Floor grid ambiance
    if (floorGrid) {
      floorGrid.material.uniforms.uAmbientColor.value.set(currentVisual.ambientR, currentVisual.ambientG, currentVisual.ambientB);
      floorGrid.material.uniforms.uSceneMood.value = currentVisual.mood;
    }

    // Audio
    let rms = 0;
    if (window.AudioPipeline && window.AudioPipeline.getRMS) rms = window.AudioPipeline.getRMS();
    uniforms.uAudioLevel.value += (Math.min(rms*4,1) - uniforms.uAudioLevel.value) * 0.15;

    // Glow colors
    glowTimer += dt;
    if (glowTimer > 0.5 && glowMeshes.length >= 3) {
      glowTimer = 0;
      glowMeshes[0].material.color.setRGB(currentVisual.priR, currentVisual.priG, currentVisual.priB);
      glowMeshes[1].material.color.setRGB(currentVisual.accR, currentVisual.accG, currentVisual.accB);
      glowMeshes[2].material.color.setRGB(currentVisual.secR, currentVisual.secG, currentVisual.secB);
    }
    glowMeshes.forEach(function(m) {
      m.material.opacity = m._baseOpacity * (0.4 + currentTone.glow*0.35) + uniforms.uAudioLevel.value*0.01;
    });

    if (particles) {
      particles.rotation.y += dt * 0.05 * currentTone.speed;
      particles.rotation.x = Math.sin(elapsed * 0.1) * 0.05;
      // Spatial movement — Nova walks around in 3D space
      particles.position.x = currentVisual.posX;
      particles.position.y = currentVisual.posY;
      particles.position.z = currentVisual.posZ;
    }
    // Glow meshes follow spatial position
    glowMeshes.forEach(function(m) {
      m.position.x = currentVisual.posX;
      m.position.y = currentVisual.posY;
      m.position.z = currentVisual.posZ;
    });
    // ── Environment particles ──
    const eL = 1 - Math.exp(-2.0 * dt);
    for (const k in currentEnv) {
      if (k === "envType") { currentEnv[k] = targetEnv[k]; continue; }
      currentEnv[k] += (targetEnv[k] - currentEnv[k]) * eL;
    }
    if (envUniforms) {
      envUniforms.uEnvType.value = currentEnv.envType;
      envUniforms.uEnvDensity.value = currentEnv.envDensity;
      envUniforms.uEnvSpeed.value = currentEnv.envSpeed;
      envUniforms.uEnvColor.value.set(currentEnv.envColorR, currentEnv.envColorG, currentEnv.envColorB);
      envUniforms.uEnvIntensity.value = currentEnv.envIntensity;
      envUniforms.uEnvScale.value = currentEnv.envScale;
    }

    renderer.render(scene, camera);
  }

  // ── Public API ───────────────────────────────────────────────────────────
  function setTone(toneName) {
    let n = toneName;
    if (n && n.startsWith("voice:")) n = "excited";
    targetTone = { ...(TONE_PRESETS[n] || TONE_PRESETS.neutral) };
  }

  function setVisual(params) {
    if (params.palette) {
      const palName = String(params.palette);
      if (palName.includes("+")) {
        // Blend multiple palettes: "ocean+volcanic" or "ocean+volcanic+sakura"
        const names = palName.split("+");
        const valid = names.map(function(n){ return PALETTES[n.trim()]; }).filter(Boolean);
        if (valid.length > 0) {
          let pr=0,pg=0,pb=0,sr=0,sg=0,sb=0,ar=0,ag=0,ab=0;
          for (let i = 0; i < valid.length; i++) {
            pr+=valid[i].pri[0]; pg+=valid[i].pri[1]; pb+=valid[i].pri[2];
            sr+=valid[i].sec[0]; sg+=valid[i].sec[1]; sb+=valid[i].sec[2];
            ar+=valid[i].acc[0]; ag+=valid[i].acc[1]; ab+=valid[i].acc[2];
          }
          const n = valid.length;
          targetVisual.priR=pr/n; targetVisual.priG=pg/n; targetVisual.priB=pb/n;
          targetVisual.secR=sr/n; targetVisual.secG=sg/n; targetVisual.secB=sb/n;
          targetVisual.accR=ar/n; targetVisual.accG=ag/n; targetVisual.accB=ab/n;
        }
      } else {
        const p = PALETTES[palName];
        if (p) {
          targetVisual.priR=p.pri[0]; targetVisual.priG=p.pri[1]; targetVisual.priB=p.pri[2];
          targetVisual.secR=p.sec[0]; targetVisual.secG=p.sec[1]; targetVisual.secB=p.sec[2];
          targetVisual.accR=p.acc[0]; targetVisual.accG=p.acc[1]; targetVisual.accB=p.acc[2];
        }
      }
    }
    // Direct color overrides (R/G/B, 0-1 range)
    if (params.pri !== undefined) {
      const rgb = String(params.pri).split("/");
      if (rgb.length === 3) { targetVisual.priR=parseFloat(rgb[0])||0; targetVisual.priG=parseFloat(rgb[1])||0; targetVisual.priB=parseFloat(rgb[2])||0; }
    }
    if (params.sec !== undefined) {
      const rgb = String(params.sec).split("/");
      if (rgb.length === 3) { targetVisual.secR=parseFloat(rgb[0])||0; targetVisual.secG=parseFloat(rgb[1])||0; targetVisual.secB=parseFloat(rgb[2])||0; }
    }
    if (params.acc !== undefined) {
      const rgb = String(params.acc).split("/");
      if (rgb.length === 3) { targetVisual.accR=parseFloat(rgb[0])||0; targetVisual.accG=parseFloat(rgb[1])||0; targetVisual.accB=parseFloat(rgb[2])||0; }
    }
    if (params.form) {
      const morphGen = MORPH_GENS[params.form];
      const abstractForm = FORMS[params.form];

      if (morphGen) {
        // Real-world morph form
        // Also generate orb targets for orb mode
        _setOrbTargets(morphGen(ORB_COUNT));
        if (_morphState === "holding") {
          // Currently holding stable — queue the new form, it will
          // trigger once hold time expires
          _pendingMorphGen = morphGen;
        } else if (_morphState === "reforming") {
          // Still forming — queue replacement
          _pendingMorphGen = morphGen;
        } else if (currentMorph > 0.05 && _morphState !== "dissolving") {
          // Already morphed and idle: dissolve first, then reform
          _pendingMorphGen = morphGen;
          targetMorph = 0.0;
          _morphState = "dissolving";
        } else if (_morphState === "dissolving") {
          // Already dissolving, update pending
          _pendingMorphGen = morphGen;
        } else {
          // Not morphed: scatter outward first, then gather and reform
          _setMorphTargets(morphGen(COUNT));
          targetScatter = 1.0;
          targetColorSep = 1.0;
          _morphState = "scattering";
        }
        // Reset abstract form params to neutral
        targetVisual.spread = 0; targetVisual.stretch = 0;
        targetVisual.ring = 0; targetVisual.spiral = 0;
        targetVisual.flatten = 0; targetVisual.split = 0;
      } else if (abstractForm) {
        // Abstract form: deactivate morph and scatter
        targetMorph = 0.0;
        targetScatter = 0.0;
        targetColorSep = 0.0;
        _morphState = "idle";
        _pendingMorphGen = null;
        targetVisual.spread = abstractForm.spread;
        targetVisual.stretch = abstractForm.stretch;
        targetVisual.ring = abstractForm.ring;
        targetVisual.spiral = abstractForm.spiral;
        targetVisual.flatten = abstractForm.flatten;
        targetVisual.split = abstractForm.split;
      }
    }
    // Fine-tuning params
    if (params.speed !== undefined)      targetTone.speed = cl(params.speed, 0, 2);
    if (params.glow !== undefined)       targetTone.glow = cl(params.glow, 0, 1.5);
    if (params.chaos !== undefined)      targetVisual.chaos = cl(params.chaos, 0, 1);
    if (params.shimmer !== undefined)    targetVisual.shimmer = cl(params.shimmer, 0, 1);
    if (params.density !== undefined)    targetVisual.density = cl(params.density, 0, 1);
    if (params.size !== undefined)       targetVisual.sizeMul = cl(params.size, 0.3, 3);
    if (params.pulse !== undefined)      targetVisual.pulse = cl(params.pulse, 0, 1);
    if (params.turbulence !== undefined) targetVisual.turbulence = cl(params.turbulence, 0, 1);
    if (params.gravity !== undefined)    targetVisual.gravity = cl(params.gravity, -1, 1);
    if (params.ripple !== undefined)     targetVisual.ripple = cl(params.ripple, 0, 1);
    if (params.flow !== undefined)       targetVisual.flow = cl(params.flow, -1, 1);
    if (params.hue !== undefined)        targetVisual.hueShift = cl(params.hue, 0, 360);
    if (params.saturation !== undefined) targetVisual.saturation = cl(params.saturation, 0, 2);
    if (params.orbenergy !== undefined) targetVisual.orbEnergy = cl(params.orbenergy, 0, 1);
    if (params.orbspread !== undefined) targetVisual.orbSpread = cl(params.orbspread, 0, 1);
    if (params.orbsize !== undefined)  targetVisual.orbSize = cl(params.orbsize, 0.1, 3);
    if (params.orbsizevar !== undefined) {
      targetVisual.orbSizeVar = cl(params.orbsizevar, 0, 1);
      // Regenerate per-orb sizes with deterministic randomness
      const v = targetVisual.orbSizeVar;
      for (let i = 0; i < ORB_COUNT; i++) {
        // Deterministic hash per orb so sizes are stable
        const seed = Math.sin(i * 127.1 + 311.7) * 43758.5453;
        const r = seed - Math.floor(seed); // 0-1
        orbSizes[i] = Math.max(0.05, 1.0 + (r * 2.0 - 1.0) * v);
      }
    }
    if (params.viscosity !== undefined) targetVisual.viscosity = cl(params.viscosity, 0, 1);
    if (params.x !== undefined)         targetVisual.posX = cl(params.x, -3, 3);
    if (params.y !== undefined)         targetVisual.posY = cl(params.y, -2, 2);
    if (params.z !== undefined)         targetVisual.posZ = cl(params.z, -3, 3);

    // Orb mode control
    if (params.orbmode !== undefined) {
      if (params.orbmode === "separated") {
        targetOrbMode = 1;
      } else {
        targetOrbMode = 0;
      }
    }

    // Ambiance controls
    if (params.fog !== undefined)        targetVisual.fogDensity = cl(params.fog, 0, 1);
    if (params.mood !== undefined)       targetVisual.mood = cl(params.mood, 0, 1);
    if (params.fogcolor !== undefined) {
      const rgb = String(params.fogcolor).split("/");
      if (rgb.length === 3) {
        targetVisual.fogColorR = parseFloat(rgb[0]) || 0;
        targetVisual.fogColorG = parseFloat(rgb[1]) || 0;
        targetVisual.fogColorB = parseFloat(rgb[2]) || 0;
      }
    }
    if (params.ambientcolor !== undefined) {
      const rgb = String(params.ambientcolor).split("/");
      if (rgb.length === 3) {
        targetVisual.ambientR = parseFloat(rgb[0]) || 0;
        targetVisual.ambientG = parseFloat(rgb[1]) || 0;
        targetVisual.ambientB = parseFloat(rgb[2]) || 0;
      }
    }

    // ── Environment particle controls ──
    if (params.env !== undefined) {
      const envName = String(params.env).toLowerCase();
      if (envName in ENV_TYPES) {
        targetEnv.envType = ENV_TYPES[envName];
        // When turning off, fade intensity to 0
        if (envName === "off") targetEnv.envIntensity = 0;
        else if (currentEnv.envType === 0) targetEnv.envIntensity = 0.5;
      }
    }
    if (params.envcolor !== undefined) {
      const rgb = String(params.envcolor).split("/");
      if (rgb.length === 3) {
        targetEnv.envColorR = parseFloat(rgb[0]) || 0;
        targetEnv.envColorG = parseFloat(rgb[1]) || 0;
        targetEnv.envColorB = parseFloat(rgb[2]) || 0;
      }
    }
    if (params.envdensity !== undefined)   targetEnv.envDensity = cl(params.envdensity, 0, 1);
    if (params.envspeed !== undefined)     targetEnv.envSpeed = cl(params.envspeed, 0, 2);
    if (params.envintensity !== undefined) targetEnv.envIntensity = cl(params.envintensity, 0, 1);
    if (params.envscale !== undefined)     targetEnv.envScale = cl(params.envscale, 0.5, 3);
  }

  function cl(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  return { init, setTone, setVisual };
})();
