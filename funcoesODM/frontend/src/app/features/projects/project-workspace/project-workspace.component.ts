import { Component, OnInit, OnDestroy, signal, computed, inject, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, distinctUntilChanged, switchMap, tap, catchError, of, interval, forkJoin, finalize } from 'rxjs';

import { ProjectService } from '../services/project.service';
import { ImageUploadService } from '../services/image-upload.service';
import { ChunkService } from '../services/chunk.service';
import { Project, ProjectImage, Chunk, ChunkStatus } from '../models/project.model';

import { ButtonComponent } from '../../../shared/components/button/button.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { ResultsViewerComponent } from '../components/results-viewer/results-viewer.component';

// Sub-components
import { PhotosTabComponent } from './components/photos-tab/photos-tab.component';
import { OptionsTabComponent, ChunkOptions } from './components/options-tab/options-tab.component';
import { ProcessTabComponent } from './components/process-tab/process-tab.component';
import { ResultsTabComponent } from './components/results-tab/results-tab.component';
import { GcpEditorComponent } from './components/gcp-editor/gcp-editor.component';

// Constants
import { ODM_DEFAULT_OPTIONS, ODM_OPTION_CATEGORIES, QUALITY_LEVELS } from './constants/odm-options.const';

@Component({
  selector: 'app-project-workspace',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    ButtonComponent,
    LoadingSpinnerComponent,
    ResultsViewerComponent,
    PhotosTabComponent,
    OptionsTabComponent,
    ProcessTabComponent,
    ResultsTabComponent,
    GcpEditorComponent
  ],
  templateUrl: './project-workspace.component.html',
  styleUrls: ['./project-workspace.component.scss']
})
export class ProjectWorkspaceComponent implements OnInit, OnDestroy {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly projectService = inject(ProjectService);
  private readonly uploadService = inject(ImageUploadService);
  private readonly chunkService = inject(ChunkService);
  private readonly destroyRef = inject(DestroyRef);

  // ==================== STATE ====================
  
  // Project state
  project = signal<Project | null>(null);
  projectName = signal('');
  saveStatus = signal<'idle' | 'saving' | 'saved' | 'error'>('idle');
  initialLoading = signal(true);
  isNewProject = false;
  errorSignal = signal<string | null>(null);

  // Chunks state
  chunks = signal<Chunk[]>([]);
  selectedChunk = signal<Chunk | null>(null);
  activeTab = signal<'photos' | 'options' | 'process' | 'results'>('photos');

  // Chunk menu
  showChunkMenu = signal(false);
  menuChunk = signal<Chunk | null>(null);
  menuPosition = { x: 0, y: 0 };

  // Chunk editing
  chunkNameEdit = '';
  chunkDescriptionEdit = '';

  // Images state
  projectImages = signal<ProjectImage[]>([]);
  chunkImages = signal<ProjectImage[]>([]);
  selectedChunkImages = signal<number[]>([]);

  // Upload state
  isUploading = signal(false);
  isDragOver = signal(false);
  uploadProgress = signal<{ loaded: number; total: number; percentage: number } | null>(null);
  uploadingFiles = signal<File[]>([]);
  readonly maxFileSizeMb = signal(100);
  readonly maxRequestSizeMb = signal(500);
  readonly hardMaxFileSizeMb = signal(5120);
  readonly hardMaxRequestSizeMb = signal(20480);

  // Image selection from project
  showImageSelector = signal(false);
  selectedProjectImages = signal<number[]>([]);

  // Processing options
  chunkOptions: ChunkOptions = {
    crs: 'EPSG:4326',
    orthophoto: true,
    dsm: true,
    dtm: false,
    pointCloud: false,
    mesh: false,
    quality: 'medium'
  };
  
  chunkAdvancedOptions: Record<string, any> = { ...ODM_DEFAULT_OPTIONS };
  readonly qualityLevels = QUALITY_LEVELS;
  readonly advancedOptionCategories = ODM_OPTION_CATEGORIES;
  showAdvancedOptions = signal(false);

  /** Arquivo GCP selecionado pelo usuario para upload junto ao processamento */
  gcpFile = signal<File | null>(null);

