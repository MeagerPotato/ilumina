// Builds the stage: floor, furniture, props, both actors and the effect pools.
import * as THREE from 'three';
import { pixelMat, withPixAttrs, createLights } from './engine.js';
import { createStudent, createPhilosopher } from './characters.js';
import {
  buildDesk, buildDeskStuff, buildPaper, addWriting, buildPencil, buildChair, buildRock, buildRubble,
  buildScorch, buildBin, buildPaperBall, buildGun, buildMissile, buildFlame, buildDevice, buildFlag, PAL,
} from './models.js';
import { FX } from './fx.js';

export const LAYOUT = {
  desk: new THREE.Vector3(-10, 0, 15),
  chair: new THREE.Vector3(-10, 0, -8),
  rock: new THREE.Vector3(46, 0, -12),
  bin: new THREE.Vector3(-56, 0, 18),
  paper: new THREE.Vector3(-13, 40, 13),
  deviceDesk: new THREE.Vector3(2, 40, 21),
};

export function buildStage() {
  const scene = new THREE.Scene();
  const lights = createLights(scene);

  const floorGeo = new THREE.CircleGeometry(170, 128);
  floorGeo.rotateX(-Math.PI / 2);
  withPixAttrs(floorGeo);
  const floor = new THREE.Mesh(floorGeo, pixelMat({ floor: true, vertexColors: false }));
  floor.receiveShadow = true;
  scene.add(floor);

  const propMat = pixelMat();
  const desk = buildDesk().mesh(propMat);
  desk.position.copy(LAYOUT.desk);
  scene.add(desk);

  const deskStuff = buildDeskStuff().mesh(propMat);
  deskStuff.position.copy(LAYOUT.desk);
  scene.add(deskStuff);

  // two sheets: the one that gets crumpled, and the fresh one under it
  const paper1Grid = buildPaper(3);
  const p1Start = addWriting(paper1Grid, 11, [[2, 5, -6]], 0);
  const p1Lines = addWriting(paper1Grid, 12, [[-1, 5, -5]], p1Start);
  const p1Messy = addWriting(paper1Grid, 13, [[-4, 5, -6], [-6, 5, -6], [-8, 4, -5]], 100, 0x3f4350, true);
  const paper1Mat = pixelMat();
  const paper1 = paper1Grid.mesh(paper1Mat, 0.5, 0, 0.5, { cast: false });
  paper1.position.copy(LAYOUT.paper);
  paper1.rotation.y = -0.14;
  scene.add(paper1);

  const paper2Grid = buildPaper(5);
  const p2Keys = addWriting(paper2Grid, 21, [[2, 5, -6], [-1, 5, -4], [-4, 5, -6], [-7, 4, -3]], 1, 0x4d5260);
  const paper2Mat = pixelMat();
  const paper2 = paper2Grid.mesh(paper2Mat, 0.5, 0, 0.5, { cast: false });
  paper2.position.copy(LAYOUT.paper).add(new THREE.Vector3(1, -0.02, -1));
  paper2.rotation.y = -0.05;
  scene.add(paper2);

  const chair = buildChair().mesh(propMat);
  chair.position.copy(LAYOUT.chair);
  scene.add(chair);

  const rock = buildRock().mesh(propMat);
  rock.position.copy(LAYOUT.rock);
  scene.add(rock);
  const rubble = buildRubble().mesh(propMat);
  rubble.position.copy(LAYOUT.rock);
  rubble.visible = false;
  scene.add(rubble);
  const scorch = buildScorch().mesh(propMat, 0, 0, 0, { cast: false });
  scorch.position.copy(LAYOUT.rock).add(new THREE.Vector3(0, -0.6, 0));
  scorch.visible = false;
  scene.add(scorch);

  const bin = buildBin().mesh(propMat);
  bin.position.copy(LAYOUT.bin);
  scene.add(bin);

  const ballGeo = buildPaperBall().geometry(0.5, 0.5, 0.5);
  const paperBall = new THREE.Mesh(ballGeo, propMat);
  paperBall.castShadow = true;
  paperBall.visible = false;
  scene.add(paperBall);

  // actors
  const student = createStudent();
  scene.add(student.rig.root);
  const phil = createPhilosopher();
  scene.add(phil.rig.root);

  const pencil = buildPencil().mesh(propMat, 0.5, 0.5, 6);
  student.rig.elR.add(pencil);
  pencil.position.set(0.3, -16.5, 2.5);
  pencil.rotation.set(1.15, 0, 0);
  const pencilBits = [0, 1].map(() => {
    const m = buildPencil().mesh(propMat, 0.5, 0.5, 6);
    m.scale.set(1, 1, 0.5);
    m.visible = false;
    scene.add(m);
    return m;
  });

  const flag = buildFlag().mesh(propMat, 0.5, 0, 0.5);
  phil.rig.elR.add(flag);
  flag.position.set(0, -17, 2);
  flag.rotation.x = Math.PI; // the stick points out past the fist
  flag.visible = false;

  // the gun and its moving parts
  const gunGrids = buildGun();
  const gunMat = pixelMat();
  const gun = new THREE.Group();
  const gunBody = gunGrids.body.mesh(gunMat, 0, 0, 0);
  gun.add(gunBody);
  const barrels = gunGrids.barrels.mesh(gunMat, 0, 0, 0);
  const barrelPivot = new THREE.Group();
  barrelPivot.position.set(-0.5, 6, 64);
  barrelPivot.add(barrels);
  gun.add(barrelPivot);
  const podL = new THREE.Group();
  podL.position.set(5, 13, 10);
  podL.add(gunGrids.podL.mesh(gunMat, 0, 0, 0));
  const podR = new THREE.Group();
  podR.position.set(-6, 13, 10);
  podR.add(gunGrids.podR.mesh(gunMat, 0, 0, 0));
  gun.add(podL, podR);
  const knifeL = new THREE.Group();
  knifeL.position.set(6, 6, 48);
  knifeL.add(gunGrids.knifeL.mesh(gunMat, 0, 0, 0));
  const knifeR = new THREE.Group();
  knifeR.position.set(-8, 6, 48);
  knifeR.add(gunGrids.knifeR.mesh(gunMat, 0, 0, 0));
  gun.add(knifeL, knifeR);
  const flash = gunGrids.flash.mesh(pixelMat({ unlit: true }), 0, 0, 0, { cast: false, receive: false });
  flash.position.set(-0.5, 6, 93);
  gun.add(flash);
  gun.visible = false;
  scene.add(gun);

  const missileGrid = buildMissile();
  const flameGrid = buildFlame();
  const flameMat = pixelMat({ unlit: true });
  const missiles = [0, 1, 2, 3].map(() => {
    const g = new THREE.Group();
    g.add(missileGrid.mesh(gunMat, 0.5, 0.5, 8));
    const fl = flameGrid.mesh(flameMat, 0.5, 0.5, -8, { cast: false, receive: false });
    g.add(fl);
    g.visible = false;
    scene.add(g);
    return g;
  });

  // the wearable
  const deviceMat = pixelMat();
  const device = buildDevice().mesh(deviceMat, 0, 0, 0);
  const deviceRoot = new THREE.Group();
  deviceRoot.add(device);
  scene.add(deviceRoot);
  deviceRoot.visible = false;

  const fx = new FX(scene);

  return {
    scene, lights, floor, desk, deskStuff, paper1, paper1Mat, paper2, paper2Mat, p1Start, p1Lines, p1Messy, p2Keys,
    chair, rock, rubble, scorch, bin, paperBall, student, phil, pencil, pencilBits, flag,
    gun, gunBody, barrelPivot, podL, podR, knifeL, knifeR, flash, missiles, device: deviceRoot, deviceMat, fx, PAL,
  };
}
