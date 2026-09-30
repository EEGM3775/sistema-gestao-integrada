import { Injectable, ElementRef, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, firstValueFrom } from 'rxjs';
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { ViewerStats, ColorMode } from '../models/project-3d.model';
import { environment } from '../../../../../environments/environment';
import { PotreeLoaderService } from './potree-loader.service';

export type ViewerMode = 'mesh' | 'pointcloud';

@Injectable()
export class Viewer3DService {
  private http = inject(HttpClient);
  readonly potree = inject(PotreeLoaderService);

  private loadProgress$ = new BehaviorSubject<number>(0);
  private stats$ = new BehaviorSubject<ViewerStats>({ points: 0, fps: 0, memory: 0 });

  private renderer?: THREE.WebGLRenderer;
  private scene?: THREE.Scene;
  private camera?: THREE.PerspectiveCamera;
  private controls?: OrbitControls;
  private animationId?: number;
  private meshObject?: THREE.Mesh;
  private grid?: THREE.GridHelper;
  private axes?: THREE.AxesHelper;
  private resizeObserver?: ResizeObserver;

  private fpsFrames = 0;
  private fpsLast = 0;
  private rawGeometry?: THREE.BufferGeometry;
  private currentColorMode: ColorMode = 'elevation';

  getLoadProgress(): Observable<number> {
    return this.loadProgress$.asObservable();
  }

  getStats(): Observable<ViewerStats> {
    return this.stats$.asObservable();
  }

