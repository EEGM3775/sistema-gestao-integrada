import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ProjectImage, UploadProgress } from '../../../models/project.model';

@Component({
  selector: 'app-photos-tab',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="photos-tab">
      <!-- Upload Zone -->
      <div 
        class="upload-zone"
        [class.dragover]="isDragOver"
        [class.uploading]="isUploading"
        (dragover)="onDragOver($event)"
        (dragleave)="onDragLeave($event)"
        (drop)="onDrop($event)"
      >
        <input
          type="file"
          #fileInput
          multiple
          accept="image/jpeg,image/jpg,image/png,image/tiff"
          (change)="onFilesSelected($event)"
          hidden
        />
        
        @if (!isUploading) {
          <div class="upload-content">
            <div class="upload-icon">📤</div>
            <p>Arraste fotos aqui ou <button class="link-btn" (click)="fileInput.click()">selecione arquivos</button></p>
            <span class="upload-hint">JPG, PNG, TIFF • Máx. {{ maxFileSizeMb }}MB por arquivo</span>
          </div>
        } @else {
          <div class="upload-progress-container">
            <div class="progress-spinner"></div>
            <p>Enviando {{ uploadingFiles.length }} arquivo(s)...</p>
            <div class="progress-bar">
              <div class="progress-fill" [style.width.%]="uploadProgress?.percentage || 0"></div>
            </div>
            <span>{{ uploadProgress?.percentage || 0 }}%</span>
          </div>
        }
      </div>

      <!-- Upload Limits Configuration -->
      <div class="upload-limits-config">
        <div class="config-header">
          <span class="config-title">⚙️ Configurações de Upload</span>
          <button class="btn-save-limits" (click)="onSaveLimits()" [disabled]="isSavingLimits">
            {{ isSavingLimits ? 'Salvando...' : 'Salvar' }}
          </button>
        </div>
        <div class="config-fields">
          <div class="config-field">
            <label for="maxFileSize">Tamanho máximo por arquivo (MB)</label>
            <input 
              id="maxFileSize"
              type="number" 
              [(ngModel)]="localMaxFileSizeMb" 
              min="1" 
              [max]="hardMaxFileSizeMb || 5120"
              class="config-input"
            />
            <small class="config-hint">Máximo permitido: {{ hardMaxFileSizeMb || 5120 }}MB</small>
          </div>
          <div class="config-field">
            <label for="maxRequestSize">Tamanho máximo por envio (MB)</label>
            <input 
              id="maxRequestSize"
              type="number" 
              [(ngModel)]="localMaxRequestSizeMb" 
              min="1"
              [max]="hardMaxRequestSizeMb || 20480"
              class="config-input"
            />
            <small class="config-hint">Máximo permitido: {{ hardMaxRequestSizeMb || 20480 }}MB</small>
          </div>
        </div>
        @if (limitsError) {
          <div class="limits-error">{{ limitsError }}</div>
        }
        @if (limitsSuccess) {
          <div class="limits-success">{{ limitsSuccess }}</div>
        }
      </div>

      <!-- Images from project (to add to chunk) -->
      @if (projectImages.length > 0) {
        <div class="available-images">
          <div class="section-header">
            <h4>💾 Imagens do Projeto ({{ projectImages.length }} disponíveis)</h4>
            <div class="header-actions">
              <button class="btn-select-mode" (click)="toggleSelectionMode()" [class.active]="selectionMode">
                {{ selectionMode ? '✓ Modo Seleção' : '☐ Selecionar' }}
              </button>
              @if (selectionMode && selectedProjectImages.length > 0) {
                <button class="btn-add-selected" (click)="addSelectedToChunk.emit()">
                  + Adicionar ({{ selectedProjectImages.length }})
                </button>
              }
            </div>
          </div>
          
          @if (selectionMode) {
            <div class="selection-toolbar">
              <button class="btn-toolbar" (click)="selectAllProjectImages.emit()">
                Selecionar Todas
              </button>
              <button class="btn-toolbar" (click)="deselectAllProjectImages.emit()">
                Limpar Seleção
              </button>
            </div>
          }
          
          <div class="images-mini-grid" [class.selection-mode]="selectionMode">
            @for (img of projectImages; track img.id) {
              <div 
                class="image-mini" 
                [class.selected]="isProjectImageSelected(img.id)"
                (click)="handleProjectImageClick(img.id)"
                [title]="selectionMode ? 'Clique para selecionar' : 'Clique para adicionar'"
              >
                @if (selectionMode) {
                  <div class="selection-checkbox">
                    <input type="checkbox" [checked]="isProjectImageSelected(img.id)" readonly />
                  </div>
                }
                <span class="img-name">{{ img.originalFilename }}</span>
                @if (!selectionMode) {
                  <span class="add-icon">+</span>
                }
              </div>
            }
          </div>
        </div>
      }

      <!-- Chunk Images Grid -->
      <div class="chunk-images">
        <div class="section-header">
          <h4>Imagens neste Chunk ({{ chunkImages.length }})</h4>
          @if (selectedChunkImages.length > 0) {
            <button class="btn-remove" (click)="removeSelectedImages.emit()">
              Remover Selecionadas ({{ selectedChunkImages.length }})
            </button>
          }
        </div>
        
        @if (chunkImages.length > 0) {
          <div class="images-grid">
            @for (img of chunkImages; track img.id) {
              <div 
                class="image-card"
                [class.selected]="isImageSelected(img.id)"
                (click)="toggleImageSelection.emit(img.id)"
              >
                <div class="image-thumb">
                  <img [src]="getImageThumbnail(img)" [alt]="img.originalFilename" loading="lazy" />
                </div>
                <div class="image-info">
                  <span class="img-name">{{ img.originalFilename }}</span>
                  <span class="img-size">{{ formatFileSize(img.fileSize) }}</span>
                </div>
                <div class="image-checkbox">
                  <input type="checkbox" [checked]="isImageSelected(img.id)" />
                </div>
              </div>
            }
          </div>
        } @else {
          <div class="empty-state">
            <p>Nenhuma imagem neste chunk</p>
            <p class="hint">Faça upload ou adicione imagens do projeto acima</p>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .photos-tab {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .upload-zone {
      border: 2px dashed #30363d;
      border-radius: 8px;
      padding: 24px;
      text-align: center;
      transition: all 0.2s;
    }

    .upload-zone.dragover {
      border-color: #58a6ff;
      background: #1f6feb11;
    }

    .upload-content { color: #8b949e; }
    .upload-icon { font-size: 32px; margin-bottom: 8px; }

    .link-btn {
      background: none;
      border: none;
      color: #58a6ff;
      cursor: pointer;
      text-decoration: underline;
    }

    .upload-hint { font-size: 11px; color: #6e7681; margin-top: 8px; display: block; }

    /* Upload Limits Configuration Styles */
    .upload-limits-config {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 16px;
      margin-top: 16px;
    }

    .config-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }

    .config-title {
      font-size: 13px;
      font-weight: 600;
      color: #c9d1d9;
    }

    .btn-save-limits {
      background: #238636;
      border: 1px solid #2ea043;
      color: #fff;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 500;
      transition: all 0.2s;
    }

    .btn-save-limits:hover:not(:disabled) {
      background: #2ea043;
    }

    .btn-save-limits:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .config-fields {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    .config-field {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .config-field label {
      font-size: 12px;
      font-weight: 500;
      color: #c9d1d9;
    }

    .config-input {
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 8px 12px;
      color: #c9d1d9;
      font-size: 13px;
      transition: border-color 0.2s;
    }

    .config-input:focus {
      outline: none;
      border-color: #58a6ff;
    }

    .config-hint {
      font-size: 11px;
      color: #6e7681;
    }

    .limits-error {
      margin-top: 12px;
      padding: 10px 12px;
      background: #f8514922;
      border: 1px solid #f85149;
      border-radius: 6px;
      color: #ffa198;
      font-size: 12px;
    }

    .limits-success {
      margin-top: 12px;
      padding: 10px 12px;
      background: #2ea04322;
      border: 1px solid #2ea043;
      border-radius: 6px;
      color: #7ee787;
      font-size: 12px;
    }

    .progress-bar {
      height: 4px;
      background: #30363d;
      border-radius: 2px;
      overflow: hidden;
      margin: 8px 0;
    }

    .progress-fill {
      height: 100%;
      background: #58a6ff;
      transition: width 0.2s;
    }

    .progress-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid #30363d;
      border-top-color: #58a6ff;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 12px;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }

    .section-header h4 { margin: 0; font-size: 13px; }

    .btn-add-all, .btn-remove {
      background: transparent;
      border: 1px solid #30363d;
      color: #c9d1d9;
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
    }

    .btn-add-all:hover { border-color: #58a6ff; color: #58a6ff; }
    .btn-remove { border-color: #f85149; color: #f85149; }
    .btn-remove:hover { background: #f8514922; }

    .available-images {
      background: #161b22;
      border-radius: 8px;
      padding: 12px;
    }

    .images-mini-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      max-height: 100px;
      overflow-y: auto;
    }

    .image-mini {
      display: flex;
      align-items: center;
      gap: 4px;
      background: #21262d;
      padding: 4px 8px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 11px;
    }

    .image-mini:hover { background: #30363d; }
    .image-mini .add-icon { color: #3fb950; }

    .chunk-images { flex: 1; }

    .images-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 12px;
    }

    .image-card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      overflow: hidden;
      cursor: pointer;
      position: relative;
    }

    .image-card:hover { border-color: #8b949e; }
    .image-card.selected { border-color: #58a6ff; background: #1f6feb11; }

    .image-thumb {
      height: 100px;
      background: #21262d;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .image-thumb img {
      max-width: 100%;
      max-height: 100%;
      object-fit: cover;
    }

    .image-info {
      padding: 8px;
    }

    .img-name {
      display: block;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .img-size { font-size: 11px; color: #8b949e; }

    .image-checkbox {
      position: absolute;
      top: 8px;
      left: 8px;
    }

    .empty-state {
      text-align: center;
      padding: 40px;
      color: #8b949e;
    }

    .empty-state .hint { font-size: 12px; }

    /* Selection Mode Styles */
    .btn-select-mode {
      background: transparent;
      border: 1px solid #30363d;
      color: #c9d1d9;
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      margin-left: 8px;
    }

    .btn-select-mode:hover {
      border-color: #58a6ff;
      color: #58a6ff;
    }

    .btn-select-mode.active {
      border-color: #58a6ff;
      background: #1f6feb22;
      color: #58a6ff;
    }

    .selection-toolbar {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
      align-items: center;
    }

    .btn-toolbar {
      background: transparent;
      border: 1px solid #30363d;
      color: #c9d1d9;
      padding: 6px 12px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
    }

    .btn-toolbar:hover {
      border-color: #8b949e;
      background: #21262d;
    }

    .btn-add-selected {
      border-color: #3fb950;
      color: #3fb950;
    }

    .btn-add-selected:hover {
      background: #3fb95022;
    }

    .btn-add-selected:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      border-color: #30363d;
      color: #6e7681;
    }

    .selection-checkbox {
      position: absolute;
      top: 8px;
      left: 8px;
      width: 20px;
      height: 20px;
      cursor: pointer;
      z-index: 1;
    }

    .image-mini.selection-mode {
      padding-left: 32px;
      position: relative;
    }

    .selection-count {
      font-size: 12px;
      color: #8b949e;
      margin-left: auto;
    }
  `]
})
export class PhotosTabComponent implements OnInit {
  @Input() projectId: number = 0;
  @Input() projectImages: ProjectImage[] = [];
  @Input() chunkImages: ProjectImage[] = [];
  @Input() selectedChunkImages: number[] = [];
  @Input() selectedProjectImages: number[] = [];
  @Input() isUploading = false;
  @Input() isDragOver = false;
  @Input() uploadProgress: UploadProgress | null = null;
  @Input() uploadingFiles: File[] = [];
  @Input() maxFileSizeMb = 100;
  @Input() maxRequestSizeMb = 500;
  @Input() hardMaxFileSizeMb = 5120;
  @Input() hardMaxRequestSizeMb = 20480;

  @Output() filesSelected = new EventEmitter<Event>();
  @Output() dragOver = new EventEmitter<DragEvent>();
  @Output() dragLeave = new EventEmitter<DragEvent>();
  @Output() drop = new EventEmitter<DragEvent>();
  @Output() addImage = new EventEmitter<number>();
  @Output() addAllImages = new EventEmitter<void>();
  @Output() addSelectedToChunk = new EventEmitter<void>();
  @Output() removeSelectedImages = new EventEmitter<void>();
  @Output() toggleImageSelection = new EventEmitter<number>();
  @Output() toggleProjectImageSelection = new EventEmitter<number>();
  @Output() selectAllProjectImages = new EventEmitter<void>();
  @Output() deselectAllProjectImages = new EventEmitter<void>();
  @Output() saveLimits = new EventEmitter<{ maxFileSizeMb: number; maxRequestSizeMb: number }>();

  selectionMode = false;
  localMaxFileSizeMb = 100;
  localMaxRequestSizeMb = 500;
  isSavingLimits = false;
  limitsError: string | null = null;
  limitsSuccess: string | null = null;

  ngOnInit(): void {
    this.localMaxFileSizeMb = this.maxFileSizeMb;
    this.localMaxRequestSizeMb = this.maxRequestSizeMb;
  }

  onSaveLimits(): void {
    // Validações
    if (this.localMaxFileSizeMb < 1) {
      this.limitsError = 'O tamanho máximo por arquivo deve ser pelo menos 1MB';
      this.limitsSuccess = null;
      return;
    }

    if (this.localMaxRequestSizeMb < 1) {
      this.limitsError = 'O tamanho máximo por envio deve ser pelo menos 1MB';
      this.limitsSuccess = null;
      return;
    }

    if (this.localMaxRequestSizeMb < this.localMaxFileSizeMb) {
      this.limitsError = 'O tamanho máximo por envio deve ser maior ou igual ao tamanho máximo por arquivo';
      this.limitsSuccess = null;
      return;
    }

    if (this.localMaxFileSizeMb > this.hardMaxFileSizeMb) {
      this.limitsError = `O tamanho máximo por arquivo não pode exceder ${this.hardMaxFileSizeMb}MB`;
      this.limitsSuccess = null;
      return;
    }

    if (this.localMaxRequestSizeMb > this.hardMaxRequestSizeMb) {
      this.limitsError = `O tamanho máximo por envio não pode exceder ${this.hardMaxRequestSizeMb}MB`;
      this.limitsSuccess = null;
      return;
    }

    this.limitsError = null;
    this.limitsSuccess = null;
    this.isSavingLimits = true;
    
    this.saveLimits.emit({
      maxFileSizeMb: this.localMaxFileSizeMb,
      maxRequestSizeMb: this.localMaxRequestSizeMb
    });

    // Simular feedback de sucesso (will be updated by parent)
    setTimeout(() => {
      this.isSavingLimits = false;
      this.limitsSuccess = 'Configurações salvas com sucesso!';
      setTimeout(() => {
        this.limitsSuccess = null;
      }, 3000);
    }, 500);
  }

  toggleSelectionMode(): void {
    this.selectionMode = !this.selectionMode;
    if (!this.selectionMode) {
      this.deselectAllProjectImages.emit();
    }
  }

  handleProjectImageClick(imageId: number): void {
    if (this.selectionMode) {
      this.toggleProjectImageSelection.emit(imageId);
    } else {
      this.addImage.emit(imageId);
    }
  }

  isProjectImageSelected(imageId: number): boolean {
    return this.selectedProjectImages.includes(imageId);
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragOver.emit(event);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.dragLeave.emit(event);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.drop.emit(event);
  }

  onFilesSelected(event: Event): void {
    this.filesSelected.emit(event);
  }

  isImageSelected(imageId: number): boolean {
    return this.selectedChunkImages.includes(imageId);
  }

  getImageThumbnail(image: ProjectImage): string {
    return `/api/v1/projects/${this.projectId}/images/${image.id}/thumbnail`;
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }
}
