import { Component, OnInit, signal, Input, ViewChild, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { switchMap, tap } from 'rxjs/operators';
import { ProjectService } from '../services/project.service';
import { Project, ProjectTask, ImageUploadResponse } from '../models/project.model';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { ImageUploaderComponent } from '../components/image-uploader/image-uploader.component';
import { ImageGalleryComponent } from '../components/image-gallery/image-gallery.component';
import { TaskListComponent } from '../components/task-list/task-list.component';
import { CreateTaskDialogComponent } from '../components/create-task-dialog/create-task-dialog.component.fixed';
import { ResultsViewerComponent } from '../components/results-viewer/results-viewer.component';
import { ProcessingTask } from '../services/task.service';

@Component({
  selector: 'app-project-detail',
  standalone: true,
  imports: [
    CommonModule, 
    RouterLink, 
    ButtonComponent, 
    LoadingSpinnerComponent, 
    ImageUploaderComponent, 
    ImageGalleryComponent,
    TaskListComponent,
    CreateTaskDialogComponent,
    ResultsViewerComponent
  ],
  template: `
    <div class="project-workspace">
      <app-loading-spinner *ngIf="isLoading()" message="Carregando projeto..."></app-loading-spinner>

      <ng-container *ngIf="!isLoading() && project()">
        <!-- Top Bar -->
        <header class="workspace-header">
          <div class="header-left">
            <a routerLink="/projects" class="back-btn" title="Voltar">←</a>
            <div class="project-info">
              <h1>{{ project()!.name }}</h1>
              <span class="status-badge" [class]="project()!.status.toLowerCase()">
                {{ getStatusLabel(project()!.status) }}
              </span>
            </div>
          </div>
          <div class="header-actions">
            <app-button variant="outline" size="sm" (click)="openCreateTaskDialog()">
              + Processar
            </app-button>
          </div>
        </header>

        <div class="workspace-body">
          <!-- Sidebar (Workspace Pane) -->
          <aside class="workspace-sidebar">
            <div class="sidebar-section">
              <div class="sidebar-header">Workspace</div>
              
              <!-- Photos Item -->
              <div 
                class="sidebar-item" 
                [class.selected]="viewMode() === 'photos'"
                (click)="setViewMode('photos')"
              >
                <span class="item-icon">📷</span>
                <span class="item-name">Fotos ({{ project()!.imageCount }})</span>
              </div>

              <!-- Chunks / Tasks -->
              <div class="chunks-list">
                <app-task-list 
                  #taskList
                  [projectId]="project()!.id"
                  mode="compact"
                  (taskSelected)="onTaskSelected($event)"
                />
              </div>
            </div>
          </aside>

          <!-- Main Content Area -->
          <main class="workspace-main">
            @if (viewMode() === 'photos') {
              <div class="photos-view">
                <div class="view-toolbar">
                  <h2>Galeria de Imagens</h2>
                  <div class="toolbar-actions">
                    <!-- Image Upload is integrated here -->
                  </div>
                </div>
                
                <div class="photos-content">
                  <app-image-uploader 
                    [projectId]="project()!.id"
                    (uploadComplete)="onUploadComplete($event)"
                  />
                  <div class="gallery-container">
                    <app-image-gallery 
                      #imageGallery
                      [projectId]="project()!.id"
                      (imagesChanged)="onImagesChanged()"
                    />
                  </div>
                </div>
              </div>
            } @else if (viewMode() === 'model') {
              <div class="model-view">
                @if (selectedTask()) {
                  @if (isTaskCompleted(selectedTask()!.status)) {
                    <!-- Results Viewer com todas as abas (Ortofoto, DSM, 3D, Medições, Downloads) -->
                    <app-results-viewer
                      [projectId]="project()!.id"
                      [taskId]="selectedTask()!.id"
                      [nodeodmTaskId]="selectedTask()!.nodeodmTaskId"
                      [outputs]="selectedTask()!.outputs || {}"
                    />
                  } @else {
                    <div class="placeholder-state">
                      <div class="spinner" *ngIf="selectedTask()!.status === 'RUNNING'"></div>
                      <h3>{{ selectedTask()!.name || 'Tarefa #' + selectedTask()!.id }}</h3>
                      <p>Status: {{ getTaskStatusLabel(selectedTask()!.status) }}</p>
                      <p *ngIf="selectedTask()!.status === 'RUNNING'">Progresso: {{ selectedTask()!.progress }}%</p>
                      <p *ngIf="selectedTask()!.status === 'FAILED'" class="error-text">{{ selectedTask()!.errorMessage }}</p>
                    </div>
                  }
                } @else {
                  <div class="placeholder-state">
                    <span class="icon">⬅️</span>
                    <p>Selecione um Chunk (Tarefa) na barra lateral para visualizar</p>
                  </div>
                }
              </div>
            }
          </main>
        </div>
      </ng-container>

      <div *ngIf="!isLoading() && !project()" class="not-found">
        <h2>Projeto não encontrado</h2>
        <app-button routerLink="/projects">Voltar para Projetos</app-button>
      </div>

      <!-- Create Task Dialog -->
      @if (showCreateTaskDialog() && project()) {
        <app-create-task-dialog
          [projectId]="project()!.id"
          (closed)="closeCreateTaskDialog()"
          (created)="onTaskCreated()"
        />
      }
    </div>
  `,
  styles: [`
    .project-workspace {
      height: 100vh;
      display: flex;
      flex-direction: column;
      background: #f9fafb;
      overflow: hidden;
    }

    /* Header */
    .workspace-header {
      height: 48px;
      background: #1e1e1e;
      border-bottom: 1px solid #3d3d3d;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 16px;
      flex-shrink: 0;
      color: #e0e0e0;
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .back-btn {
      text-decoration: none;
      color: #a0a0a0;
      font-weight: bold;
      font-size: 18px;
    }

    .back-btn:hover {
      color: white;
    }

    .project-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .project-info h1 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      color: #e0e0e0;
    }

    .status-badge {
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
    }
    .status-badge.completed { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-badge.processing { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
    .status-badge.pending { background: rgba(107, 114, 128, 0.2); color: #9ca3af; }

    /* Body */
    .workspace-body {
      flex: 1;
      display: flex;
      overflow: hidden;
      background: #121212;
    }

    /* Sidebar */
    .workspace-sidebar {
      width: 280px;
      background: #252526;
      border-right: 1px solid #3d3d3d;
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }

    .sidebar-section {
      flex: 1;
      display: flex;
      flex-direction: column;
    }

    .sidebar-header {
      padding: 8px 12px;
      background: #2d2d2d;
      border-bottom: 1px solid #3d3d3d;
      font-size: 12px;
      font-weight: 600;
      color: #a0a0a0;
      text-transform: uppercase;
    }

    .sidebar-item {
      padding: 8px 12px;
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      font-size: 13px;
      color: #cccccc;
      border-bottom: 1px solid #2d2d2d;
    }

    .sidebar-item:hover {
      background: #2a2d2e;
      color: white;
    }

    .sidebar-item.selected {
      background: #37373d;
      color: white;
      border-left: 3px solid #007acc;
    }

    .chunks-list {
      flex: 1;
      overflow-y: auto;
    }

    /* Main Area */
    .workspace-main {
      flex: 1;
      background: #1e1e1e;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    /* Photos View */
    .photos-view {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 16px;
      overflow-y: auto;
      background: #1e1e1e;
      color: #e0e0e0;
    }

    .view-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .view-toolbar h2 {
      margin: 0;
      font-size: 18px;
      color: #e0e0e0;
    }

    .photos-content {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    /* Model View */
    .model-view {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .placeholder-state {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: #6b7280;
      text-align: center;
      padding: 20px;
    }

    .placeholder-state .icon {
      font-size: 48px;
      margin-bottom: 16px;
      opacity: 0.5;
    }

    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid #e5e7eb;
      border-top-color: #3b82f6;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin-bottom: 16px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .error-text {
      color: #ef4444;
    }

    .not-found {
      padding: 40px;
      text-align: center;
    }
  `]
})
export class ProjectDetailComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  
  @Input() id!: string;
  @ViewChild('imageGallery') imageGallery?: ImageGalleryComponent;
  @ViewChild('taskList') taskList?: TaskListComponent;
  
  isLoading = signal(true);
  project = signal<Project | null>(null);
  showCreateTaskDialog = signal(false);
  
  // View State
  viewMode = signal<'photos' | 'model'>('photos');
  selectedTask = signal<ProcessingTask | null>(null);

  constructor(private projectService: ProjectService) {}

  ngOnInit(): void {
    this.loadProject();
  }

  loadProject(): void {
    const projectId = parseInt(this.id, 10);
    
    this.projectService.loadProjects().pipe(
      switchMap(() => this.projectService.getProject(projectId)),
      tap((project) => {
        this.project.set(project || null);
        this.isLoading.set(false);
      }),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe();
  }

  onUploadComplete(result: ImageUploadResponse): void {
    if (this.imageGallery) {
      this.imageGallery.loadImages();
    }
    if (this.project()) {
      const currentProject = this.project()!;
      this.project.set({
        ...currentProject,
        imageCount: currentProject.imageCount + result.totalUploaded
      });
    }
  }

  onImagesChanged(): void {
    this.loadProject();
  }

  // Task dialog methods
  openCreateTaskDialog(): void {
    this.showCreateTaskDialog.set(true);
  }

  closeCreateTaskDialog(): void {
    this.showCreateTaskDialog.set(false);
  }

  onTaskCreated(): void {
    this.closeCreateTaskDialog();
    if (this.taskList) {
      this.taskList.loadTasks();
    }
    if (this.project()) {
      const currentProject = this.project()!;
      this.project.set({
        ...currentProject,
        taskCount: currentProject.taskCount + 1
      });
    }
  }

  // View Logic
  setViewMode(mode: 'photos' | 'model'): void {
    this.viewMode.set(mode);
    if (mode === 'photos') {
      this.selectedTask.set(null);
    }
  }

  onTaskSelected(task: ProcessingTask): void {
    this.selectedTask.set(task);
    this.viewMode.set('model');
  }

  getStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      'COMPLETED': 'Concluído',
      'PROCESSING': 'Processando',
      'PENDING': 'Pendente',
      'ERROR': 'Erro'
    };
    return labels[status] || status;
  }

  getTaskStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      'COMPLETED': 'Concluído',
      'COMPLETED_WITH_WARNINGS': 'Concluído com Avisos',
      'RUNNING': 'Executando',
      'QUEUED': 'Na Fila',
      'FAILED': 'Falhou',
      'CANCELED': 'Cancelado'
    };
    return labels[status] || status;
  }

  isTaskCompleted(status: string): boolean {
    return status === 'COMPLETED' || status === 'COMPLETED_WITH_WARNINGS' || status?.includes('COMPLETED');
  }
}