import { Component, inject, signal, input, output, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ImageUploadService } from '../../services/image-upload.service';
import { ImageUploadResponse, UploadProgress, UploadLimits } from '../../models/project.model';

@Component({
  selector: 'app-image-uploader',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="image-uploader">
      <!-- Upload Limits -->
      <div class="upload-limits">
        <div class="limits-header">
          <span>Limites de upload</span>
          <button class="save-limits-btn" (click)="saveLimits()" [disabled]="limitsSaving() || limitsLoading()">Salvar</button>
        </div>

        <div class="limits-row">
          <div class="limits-field">
            <label>Máx. por arquivo (MB)</label>
            <input type="number" [(ngModel)]="maxFileSizeMb" min="1" />
            <small>Máximo permitido: {{ uploadLimits()?.hardMaxFileSizeMb ? (uploadLimits()?.hardMaxFileSizeMb + 'MB') : 'Sem limite' }}</small>
          </div>
          <div class="limits-field">
            <label>Máx. por envio (MB)</label>
            <input type="number" [(ngModel)]="maxRequestSizeMb" min="1" />
            <small>Máximo permitido: {{ uploadLimits()?.hardMaxRequestSizeMb ? (uploadLimits()?.hardMaxRequestSizeMb + 'MB') : 'Sem limite' }}</small>
          </div>
        </div>

        @if (limitsError()) {
          <div class="limits-error">{{ limitsError() }}</div>
        }
      </div>

      <!-- Drag and Drop Zone -->
      <div 
        class="drop-zone"
        [class.drag-over]="isDragOver()"
        [class.uploading]="isUploading()"
        (dragover)="onDragOver($event)"
        (dragleave)="onDragLeave($event)"
        (drop)="onDrop($event)"
        (click)="fileInput.click()"
      >
        @if (isUploading()) {
          <div class="upload-progress">
            <div class="progress-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spinning">
                <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              </svg>
            </div>
            <p class="progress-text">Enviando imagens...</p>
            @if (uploadProgress(); as progress) {
              <div class="progress-bar-container">
                <div class="progress-bar" [style.width.%]="progress.percentage"></div>
              </div>
              <p class="progress-details">
                {{ progress.percentage }}% - {{ formatBytes(progress.loaded) }} / {{ formatBytes(progress.total) }}
              </p>
            }
          </div>
        } @else {
          <div class="drop-zone-content">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p class="drop-text">
              Arraste imagens aqui ou <span class="link">clique para selecionar</span>
            </p>
            <p class="drop-hint">
              JPEG, PNG, TIFF • Máximo {{ maxFileSizeMb }}MB por arquivo • {{ maxRequestSizeMb }}MB por envio
            </p>
          </div>
        }
        
        <input 
          #fileInput
          type="file" 
          multiple 
          accept="image/jpeg,image/jpg,image/png,image/tiff,image/tif"
          (change)="onFileSelected($event)"
          style="display: none"
        />
      </div>

      <!-- Selected Files Preview -->
      @if (selectedFiles().length > 0 && !isUploading()) {
        <div class="selected-files">
          <div class="files-header">
            <span>{{ selectedFiles().length }} arquivo(s) selecionado(s)</span>
            <button class="clear-btn" (click)="clearSelection()">Limpar</button>
          </div>
          <ul class="files-list">
            @for (file of selectedFiles(); track file.name) {
              <li class="file-item">
                <span class="file-name">{{ file.name }}</span>
                <span class="file-size">{{ formatBytes(file.size) }}</span>
              </li>
            }
          </ul>
          <button class="upload-btn" (click)="startUpload()">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Enviar {{ selectedFiles().length }} imagem(ns)
          </button>
        </div>
      }

      <!-- Validation Errors -->
      @if (validationErrors().length > 0) {
        <div class="validation-errors">
          <p class="error-title">Alguns arquivos não puderam ser adicionados:</p>
          <ul>
            @for (error of validationErrors(); track error) {
              <li>{{ error }}</li>
            }
          </ul>
        </div>
      }

      <!-- Upload Result -->
      @if (uploadResult(); as result) {
        <div class="upload-result" [class.has-errors]="result.totalFailed > 0">
          @if (result.totalUploaded > 0) {
            <p class="success-msg">
              ✓ {{ result.totalUploaded }} imagem(ns) enviada(s) com sucesso
            </p>
          }
          @if (result.totalFailed > 0) {
            <p class="error-msg">
              ✗ {{ result.totalFailed }} arquivo(s) falharam
            </p>
            <ul class="error-list">
              @for (error of result.errors; track error) {
                <li>{{ error }}</li>
              }
            </ul>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .image-uploader {
      width: 100%;
    }

    .upload-limits {
      padding: 16px;
      border: 1px solid var(--border-color, #e5e7eb);
      border-radius: 10px;
      margin-bottom: 16px;
      background: var(--bg-secondary, #f9fafb);
    }

    .limits-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 600;
      margin-bottom: 12px;
    }

    .limits-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .limits-field label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 6px;
      color: var(--text-secondary, #6b7280);
    }

    .limits-field input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--border-color, #d1d5db);
      border-radius: 6px;
      font-size: 14px;
    }

    .limits-field small {
      display: block;
      margin-top: 4px;
      font-size: 11px;
      color: var(--text-secondary, #6b7280);
    }

    .save-limits-btn {
      background: var(--primary-color, #3b82f6);
      color: #fff;
      border: none;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
    }

    .save-limits-btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .limits-error {
      margin-top: 8px;
      color: #b91c1c;
      font-size: 12px;
    }

    .drop-zone {
      border: 2px dashed var(--border-color, #d1d5db);
      border-radius: 12px;
      padding: 40px 20px;
      text-align: center;
      cursor: pointer;
      transition: all 0.3s ease;
      background: var(--bg-secondary, #f9fafb);
    }

    .drop-zone:hover {
      border-color: var(--primary-color, #3b82f6);
      background: var(--primary-bg, #eff6ff);
    }

    .drop-zone.drag-over {
      border-color: var(--primary-color, #3b82f6);
      background: var(--primary-bg, #dbeafe);
      transform: scale(1.02);
    }

    .drop-zone.uploading {
      cursor: default;
      pointer-events: none;
    }

    .drop-zone-content svg {
      color: var(--text-secondary, #6b7280);
      margin-bottom: 16px;
    }

    .drop-text {
      font-size: 16px;
      color: var(--text-primary, #111827);
      margin-bottom: 8px;
    }

    .drop-text .link {
      color: var(--primary-color, #3b82f6);
      font-weight: 500;
    }

    .drop-hint {
      font-size: 13px;
      color: var(--text-secondary, #6b7280);
    }

    .upload-progress {
      padding: 20px;
    }

    .progress-icon {
      color: var(--primary-color, #3b82f6);
      margin-bottom: 16px;
    }

    .spinning {
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    .progress-text {
      font-size: 16px;
      font-weight: 500;
      color: var(--text-primary, #111827);
      margin-bottom: 16px;
    }

    .progress-bar-container {
      width: 100%;
      max-width: 400px;
      height: 8px;
      background: var(--border-color, #e5e7eb);
      border-radius: 4px;
      margin: 0 auto 12px;
      overflow: hidden;
    }

    .progress-bar {
      height: 100%;
      background: var(--primary-color, #3b82f6);
      border-radius: 4px;
      transition: width 0.3s ease;
    }

    .progress-details {
      font-size: 13px;
      color: var(--text-secondary, #6b7280);
    }

    .selected-files {
      margin-top: 20px;
      border: 1px solid var(--border-color, #e5e7eb);
      border-radius: 8px;
      overflow: hidden;
    }

    .files-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      background: var(--bg-secondary, #f9fafb);
      border-bottom: 1px solid var(--border-color, #e5e7eb);
      font-size: 14px;
      font-weight: 500;
    }

    .clear-btn {
      background: none;
      border: none;
      color: var(--error-color, #ef4444);
      cursor: pointer;
      font-size: 13px;
    }

    .files-list {
      list-style: none;
      padding: 0;
      margin: 0;
      max-height: 200px;
      overflow-y: auto;
    }

    .file-item {
      display: flex;
      justify-content: space-between;
      padding: 10px 16px;
      border-bottom: 1px solid var(--border-color, #f3f4f6);
      font-size: 13px;
    }

    .file-item:last-child {
      border-bottom: none;
    }

    .file-name {
      color: var(--text-primary, #111827);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
      margin-right: 16px;
    }

    .file-size {
      color: var(--text-secondary, #6b7280);
      white-space: nowrap;
    }

    .upload-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      padding: 14px;
      background: var(--primary-color, #3b82f6);
      color: white;
      border: none;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .upload-btn:hover {
      background: var(--primary-hover, #2563eb);
    }

    .validation-errors {
      margin-top: 16px;
      padding: 12px 16px;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 8px;
      font-size: 13px;
    }

    .error-title {
      color: #991b1b;
      font-weight: 500;
      margin-bottom: 8px;
    }

    .validation-errors ul {
      margin: 0;
      padding-left: 20px;
      color: #b91c1c;
    }

    .upload-result {
      margin-top: 16px;
      padding: 12px 16px;
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      border-radius: 8px;
    }

    .upload-result.has-errors {
      background: #fffbeb;
      border-color: #fde68a;
    }

    .success-msg {
      color: #166534;
      font-weight: 500;
      margin-bottom: 4px;
    }

    .error-msg {
      color: #92400e;
      font-weight: 500;
    }

    .error-list {
      margin: 8px 0 0;
      padding-left: 20px;
      color: #b45309;
      font-size: 13px;
    }
  `]
})
export class ImageUploaderComponent implements OnInit {
  private readonly uploadService = inject(ImageUploadService);

  // Input
  projectId = input.required<number>();

  // Output
  uploadComplete = output<ImageUploadResponse>();

  // State
  isDragOver = signal(false);
  isUploading = signal(false);
  selectedFiles = signal<File[]>([]);
  validationErrors = signal<string[]>([]);
  uploadProgress = signal<UploadProgress | null>(null);
  uploadResult = signal<ImageUploadResponse | null>(null);
  uploadLimits = signal<UploadLimits | null>(null);
  limitsLoading = signal(false);
  limitsSaving = signal(false);
  limitsError = signal<string | null>(null);

  maxFileSizeMb = 100;
  maxRequestSizeMb = 500;

  constructor() {
    // Subscribe to upload progress
    this.uploadService.uploadProgress$.subscribe(progress => {
      this.uploadProgress.set(progress);
    });

    this.uploadService.uploading$.subscribe(uploading => {
      this.isUploading.set(uploading);
    });
  }

  ngOnInit(): void {
    this.loadUploadLimits();
  }

  loadUploadLimits(): void {
    this.limitsLoading.set(true);
    this.uploadService.getUploadLimits().subscribe({
      next: (limits) => {
        this.uploadLimits.set(limits);
        this.maxFileSizeMb = limits.maxFileSizeMb;
        this.maxRequestSizeMb = limits.maxRequestSizeMb;
        this.limitsLoading.set(false);
        this.limitsError.set(null);
      },
      error: () => {
        this.limitsLoading.set(false);
        this.limitsError.set('Não foi possível carregar os limites de upload.');
      }
    });
  }

  saveLimits(): void {
    const hardFileMax = this.uploadLimits()?.hardMaxFileSizeMb ?? 0;
    const hardRequestMax = this.uploadLimits()?.hardMaxRequestSizeMb ?? 0;

    if (this.maxFileSizeMb <= 0 || this.maxRequestSizeMb <= 0) {
      this.limitsError.set('Os limites devem ser maiores que zero.');
      return;
    }

    if ((hardFileMax > 0 && this.maxFileSizeMb > hardFileMax) || (hardRequestMax > 0 && this.maxRequestSizeMb > hardRequestMax)) {
      this.limitsError.set('Os limites excedem o máximo permitido pelo servidor.');
      return;
    }

    if (this.maxRequestSizeMb < this.maxFileSizeMb) {
      this.limitsError.set('O limite por envio deve ser maior ou igual ao limite por arquivo.');
      return;
    }

    this.limitsSaving.set(true);
    this.uploadService.updateUploadLimits({
      maxFileSizeMb: this.maxFileSizeMb,
      maxRequestSizeMb: this.maxRequestSizeMb
    }).subscribe({
      next: (limits) => {
        this.uploadLimits.set(limits);
        this.maxFileSizeMb = limits.maxFileSizeMb;
        this.maxRequestSizeMb = limits.maxRequestSizeMb;
        this.limitsSaving.set(false);
        this.limitsError.set(null);
      },
      error: (error) => {
        this.limitsSaving.set(false);
        this.limitsError.set(error?.error?.message || 'Falha ao salvar limites.');
      }
    });
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragOver.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragOver.set(false);

    const files = event.dataTransfer?.files;
    if (files) {
      this.processFiles(Array.from(files));
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      this.processFiles(Array.from(input.files));
    }
    // Reset input for re-selecting same files
    input.value = '';
  }

  private processFiles(files: File[]): void {
    this.uploadResult.set(null);
    
    const { valid, errors } = this.uploadService.validateFiles(files, this.maxFileSizeMb);

    const totalSelectedBytes = valid.reduce((sum, file) => sum + file.size, 0);
    const currentBytes = this.selectedFiles().reduce((sum, file) => sum + file.size, 0);
    const maxRequestBytes = this.maxRequestSizeMb * 1024 * 1024;

    if (currentBytes + totalSelectedBytes > maxRequestBytes) {
      errors.push(`Total do envio excede o limite de ${this.maxRequestSizeMb}MB.`);
    }
    
    this.validationErrors.set(errors);
    
    if (valid.length > 0 && errors.length === 0) {
      // Add to existing selection
      const current = this.selectedFiles();
      const newFiles = valid.filter(f => !current.some(c => c.name === f.name));
      this.selectedFiles.set([...current, ...newFiles]);
    }
  }

  clearSelection(): void {
    this.selectedFiles.set([]);
    this.validationErrors.set([]);
    this.uploadResult.set(null);
  }

  startUpload(): void {
    const files = this.selectedFiles();
    if (files.length === 0) return;

    this.uploadService.uploadImages(this.projectId(), files).subscribe({
      next: (response) => {
        this.uploadResult.set(response);
        this.selectedFiles.set([]);
        this.uploadComplete.emit(response);
      },
      error: (error) => {
        console.error('Upload failed:', error);
        this.uploadResult.set({
          totalUploaded: 0,
          totalFailed: files.length,
          images: [],
          errors: ['Erro ao enviar imagens. Tente novamente.']
        });
      }
    });
  }

  formatBytes(bytes: number): string {
    return this.uploadService.formatFileSize(bytes);
  }
}
