import { Component, OnInit, OnDestroy, AfterViewInit, ElementRef, ViewChild, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { ViewerControlsComponent } from './components/viewer-controls/viewer-controls.component';
import { ViewerOptionsComponent } from './components/viewer-options/viewer-options.component';
import { ViewerStatsComponent } from './components/viewer-stats/viewer-stats.component';

import { Viewer3DService } from './services/viewer-3d.service';
import { PotreeLoaderService } from './services/potree-loader.service';
import { environment } from '../../../../environments/environment';

import {
  ProjectInfo,
  ViewMode,
  DisplayType,
  ColorMode,
  ViewerStats
} from './models/project-3d.model';
import { ViewerMode } from './services/viewer-3d.service';
import { PotreeConversionStatus } from './services/potree-loader.service';

interface ProcessingTaskDto {
  id: number;
  projectId: number;
  name: string;
  status: string;
  progress: number;
  nodeodmTaskId: string;
}

interface ProjectApiResponse {
  id: number;
  name: string;
  description: string;
}

@Component({
  selector: 'app-project-3d',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ViewerControlsComponent,
    ViewerOptionsComponent,
    ViewerStatsComponent
  ],
  providers: [Viewer3DService, PotreeLoaderService],
  templateUrl: './project-3d.component.html',
  styleUrls: ['./project-3d.component.scss']
})
export class Project3DComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('viewerContainer') viewerContainer!: ElementRef;
  @ViewChild('canvas3D') canvas!: ElementRef<HTMLCanvasElement>;

  private route = inject(ActivatedRoute);
  private http = inject(HttpClient);
  private viewer3DService = inject(Viewer3DService);

  projectId!: number;
  project = signal<ProjectInfo | null>(null);

  isLoading = signal(true);
  loadProgress = signal(0);
  has3DData = signal(true);
  errorMessage = signal<string | null>(null);

  isFullscreen = signal(false);
  viewMode = signal<ViewMode>('orbit');
  displayType = signal<DisplayType>('pointcloud');
  colorMode = signal<ColorMode>('elevation');
  pointSize = signal(3);
  showGrid = signal(true);
  showAxes = signal(true);

  stats = signal<ViewerStats>({ points: 0, fps: 0, memory: 0 });

  viewerMode = signal<ViewerMode>('mesh');
  potreeStatus = signal<PotreeConversionStatus>('idle');

  private viewerReady = false;
  private pendingLoad: { projectId: number; taskId: number } | null = null;

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.projectId = +params['id'];
      this.loadProjectAndTask();
    });

    this.viewer3DService.getLoadProgress().subscribe(progress => {
      this.loadProgress.set(progress);
      if (progress >= 100) {
        setTimeout(() => this.isLoading.set(false), 400);
      }
    });

    this.viewer3DService.getStats().subscribe(stats => this.stats.set(stats));
    this.viewer3DService.potree.conversionStatus.subscribe(s => this.potreeStatus.set(s));
  }

  ngAfterViewInit(): void {
    this.viewer3DService.initViewer(this.canvas);
    this.viewerReady = true;

    if (this.pendingLoad) {
      const { projectId, taskId } = this.pendingLoad;
      this.pendingLoad = null;
      this.triggerLoad(projectId, taskId);
    }
  }

  ngOnDestroy(): void {
    this.viewer3DService.destroy();
  }

  private async loadProjectAndTask(): Promise<void> {
    try {
      const [projectResp, tasksResp] = await Promise.all([
        firstValueFrom(
          this.http.get<ProjectApiResponse>(`${environment.apiUrl}/projects/${this.projectId}`)
        ),
        firstValueFrom(
          this.http.get<ProcessingTaskDto[]>(`${environment.apiUrl}/projects/${this.projectId}/tasks`)
        )
      ]);

      const completedTask = tasksResp.find(t =>
        t.status === 'COMPLETED' || t.status === 'COMPLETED_WITH_WARNINGS'
      );

      if (!completedTask) {
        this.has3DData.set(false);
        this.isLoading.set(false);
        return;
      }

      this.project.set({
        id: this.projectId,
        taskId: completedTask.id,
        name: projectResp.name,
        description: projectResp.description ?? '',
        status: completedTask.status
      });

      if (this.viewerReady) {
        this.triggerLoad(this.projectId, completedTask.id);
      } else {
        this.pendingLoad = { projectId: this.projectId, taskId: completedTask.id };
      }
    } catch (err) {
      console.error('[3D] Erro ao carregar projeto/task:', err);
      this.errorMessage.set('Erro ao carregar dados do projeto.');
      this.has3DData.set(false);
      this.isLoading.set(false);
    }
  }

  private async triggerLoad(projectId: number, taskId: number): Promise<void> {
    try {
      await this.viewer3DService.loadMesh(projectId, taskId);
    } catch (err: any) {
      console.error('[3D] Erro ao carregar mesh:', err);
      this.errorMessage.set(err?.message ?? 'Erro ao carregar modelo 3D.');
      this.has3DData.set(false);
      this.isLoading.set(false);
    }
  }

  onViewModeChange(mode: ViewMode): void {
    this.viewMode.set(mode);
  }

  onResetCamera(): void {
    this.viewer3DService.reset();
  }

  onTakeScreenshot(): void {
    const dataUrl = this.viewer3DService.screenshot();
    if (!dataUrl) return;
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = `viewer3d_projeto${this.projectId}.png`;
    a.click();
  }

  onToggleFullscreen(): void {
    const container = this.viewerContainer.nativeElement;
    if (!this.isFullscreen()) {
      container.requestFullscreen?.();
      this.isFullscreen.set(true);
    } else {
      document.exitFullscreen?.();
      this.isFullscreen.set(false);
    }
  }

  onDisplayTypeChange(type: DisplayType): void {
    this.displayType.set(type);
  }

  async switchToPointCloud(): Promise<void> {
    const proj = this.project();
    if (!proj || this.viewerMode() === 'pointcloud') return;
    this.viewerMode.set('pointcloud');
    this.isLoading.set(true);
    this.loadProgress.set(0);
    try {
      await this.viewer3DService.loadPointCloudPotree(proj.id, proj.taskId);
    } catch (err: any) {
      this.errorMessage.set(err?.message ?? 'Erro ao carregar nuvem de pontos.');
      this.viewerMode.set('mesh');
      this.isLoading.set(false);
    }
  }

  switchToMesh(): void {
    if (this.viewerMode() === 'mesh') return;
    this.viewerMode.set('mesh');
    this.isLoading.set(true);
    this.loadProgress.set(0);
    const proj = this.project();
    if (proj) {
      this.triggerLoad(proj.id, proj.taskId);
    }
  }

  onColorModeChange(mode: ColorMode): void {
    this.colorMode.set(mode);
    this.viewer3DService.setColorMode(mode);
  }

  onPointSizeChange(size: number): void {
    this.pointSize.set(size);
  }

  onShowGridChange(show: boolean): void {
    this.showGrid.set(show);
    this.viewer3DService.setShowGrid(show);
  }

  onShowAxesChange(show: boolean): void {
    this.showAxes.set(show);
    this.viewer3DService.setShowAxes(show);
  }
}
