import {
  Component, Input, OnInit, OnDestroy, AfterViewInit, OnChanges, SimpleChanges,
  ElementRef, ViewChild, signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { Viewer3DService } from '../../../features/projects/project-3d/services/viewer-3d.service';
import { PotreeLoaderService } from '../../../features/projects/project-3d/services/potree-loader.service';

@Component({
  selector: 'app-pointcloud-viewer',
  standalone: true,
  imports: [CommonModule],
  providers: [Viewer3DService, PotreeLoaderService],
  template: `
    <div class="pcv-wrapper">

      <!-- Loading -->
      @if (loading()) {
        <div class="pcv-loading">
          <div class="pcv-spinner"></div>
          <p>Carregando modelo 3D...</p>
          <div class="pcv-bar"><div class="pcv-fill" [style.width.%]="progress()"></div></div>
          <span class="pcv-pct">{{ progress() }}%</span>
        </div>
      }

      <!-- Error / sem dados -->
      @if (!loading() && !hasData()) {
        <div class="pcv-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 3L2 7.5l10 4.5 10-4.5L12 3z"/>
            <path d="M2 17.5l10 4.5 10-4.5"/>
            <path d="M2 12.5l10 4.5 10-4.5"/>
          </svg>
          <p>{{ errorMsg() || 'Modelo 3D indisponivel. Execute o processamento primeiro.' }}</p>
        </div>
      }

      <!-- Canvas WebGL -->
      <canvas #canvas3d class="pcv-canvas"></canvas>

      <!-- Stats -->
      @if (!loading() && hasData()) {
        <div class="pcv-stats">
          <span>{{ stats().fps }} FPS</span>
          <span>{{ formatNum(stats().points) }} vertices</span>
          @if (stats().memory > 0) { <span>{{ stats().memory }} MB</span> }
        </div>
      }
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; height: 100%; }

    .pcv-wrapper {
      position: relative;
      width: 100%;
      height: 100%;
      background: #1e293b;
      overflow: hidden;
    }

    .pcv-canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .pcv-loading {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      color: #94a3b8;
      font-size: 0.875rem;
      z-index: 10;
    }

    .pcv-spinner {
      width: 2.5rem;
      height: 2.5rem;
      border: 3px solid #334155;
      border-top-color: #3b82f6;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .pcv-bar {
      width: 200px;
      height: 4px;
      background: #334155;
      border-radius: 2px;
      overflow: hidden;
    }
    .pcv-fill {
      height: 100%;
      background: #3b82f6;
      transition: width 0.3s;
    }
    .pcv-pct { color: #64748b; font-size: 0.75rem; }

    .pcv-empty {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      color: #64748b;
      text-align: center;
      padding: 2rem;

      svg {
        width: 4rem;
        height: 4rem;
        opacity: 0.4;
      }
      p { max-width: 320px; font-size: 0.9rem; }
    }

    .pcv-stats {
      position: absolute;
      bottom: 1rem;
      left: 1rem;
      display: flex;
      gap: 0.5rem;
      z-index: 5;

      span {
        padding: 0.25rem 0.6rem;
        background: rgba(0,0,0,0.6);
        color: #60a5fa;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.75rem;
      }
    }
  `]
})
export class PointcloudViewerComponent implements OnInit, AfterViewInit, OnChanges, OnDestroy {
  @ViewChild('canvas3d') canvasRef!: ElementRef<HTMLCanvasElement>;

  @Input() projectId!: number;
  @Input() taskId?: number;
  @Input() nodeodmTaskId?: string;

  loading = signal(true);
  progress = signal(0);
  hasData = signal(false);
  errorMsg = signal<string | null>(null);
  stats = signal({ fps: 0, points: 0, memory: 0 });

  private viewerReady = false;
  private loaded = false;

  constructor(private viewer: Viewer3DService, private http: HttpClient) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['taskId'] && this.viewerReady && !this.loaded && this.taskId) {
      this.tryLoad();
    }
  }

  ngOnInit(): void {
    this.viewer.getLoadProgress().subscribe(p => {
      this.progress.set(p);
      if (p >= 100) setTimeout(() => this.loading.set(false), 400);
    });
    this.viewer.getStats().subscribe(s => this.stats.set(s));
  }

  ngAfterViewInit(): void {
    this.viewer.initViewer(this.canvasRef);
    this.viewerReady = true;
    this.tryLoad();
  }

  ngOnDestroy(): void {
    this.viewer.destroy();
  }

  private async tryLoad(): Promise<void> {
    if (this.loaded) return;
    if (!this.projectId) {
      this.errorMsg.set('Projeto nao identificado.');
      this.loading.set(false);
      this.hasData.set(false);
      return;
    }

    // taskId do Input pode ser chunk.id, nao processing_task.id.
    // Sempre busca a task completada via API para garantir o ID correto.
    let processingTaskId: number | undefined;
    try {
      const tasks = await firstValueFrom(
        this.http.get<Array<{ id: number; status: string }>>(`/api/v1/projects/${this.projectId}/tasks`)
      );
      const done = tasks.find(t => t.status === 'COMPLETED' || t.status === 'COMPLETED_WITH_WARNINGS');
      if (!done) {
        this.errorMsg.set('Nenhum processamento concluido para este projeto.');
        this.loading.set(false);
        this.hasData.set(false);
        return;
      }
      processingTaskId = done.id;
    } catch {
      this.errorMsg.set('Erro ao buscar dados de processamento.');
      this.loading.set(false);
      this.hasData.set(false);
      return;
    }

    try {
      this.loaded = true;
      await this.viewer.loadMesh(this.projectId, processingTaskId);
      this.hasData.set(true);
    } catch (err: any) {
      this.errorMsg.set(err?.message ?? 'Erro ao carregar modelo 3D.');
      this.hasData.set(false);
      this.loading.set(false);
    }
  }

  formatNum(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
    return n.toString();
  }
}
