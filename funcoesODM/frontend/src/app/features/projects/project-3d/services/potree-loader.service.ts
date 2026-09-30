import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import {
  BehaviorSubject, Observable, interval, switchMap,
  takeWhile, tap, firstValueFrom
} from 'rxjs';
import * as THREE from 'three';
import { PointCloudOctree, Potree } from '@pnext/three-loader';
import { environment } from '../../../../../environments/environment';

export type PotreeConversionStatus = 'idle' | 'checking' | 'converting' | 'ready' | 'failed';

export interface PotreeStatus {
  status: string;
  tilesUrl?: string;
  error?: string;
  startedAt?: string;
  completedAt?: string;
}

@Injectable()
export class PotreeLoaderService {
  private http = inject(HttpClient);

  private conversionStatus$ = new BehaviorSubject<PotreeConversionStatus>('idle');
  private conversionProgress$ = new BehaviorSubject<number>(0);

  private potree?: Potree;
  private pointCloud?: PointCloudOctree;

  readonly conversionStatus = this.conversionStatus$.asObservable();
  readonly conversionProgress = this.conversionProgress$.asObservable();

  /**
   * Inicia o fluxo completo: verifica status, dispara conversao se necessario,
   * faz polling ate ready, e carrega os tiles no renderer.
   */
  async loadPotreePointCloud(
    projectId: number,
    taskId: number,
    scene: THREE.Scene,
    camera: THREE.Camera,
    renderer: THREE.WebGLRenderer
  ): Promise<PointCloudOctree> {
    this.conversionStatus$.next('checking');

    const statusUrl = `${environment.apiUrl}/projects/${projectId}/tasks/${taskId}/potree`;

    // Primeira chamada — aciona conversao se necessario
    let status = await firstValueFrom(this.http.get<PotreeStatus>(statusUrl));

    if (status.status === 'not_started' || status.status === 'converting') {
      this.conversionStatus$.next('converting');
      this.conversionProgress$.next(0);

      // Polling ate ready ou failed
      status = await firstValueFrom(
        interval(3000).pipe(
          switchMap(() => this.http.get<PotreeStatus>(statusUrl)),
          tap(s => {
            if (s.status === 'converting') {
              // Animacao de progresso indeterminado
              const cur = this.conversionProgress$.value;
              this.conversionProgress$.next(Math.min(cur + 2, 92));
            }
          }),
          takeWhile(s => s.status === 'converting' || s.status === 'not_started', true)
        )
      );
    }

    if (status.status === 'failed') {
      this.conversionStatus$.next('failed');
      throw new Error('Conversao Potree falhou: ' + (status.error ?? 'erro desconhecido'));
    }

    if (status.status !== 'ready' || !status.tilesUrl) {
      this.conversionStatus$.next('failed');
      throw new Error('Status inesperado: ' + status.status);
    }

    this.conversionStatus$.next('ready');
    this.conversionProgress$.next(100);

    // Carrega tiles com @pnext/three-loader
    this.potree = new Potree();
    this.potree.pointBudget = 2_000_000;

    const tilesBaseUrl = status.tilesUrl + 'cloud.js';
    this.pointCloud = await this.potree.loadPointCloud(
      tilesBaseUrl,
      url => url
    );

    this.pointCloud.rotateX(-Math.PI / 2); // Potree usa Z-up, Three.js Y-up
    scene.add(this.pointCloud);

    return this.pointCloud;
  }

  /**
   * Chama no loop de animacao para atualizar o LOD das tiles.
   */
  update(renderer: THREE.WebGLRenderer, camera: THREE.Camera, scene: THREE.Scene): void {
    if (this.potree && this.pointCloud) {
      this.potree.updatePointClouds([this.pointCloud], camera, renderer);
    }
  }

  getPointCloud(): PointCloudOctree | undefined {
    return this.pointCloud;
  }

  dispose(): void {
    if (this.pointCloud) {
      this.pointCloud.dispose();
    }
    this.conversionStatus$.complete();
    this.conversionProgress$.complete();
  }
}