  initViewer(canvasEl: ElementRef<HTMLCanvasElement>): void {
    const canvas = canvasEl.nativeElement;
    const w = canvas.clientWidth || 800;
    const h = canvas.clientHeight || 600;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setSize(w, h, false);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x1e293b);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x1e293b, 500, 2000);

    this.camera = new THREE.PerspectiveCamera(60, w / h, 0.01, 10000);
    this.camera.position.set(0, 50, 100);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.screenSpacePanning = true;

    const ambient = new THREE.AmbientLight(0xffffff, 0.8);
    const dir = new THREE.DirectionalLight(0xffffff, 0.6);
    dir.position.set(1, 3, 2);
    this.scene.add(ambient, dir);

    this.grid = new THREE.GridHelper(200, 20, 0x334155, 0x263447);
    this.scene.add(this.grid);

    this.axes = new THREE.AxesHelper(10);
    this.scene.add(this.axes);

    this.resizeObserver = new ResizeObserver(() => this.onResize());
    this.resizeObserver.observe(canvas);

    this.fpsLast = performance.now();
    this.animate();
  }

  async loadMesh(projectId: number, taskId: number): Promise<void> {
    if (!this.scene) return;

    const url = `${environment.apiUrl}/projects/${projectId}/tasks/${taskId}/download/mesh`;

    this.loadProgress$.next(10);

    let buffer: ArrayBuffer;
    try {
      buffer = await firstValueFrom(
        this.http.get(url, { responseType: 'arraybuffer' })
      );
    } catch {
      this.loadProgress$.next(0);
      throw new Error('Arquivo mesh.ply nao encontrado para esta task.');
    }

    this.loadProgress$.next(55);

    const loader = new PLYLoader();
    const geometry = loader.parse(buffer);
    geometry.computeVertexNormals();
    this.rawGeometry = geometry;

    this.loadProgress$.next(75);

    this.applyColorMode(geometry, this.currentColorMode);

    this.loadProgress$.next(90);

    if (this.meshObject) {
      this.scene.remove(this.meshObject);
      this.meshObject.geometry.dispose();
      (this.meshObject.material as THREE.Material).dispose();
    }

    const material = new THREE.MeshPhongMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      shininess: 30,
    });

    this.meshObject = new THREE.Mesh(geometry, material);

    geometry.computeBoundingBox();
    const center = new THREE.Vector3();
    geometry.boundingBox!.getCenter(center);
    this.meshObject.position.sub(center);
    this.scene.add(this.meshObject);

    const size = new THREE.Vector3();
    geometry.boundingBox!.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);

    this.camera!.position.set(0, maxDim * 0.6, maxDim * 1.4);
    this.camera!.near = maxDim * 0.001;
    this.camera!.far = maxDim * 20;
    this.camera!.updateProjectionMatrix();
    this.controls!.target.set(0, 0, 0);
    this.controls!.update();

    this.grid!.scale.setScalar(maxDim / 100);
    this.grid!.position.y = -(size.y / 2);
    this.axes!.scale.setScalar(maxDim / 8);

    const vertexCount = geometry.attributes['position'].count;
    this.stats$.next({ ...this.stats$.value, points: vertexCount });
    this.loadProgress$.next(100);
  }

  async loadPointCloudPotree(projectId: number, taskId: number): Promise<void> {
    if (!this.scene || !this.camera || !this.renderer) return;

    if (this.meshObject) {
      this.scene.remove(this.meshObject);
      this.meshObject.geometry.dispose();
      (this.meshObject.material as THREE.Material).dispose();
      this.meshObject = undefined;
    }

    const pc = await this.potree.loadPotreePointCloud(
      projectId, taskId,
      this.scene, this.camera, this.renderer
    );

    const count = pc.numVisiblePoints ?? 0;
    this.stats$.next({ ...this.stats$.value, points: count });
    this.loadProgress$.next(100);
  }

  setColorMode(mode: ColorMode): void {
    this.currentColorMode = mode;
    if (this.rawGeometry && this.meshObject) {
      this.applyColorMode(this.rawGeometry, mode);
      (this.rawGeometry.attributes['color'] as THREE.BufferAttribute).needsUpdate = true;
    }
  }

  private applyColorMode(geometry: THREE.BufferGeometry, mode: ColorMode): void {
    const pos = geometry.attributes['position'] as THREE.BufferAttribute;
    const hasVertexColors = !!geometry.attributes['color'];

    if (mode === 'rgb' && hasVertexColors) {
      return;
    }

    let minZ = Infinity, maxZ = -Infinity;
    for (let i = 0; i < pos.count; i++) {
      const z = pos.getZ(i);
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    }
    const range = maxZ - minZ || 1;

    const colors = new Float32Array(pos.count * 3);
    const color = new THREE.Color();

    for (let i = 0; i < pos.count; i++) {
      const t = (pos.getZ(i) - minZ) / range;
      // azul (frio/baixo) -> verde -> amarelo -> vermelho (quente/alto)
      color.setHSL(0.667 * (1 - t), 0.9, 0.4 + t * 0.15);
      colors[i * 3]     = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }

    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  }

  private animate(): void {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls?.update();
    if (this.scene && this.camera && this.renderer) {
      this.potree.update(this.renderer, this.camera, this.scene);
      this.renderer.render(this.scene, this.camera);
    }

    this.fpsFrames++;
    const now = performance.now();
    if (now - this.fpsLast >= 1000) {
      const fps = Math.round(this.fpsFrames * 1000 / (now - this.fpsLast));
      const memBytes = (performance as any).memory?.usedJSHeapSize ?? 0;
      const memory = Math.round(memBytes / 1_048_576);
      this.stats$.next({ ...this.stats$.value, fps, memory });
      this.fpsFrames = 0;
      this.fpsLast = now;
    }
  }

  private onResize(): void {
    if (!this.renderer || !this.camera) return;
    const canvas = this.renderer.domElement;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  reset(): void {
    if (!this.controls || !this.camera) return;
    this.camera.position.set(0, 50, 100);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  setShowGrid(show: boolean): void {
    if (this.grid) this.grid.visible = show;
  }

  setShowAxes(show: boolean): void {
    if (this.axes) this.axes.visible = show;
  }

  screenshot(): string {
    if (!this.renderer || !this.scene || !this.camera) return '';
    this.renderer.render(this.scene, this.camera);
    return this.renderer.domElement.toDataURL('image/png');
  }

  destroy(): void {
    if (this.animationId) cancelAnimationFrame(this.animationId);
    this.resizeObserver?.disconnect();
    this.meshObject?.geometry.dispose();
    (this.meshObject?.material as THREE.Material | undefined)?.dispose();
    this.potree.dispose();
    this.renderer?.dispose();
    this.loadProgress$.complete();
    this.stats$.complete();
  }
}