  /** Controla visibilidade do editor visual de GCP */
  showGcpEditor = signal(false);

  // Auto-save subject
  private saveSubject = new Subject<{ name: string }>();

  // ==================== COMPUTED ====================

  totalImages = computed(() => this.projectImages().length);

  projectStatus = computed(() => {
    const allChunks = this.chunks();
    if (allChunks.length === 0) return 'pending';
    if (allChunks.some(c => c.status === 'RUNNING')) return 'processing';
    if (allChunks.every(c => c.status === 'COMPLETED')) return 'completed';
    return 'pending';
  });

  projectImagesNotInChunk = computed(() => {
    const chunkImgIds = new Set(this.chunkImages().map(img => img.id));
    return this.projectImages().filter(img => !chunkImgIds.has(img.id));
  });

  chunkOutputs = computed(() => {
    const chunk = this.selectedChunk();
    if (!chunk || !chunk.outputs) return {};
    
    if (typeof chunk.outputs === 'string') {
      try {
        return JSON.parse(chunk.outputs);
      } catch (e) {
        console.error('Failed to parse chunk outputs:', e);
        return {};
      }
    }
    
    return chunk.outputs;
  });

  canProcessAll = computed(() => {
    return this.chunks().some(c => this.canProcessChunk(c));
  });

  // ==================== CONSTRUCTOR ====================

  constructor() {
    // Setup auto-save
    this.saveSubject.pipe(
      debounceTime(1000),
      distinctUntilChanged((prev, curr) => prev.name === curr.name),
      tap(() => this.saveStatus.set('saving')),
      switchMap(data => {
        const project = this.project();
        if (!project) return of(null);
        return this.projectService.updateProject(project.id, data).pipe(
          catchError(err => {
            console.error('Auto-save failed:', err);
            this.saveStatus.set('error');
            return of(null);
          })
        );
      }),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(result => {
      if (result) {
        this.saveStatus.set('saved');
        setTimeout(() => {
          if (this.saveStatus() === 'saved') this.saveStatus.set('idle');
        }, 2000);
      }
    });

    // Subscribe to upload progress
    this.uploadService.uploadProgress$.pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(progress => this.uploadProgress.set(progress));

    this.uploadService.uploading$.pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(uploading => this.isUploading.set(uploading));
  }

  // ==================== LIFECYCLE ====================

  ngOnInit(): void {
    // Carregar limites de upload do usuário
    this.loadUploadLimits();

    this.route.url.pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(() => this.handleRouteChange());
  }

  ngOnDestroy(): void {}

  private handleRouteChange(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const urlSegment = this.route.snapshot.url[0]?.path;

    this.resetWorkspaceState();

    // Verifica se está na rota /projects/new (sem parâmetro id)
    if (urlSegment === 'new' || id === 'new') {
      this.isNewProject = true;
      this.createNewProject();
    } else if (id) {
      this.loadProject(parseInt(id, 10));
    } else {
      // Fallback: se não há id nem rota 'new', volta para lista
      this.initialLoading.set(false);
      this.router.navigate(['/projects']);
    }
  }

  private resetWorkspaceState(): void {
    this.isNewProject = false;
    this.project.set(null);
    this.projectName.set('');
    this.saveStatus.set('idle');
    this.initialLoading.set(true);
    this.errorSignal.set(null);
    this.chunks.set([]);
    this.selectedChunk.set(null);
    this.projectImages.set([]);
    this.chunkImages.set([]);
    this.selectedChunkImages.set([]);
    this.showImageSelector.set(false);
    this.selectedProjectImages.set([]);
    this.uploadProgress.set(null);
    this.uploadingFiles.set([]);
    this.gcpFile.set(null);
    this.showGcpEditor.set(false);
  }

  // ==================== PROJECT ====================

  private createNewProject(): void {
    this.projectService.createProject({
      name: 'Novo Projeto',
      description: ''
    }).pipe(
      finalize(() => this.initialLoading.set(false)),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: (project) => {
        this.project.set(project);
        this.projectName.set(project.name);
        this.router.navigate(['/projects', project.id], { replaceUrl: true });
        this.createNewChunk();
      },
      error: (err) => {
        console.error('Failed to create project:', err);
        if (this.errorSignal) {
          this.errorSignal.set('Erro ao criar projeto. Tente novamente.');
        }
        this.router.navigate(['/projects']);
      }
    });
  }

  private loadProject(id: number): void {
    this.projectService.getProject(id).pipe(
      finalize(() => {
        // Sempre desativa loading, mesmo em caso de erro
        this.initialLoading.set(false);
      }),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: (project) => {
        if (project) {
          this.project.set(project);
          this.projectName.set(project.name);
          this.loadProjectData(id);
        } else {
          console.warn(`Project ${id} not found`);
          this.router.navigate(['/projects']);
        }
      },
      error: (err) => {
        console.error('Failed to load project:', err);
        this.router.navigate(['/projects']);
      }
    });
  }

  private loadProjectData(projectId: number): void {
    forkJoin({
      images: this.uploadService.getProjectImages(projectId).pipe(
        catchError(err => {
          console.error('Failed to load images:', err);
          return of([]);
        })
      ),
      chunks: this.chunkService.getChunks(projectId).pipe(
        catchError(err => {
          console.error('Failed to load chunks:', err);
          return of([]);
        })
      )
    }).subscribe({
      next: ({ images, chunks }) => {
        this.projectImages.set(images);
        
        if (chunks.length === 0 && images.length > 0) {
          this.ensureProjectHasChunks(projectId);
        } else {
          this.chunks.set(chunks);
          if (chunks.length > 0) {
            this.selectChunk(chunks[0]);
          }
          chunks.filter(c => c.status === 'RUNNING' || c.status === 'QUEUED')
                .forEach(c => this.pollChunkStatus(c.id));
        }
      }
    });
  }

  private ensureProjectHasChunks(projectId: number): void {
    this.chunkService.ensureProjectHasChunks(projectId).subscribe({
      next: (chunks) => {
        this.chunks.set(chunks);
        if (chunks.length > 0) {
          this.selectChunk(chunks[0]);
        }
      },
      error: (err) => {
        console.error('Failed to ensure chunks:', err);
        this.chunks.set([]);
      }
    });
  }

  onNameChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.projectName.set(value);
    this.saveSubject.next({ name: value });
  }

  onNameBlur(): void {
    this.saveSubject.next({ name: this.projectName() });
  }

  getProjectStatusLabel(): string {
    const status = this.projectStatus();
    return status === 'processing' ? 'Processando' : 
           status === 'completed' ? 'Concluído' : 'Pendente';
  }

  // ==================== UPLOAD LIMITS ====================

  private loadUploadLimits(): void {
    this.uploadService.getUploadLimits().pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: (limits) => {
        this.maxFileSizeMb.set(limits.maxFileSizeMb);
        this.maxRequestSizeMb.set(limits.maxRequestSizeMb);
        this.hardMaxFileSizeMb.set(limits.hardMaxFileSizeMb);
        this.hardMaxRequestSizeMb.set(limits.hardMaxRequestSizeMb);
      },
      error: (err) => {
        console.error('Failed to load upload limits:', err);
      }
    });
  }

  handleSaveLimits(limits: { maxFileSizeMb: number; maxRequestSizeMb: number }): void {
    this.uploadService.updateUploadLimits(limits).pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: (updatedLimits) => {
        this.maxFileSizeMb.set(updatedLimits.maxFileSizeMb);
        this.maxRequestSizeMb.set(updatedLimits.maxRequestSizeMb);
        console.log('Upload limits updated successfully');
      },
      error: (err) => {
        console.error('Failed to update upload limits:', err);
      }
    });
  }

  // ==================== CHUNKS ====================

  createNewChunk(): void {
    const project = this.project();
    if (!project) return;

    const chunkNumber = this.chunks().length + 1;
    this.chunkService.createChunk(project.id, {
      name: `Chunk ${chunkNumber}`,
      description: ''
    }).subscribe({
      next: (chunk) => {
        this.chunks.update(list => [...list, chunk]);
        this.selectChunk(chunk);
      },
      error: (err) => console.error('Failed to create chunk:', err)
    });
  }

  selectChunk(chunk: Chunk): void {
    this.selectedChunk.set(chunk);
    this.selectedChunkImages.set([]);
    this.chunkNameEdit = chunk.name;
    this.chunkDescriptionEdit = chunk.description || '';
    this.setActiveTab('photos');
    this.loadChunkImages(chunk);
  }

  private loadChunkImages(chunk: Chunk): void {
    const project = this.project();
    if (!project) return;

    this.chunkService.getChunkImages(project.id, chunk.id).subscribe({
      next: (images) => this.chunkImages.set(images),
      error: (err) => console.error('Failed to load chunk images:', err)
    });
  }

  onChunkNameChange(event: Event): void {
    this.chunkNameEdit = (event.target as HTMLInputElement).value;
  }

  onChunkDescriptionChange(event: Event): void {
    this.chunkDescriptionEdit = (event.target as HTMLTextAreaElement).value;
  }

  saveChunkName(): void {
    const chunk = this.selectedChunk();
    const project = this.project();
    if (!chunk || !project || chunk.name === this.chunkNameEdit) return;

    this.chunkService.updateChunk(project.id, chunk.id, { name: this.chunkNameEdit }).subscribe({
      next: (updated) => {
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
      }
    });
  }

  saveChunkDescription(): void {
    const chunk = this.selectedChunk();
    const project = this.project();
    if (!chunk || !project) return;

    this.chunkService.updateChunk(project.id, chunk.id, { description: this.chunkDescriptionEdit }).subscribe({
      next: (updated) => {
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
      }
    });
  }

  deleteCurrentChunk(): void {
    const chunk = this.selectedChunk();
    if (chunk) this.deleteChunk(chunk);
  }

  deleteChunk(chunk: Chunk): void {
    const project = this.project();
    if (!project) return;

    if (!confirm(`Excluir chunk "${chunk.name}"?`)) return;

    this.chunkService.deleteChunk(project.id, chunk.id).subscribe({
      next: () => {
        this.chunks.update(list => list.filter(c => c.id !== chunk.id));
        if (this.selectedChunk()?.id === chunk.id) {
          const remaining = this.chunks();
          this.selectedChunk.set(remaining.length > 0 ? remaining[0] : null);
          if (remaining.length > 0) this.loadChunkImages(remaining[0]);
        }
        this.closeChunkMenu();
      }
    });
  }

  getChunkIcon(status: ChunkStatus): string {
    const icons: Record<ChunkStatus, string> = {
      'EMPTY': '⚪',
      'READY': '🔵',
      'QUEUED': '🟡',
      'RUNNING': '🟠',
      'COMPLETED': '🟢',
      'FAILED': '🔴',
      'CANCELED': '⚫'
    };
    return icons[status] || '⚪';
  }

  getChunkStatusLabel(status: ChunkStatus): string {
    const labels: Record<ChunkStatus, string> = {
      'EMPTY': 'Vazio',
      'READY': 'Pronto',
      'QUEUED': 'Na Fila',
      'RUNNING': 'Processando',
      'COMPLETED': 'Concluído',
      'FAILED': 'Falhou',
      'CANCELED': 'Cancelado'
    };
    return labels[status] || status;
  }

  // ==================== CHUNK CONTEXT MENU ====================

  openChunkMenu(event: MouseEvent, chunk: Chunk): void {
    event.stopPropagation();
    this.menuChunk.set(chunk);
    this.menuPosition = { x: event.clientX, y: event.clientY };
    this.showChunkMenu.set(true);
  }

  closeChunkMenu(): void {
    this.showChunkMenu.set(false);
    this.menuChunk.set(null);
  }

  renameChunk(): void {
    const chunk = this.menuChunk();
    if (chunk) {
      this.selectChunk(chunk);
      this.setActiveTab('options');
    }
    this.closeChunkMenu();
  }

  duplicateChunk(): void {
    // TODO: Implement chunk duplication
    this.closeChunkMenu();
  }

  // ==================== IMAGES ====================

  addImageToChunk(imageId: number): void {
    const chunk = this.selectedChunk();
    const project = this.project();
    if (!chunk || !project) return;

    this.chunkService.addImagesToChunk(project.id, chunk.id, [imageId]).subscribe({
      next: (updated) => {
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
        this.loadChunkImages(updated);
      }
    });
  }

  addAllImagesToChunk(): void {
    const chunk = this.selectedChunk();
    const project = this.project();
    const images = this.projectImagesNotInChunk();
    if (!chunk || !project || images.length === 0) return;

    const imageIds = images.map(img => img.id);
    this.chunkService.addImagesToChunk(project.id, chunk.id, imageIds).subscribe({
      next: (updated) => {
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
        this.loadChunkImages(updated);
      }
    });
  }

  removeSelectedFromChunk(): void {
    const chunk = this.selectedChunk();
    const project = this.project();
    const selected = this.selectedChunkImages();
    if (!chunk || !project || selected.length === 0) return;

    this.chunkService.removeImagesFromChunk(project.id, chunk.id, selected).subscribe({
      next: (updated) => {
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
        this.selectedChunkImages.set([]);
        this.loadChunkImages(updated);
      }
    });
  }

  isChunkImageSelected(imageId: number): boolean {
    return this.selectedChunkImages().includes(imageId);
  }

  toggleChunkImageSelection(imageId: number): void {
    this.selectedChunkImages.update(list => {
      if (list.includes(imageId)) {
        return list.filter(id => id !== imageId);
      }
      return [...list, imageId];
    });
  }

  getImageThumbnail(image: ProjectImage): string {
    const project = this.project();
    if (!project) return '';
    return `/api/v1/projects/${project.id}/images/${image.id}/thumbnail`;
  }

  // ==================== UPLOAD ====================

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    const files = event.dataTransfer?.files;
    if (files) this.uploadFiles(Array.from(files));
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      this.uploadFiles(Array.from(input.files));
      input.value = '';
    }
  }

  private uploadFiles(files: File[]): void {
    const project = this.project();
    const chunk = this.selectedChunk();
    if (!project) return;

    const imageFiles = files.filter(f => 
      f.type.startsWith('image/') || 
      f.name.toLowerCase().match(/\.(jpg|jpeg|png|tiff|tif)$/)
    );

    if (imageFiles.length === 0) return;

    this.uploadingFiles.set(imageFiles);

    this.uploadService.uploadImages(project.id, imageFiles).subscribe({
      next: (response) => {
        this.projectImages.update(list => [...list, ...response.images]);
        this.uploadingFiles.set([]);
        
        // Auto-add to current chunk if one is selected
        if (chunk && response.images.length > 0) {
          const newIds = response.images.map(img => img.id);
          this.chunkService.addImagesToChunk(project.id, chunk.id, newIds).subscribe({
            next: (updated) => {
              this.selectedChunk.set(updated);
              this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
              this.loadChunkImages(updated);
            }
          });
        }
      },
      error: (err) => {
        console.error('Upload failed:', err);
        this.uploadingFiles.set([]);
      }
    });
  }

  // ==================== ADD EXISTING IMAGES TO CHUNK ====================

  openImageSelector(): void {
    this.showImageSelector.set(true);
    this.selectedProjectImages.set([]);
  }

  closeImageSelector(): void {
    this.showImageSelector.set(false);
    this.selectedProjectImages.set([]);
  }

  toggleProjectImageSelection(imageId: number): void {
    this.selectedProjectImages.update(selected => {
      const index = selected.indexOf(imageId);
      if (index > -1) {
        return selected.filter(id => id !== imageId);
      } else {
        return [...selected, imageId];
      }
    });
  }

  selectAllProjectImages(): void {
    const availableImages = this.projectImagesNotInChunk();
    this.selectedProjectImages.set(availableImages.map(img => img.id));
  }

  deselectAllProjectImages(): void {
    this.selectedProjectImages.set([]);
  }

  addSelectedImagesToChunk(): void {
    const project = this.project();
    const chunk = this.selectedChunk();
    const selectedIds = this.selectedProjectImages();

    if (!project || !chunk || selectedIds.length === 0) return;

    this.chunkService.addImagesToChunk(project.id, chunk.id, selectedIds).subscribe({
      next: (updated) => {
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
        this.loadChunkImages(updated);
        this.closeImageSelector();
      },
      error: (err) => {
        console.error('Failed to add images to chunk:', err);
        alert('Erro ao adicionar imagens ao chunk: ' + (err.error?.message || err.message));
      }
    });
  }

  // ==================== PROCESSING ====================

  canProcessChunk(chunk: Chunk): boolean {
    return chunk.imageCount >= 3 && (chunk.status === 'READY' || chunk.status === 'FAILED');
  }

  processChunk(chunk: Chunk): void {
    const project = this.project();
    if (!project || !this.canProcessChunk(chunk)) return;

    const options: Record<string, any> = this.buildProcessingOptions();

    console.log('Processing chunk:', chunk.id, 'with options:', options);

    this.chunkService.processChunk(project.id, chunk.id, options, this.gcpFile()).subscribe({
      next: (updated) => {
        console.log('Chunk processing started:', updated);
        this.selectedChunk.set(updated);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
        this.setActiveTab('results');
        this.pollChunkStatus(chunk.id);
      },
      error: (err) => {
        console.error('Failed to start processing:', err);
        alert('Erro ao iniciar processamento: ' + (err.error?.message || err.message));
      }
    });

    this.closeChunkMenu();
  }

  processAllChunks(): void {
    const processable = this.chunks().filter(c => this.canProcessChunk(c));
    processable.forEach(chunk => this.processChunk(chunk));
  }

  retryingChunkIds = new Set<number>();

  retryChunk(chunk: Chunk): void {
    const project = this.project();
    if (!project || this.retryingChunkIds.has(chunk.id)) return;

    this.retryingChunkIds.add(chunk.id);
    this.chunkService.retryChunk(project.id, chunk.id).subscribe({
      next: (updated) => {
        this.retryingChunkIds.delete(chunk.id);
        this.chunks.update(list => list.map(c => c.id === updated.id ? updated : c));
        if (this.selectedChunk()?.id === updated.id) {
          this.selectedChunk.set(updated);
        }
        this.pollChunkStatus(updated.id);
        this.setActiveTab('results');
      },
      error: (err) => {
        this.retryingChunkIds.delete(chunk.id);
        console.error('Erro ao tentar novamente:', err);
      }
    });
  }

  isRetrying(chunkId: number): boolean {
    return this.retryingChunkIds.has(chunkId);
  }

  resetAdvancedOptions(): void {
    this.chunkAdvancedOptions = { ...ODM_DEFAULT_OPTIONS };
    this.advancedOptionCategories.forEach(cat => cat.expanded = false);
  }

  onGcpFileSelected(event: { key: string; file: File | null }): void {
    if (event.key === 'gcp') {
      this.gcpFile.set(event.file);
    }
  }

  openGcpEditor(): void {
    this.showGcpEditor.set(true);
  }

  onGcpEditorReady(file: File): void {
    this.gcpFile.set(file);
    // Reflete no gcpFileMap do process-tab via Input binding nao e direta;
    // o process-tab vai exibir o estado atraves do gcpFile signal do workspace
    this.showGcpEditor.set(false);
  }

  private buildProcessingOptions(): Record<string, any> {
    const opts: Record<string, any> = {};
    
    // Quality mapping
    switch (this.chunkOptions.quality) {
      case 'fast':
        opts['pc-quality'] = 'lowest';
        opts['feature-quality'] = 'low';
        opts['min-num-features'] = 4000;
        opts['mesh-octree-depth'] = 8;
        break;
      case 'medium':
        opts['pc-quality'] = 'low';
        opts['feature-quality'] = 'medium';
        opts['min-num-features'] = 8000;
        opts['mesh-octree-depth'] = 10;
        break;
      case 'high':
        opts['pc-quality'] = 'medium';
        opts['feature-quality'] = 'high';
        opts['min-num-features'] = 12000;
        opts['mesh-octree-depth'] = 11;
        break;
      case 'ultra':
        opts['pc-quality'] = 'high';
        opts['feature-quality'] = 'ultra';
        opts['min-num-features'] = 20000;
        opts['mesh-octree-depth'] = 12;
        break;
    }
    
    // Basic output options
    opts['dsm'] = this.chunkOptions.dsm;
    opts['dtm'] = this.chunkOptions.dtm;
    opts['pc-las'] = this.chunkOptions.pointCloud;
    opts['use-3dmesh'] = this.chunkOptions.mesh;
    
    // Merge advanced options (filter defaults to avoid unnecessary parameters)
    for (const [key, value] of Object.entries(this.chunkAdvancedOptions)) {
      // Skip empty strings
      if (value === '' || value === null || value === undefined) continue;

      // 'gcp' e tratado como upload de arquivo — nao enviar como string de opcao
      if (key === 'gcp') continue;
      
      // Skip options already set by quality preset
      if (['pc-quality', 'feature-quality', 'min-num-features', 'mesh-octree-depth'].includes(key)) continue;
      
      // Skip boolean false values (NodeODM uses defaults)
      if (typeof value === 'boolean' && !value) continue;
      
      // Skip numeric defaults that match NodeODM defaults
      const numericDefaults: Record<string, number> = {
        'matcher-neighbors': 0,
        'matcher-order': 0,
        'pc-filter': 5,
        'pc-sample': 0,
        'dem-gapfill-steps': 3,
        'dem-resolution': 5,
        'dem-decimation': 1,
        'smrf-scalar': 1.25,
        'smrf-slope': 0.15,
        'smrf-threshold': 0.5,
        'smrf-window': 18,
        'orthophoto-resolution': 5,
        'gps-accuracy': 3,
        'gps-z-offset': 0,
        'crop': 3,
        'auto-boundary-distance': 0,
        'rolling-shutter-readout': 0,
        'max-concurrency': 0,
        'split': 999999,
        'split-overlap': 150,
        'video-limit': 500,
        'video-resolution': 4000,
        'mesh-size': 200000
      };
      
      if (key in numericDefaults && value === numericDefaults[key]) continue;
      
      // Skip string defaults that match NodeODM defaults
      const stringDefaults: Record<string, string> = {
        'feature-type': 'sift',
        'matcher-type': 'flann',
        'camera-lens': 'auto',
        'radiometric-calibration': 'none',
        'sfm-algorithm': 'incremental',
        'orthophoto-compression': 'DEFLATE',
        'merge': 'all',
        'primary-band': 'auto',
        'end-with': 'odm_postprocess'
      };
      
      if (key in stringDefaults && value === stringDefaults[key]) continue;
      
      opts[key] = value;
    }
    
    return opts;
  }

  private pollChunkStatus(chunkId: number): void {
    const project = this.project();
    if (!project) return;

    const pollInterval = interval(5000).pipe(
      takeUntilDestroyed(this.destroyRef),
      switchMap(() => this.chunkService.getChunk(project.id, chunkId)),
      tap(chunk => {
        this.chunks.update(list => list.map(c => c.id === chunk.id ? chunk : c));
        if (this.selectedChunk()?.id === chunk.id) {
          this.selectedChunk.set(chunk);
        }
      })
    ).subscribe({
      next: (chunk) => {
        if (chunk.status === 'COMPLETED' || chunk.status === 'FAILED' || chunk.status === 'CANCELED') {
          pollInterval.unsubscribe();
          if (chunk.status === 'COMPLETED') {
            this.setActiveTab('results');
          }
        }
      }
    });
  }

  getSelectedOutputsCount(): number {
    let count = 0;
    if (this.chunkOptions.orthophoto) count++;
    if (this.chunkOptions.dsm) count++;
    if (this.chunkOptions.dtm) count++;
    if (this.chunkOptions.pointCloud) count++;
    if (this.chunkOptions.mesh) count++;
    return count;
  }

  // ==================== UI ====================

  setActiveTab(tab: 'photos' | 'options' | 'process' | 'results'): void {
    this.activeTab.set(tab);
  }

  // ==================== HELPERS ====================

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  formatTotalSize(): string {
    const total = this.projectImages().reduce((sum, img) => sum + img.fileSize, 0);
    return this.formatFileSize(total);
  }

  formatTime(seconds: number | undefined): string {
    if (!seconds) return '-';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }
}
