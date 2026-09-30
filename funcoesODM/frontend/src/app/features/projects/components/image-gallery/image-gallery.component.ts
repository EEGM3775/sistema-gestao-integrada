import { Component, inject, signal, input, output, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ImageUploadService } from '../../services/image-upload.service';
import { ProjectImage } from '../../models/project.model';

@Component({
  selector: 'app-image-gallery',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="image-gallery">
      @if (loading()) {
        <div class="loading">
          <div class="spinner"></div>
          <p>Carregando imagens...</p>
        </div>
      } @else if (images().length === 0) {
        <div class="empty-state">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
          <p>Nenhuma imagem no projeto</p>
          <p class="hint">Faça upload de imagens para começar</p>
        </div>
      } @else {
        <div class="gallery-header">
          <span class="image-count">{{ images().length }} imagem(ns)</span>
          @if (images().length > 0) {
            <button class="delete-all-btn" (click)="confirmDeleteAll()">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
              Excluir todas
            </button>
          }
        </div>
        
        <div class="gallery-grid">
          @for (image of images(); track image.id) {
            <div class="image-card">
              <div class="image-thumbnail">
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <polyline points="21 15 16 10 5 21"/>
                </svg>
              </div>
              <div class="image-info">
                <p class="image-name" [title]="image.originalFilename">{{ image.originalFilename }}</p>
                <p class="image-meta">{{ formatFileSize(image.fileSize) }}</p>
              </div>
              <button class="delete-btn" (click)="deleteImage(image)" [disabled]="deletingId() === image.id">
                @if (deletingId() === image.id) {
                  <div class="mini-spinner"></div>
                } @else {
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                }
              </button>
            </div>
          }
        </div>
      }

      <!-- Delete Confirmation Modal -->
      @if (showDeleteConfirm()) {
        <div class="modal-overlay" (click)="cancelDelete()">
          <div class="modal-content" (click)="$event.stopPropagation()">
            <h3>Confirmar exclusão</h3>
            <p>Tem certeza que deseja excluir todas as {{ images().length }} imagens?</p>
            <p class="warning">Esta ação não pode ser desfeita.</p>
            <div class="modal-actions">
              <button class="btn-cancel" (click)="cancelDelete()">Cancelar</button>
              <button class="btn-delete" (click)="deleteAllImages()">Excluir todas</button>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .image-gallery {
      width: 100%;
    }

    .loading, .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: var(--text-secondary, #6b7280);
    }

    .loading .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid var(--border-color, #e5e7eb);
      border-top-color: var(--primary-color, #3b82f6);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 16px;
    }

    .empty-state svg {
      margin-bottom: 16px;
      opacity: 0.5;
    }

    .empty-state p {
      margin: 0;
    }

    .empty-state .hint {
      font-size: 13px;
      margin-top: 4px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .gallery-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .image-count {
      font-size: 14px;
      font-weight: 500;
      color: var(--text-secondary, #6b7280);
    }

    .delete-all-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: none;
      border: 1px solid var(--error-color, #ef4444);
      color: var(--error-color, #ef4444);
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .delete-all-btn:hover {
      background: var(--error-color, #ef4444);
      color: white;
    }

    .gallery-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 12px;
    }

    .image-card {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      background: var(--bg-secondary, #f9fafb);
      border: 1px solid var(--border-color, #e5e7eb);
      border-radius: 8px;
      transition: all 0.2s;
    }

    .image-card:hover {
      border-color: var(--primary-color, #3b82f6);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }

    .image-thumbnail {
      width: 48px;
      height: 48px;
      background: var(--border-color, #e5e7eb);
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .image-thumbnail svg {
      color: var(--text-secondary, #9ca3af);
    }

    .image-info {
      flex: 1;
      min-width: 0;
    }

    .image-name {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-primary, #111827);
      margin: 0 0 4px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .image-meta {
      font-size: 12px;
      color: var(--text-secondary, #6b7280);
      margin: 0;
    }

    .delete-btn {
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: none;
      border: none;
      color: var(--text-secondary, #9ca3af);
      cursor: pointer;
      border-radius: 6px;
      transition: all 0.2s;
      flex-shrink: 0;
    }

    .delete-btn:hover:not(:disabled) {
      color: var(--error-color, #ef4444);
      background: #fef2f2;
    }

    .delete-btn:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }

    .mini-spinner {
      width: 16px;
      height: 16px;
      border: 2px solid var(--border-color, #e5e7eb);
      border-top-color: var(--primary-color, #3b82f6);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    /* Modal */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }

    .modal-content {
      background: white;
      padding: 24px;
      border-radius: 12px;
      max-width: 400px;
      width: 90%;
    }

    .modal-content h3 {
      margin: 0 0 12px;
      font-size: 18px;
      color: var(--text-primary, #111827);
    }

    .modal-content p {
      margin: 0 0 8px;
      color: var(--text-secondary, #6b7280);
    }

    .modal-content .warning {
      color: var(--error-color, #ef4444);
      font-size: 13px;
    }

    .modal-actions {
      display: flex;
      gap: 12px;
      margin-top: 20px;
    }

    .btn-cancel, .btn-delete {
      flex: 1;
      padding: 10px 16px;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .btn-cancel {
      background: var(--bg-secondary, #f3f4f6);
      border: 1px solid var(--border-color, #e5e7eb);
      color: var(--text-primary, #374151);
    }

    .btn-cancel:hover {
      background: var(--border-color, #e5e7eb);
    }

    .btn-delete {
      background: var(--error-color, #ef4444);
      border: none;
      color: white;
    }

    .btn-delete:hover {
      background: #dc2626;
    }
  `]
})
export class ImageGalleryComponent implements OnInit {
  private readonly uploadService = inject(ImageUploadService);

  // Inputs
  projectId = input.required<number>();

  // Outputs
  imagesChanged = output<void>();

  // State
  images = signal<ProjectImage[]>([]);
  loading = signal(true);
  deletingId = signal<number | null>(null);
  showDeleteConfirm = signal(false);

  ngOnInit(): void {
    this.loadImages();
  }

  loadImages(): void {
    this.loading.set(true);
    this.uploadService.getProjectImages(this.projectId()).subscribe({
      next: (images) => {
        this.images.set(images);
        this.loading.set(false);
      },
      error: (error) => {
        console.error('Failed to load images:', error);
        this.loading.set(false);
      }
    });
  }

  deleteImage(image: ProjectImage): void {
    this.deletingId.set(image.id);
    
    this.uploadService.deleteImage(this.projectId(), image.id).subscribe({
      next: () => {
        this.images.update(images => images.filter(i => i.id !== image.id));
        this.deletingId.set(null);
        this.imagesChanged.emit();
      },
      error: (error) => {
        console.error('Failed to delete image:', error);
        this.deletingId.set(null);
      }
    });
  }

  confirmDeleteAll(): void {
    this.showDeleteConfirm.set(true);
  }

  cancelDelete(): void {
    this.showDeleteConfirm.set(false);
  }

  deleteAllImages(): void {
    this.showDeleteConfirm.set(false);
    this.loading.set(true);

    this.uploadService.deleteAllImages(this.projectId()).subscribe({
      next: () => {
        this.images.set([]);
        this.loading.set(false);
        this.imagesChanged.emit();
      },
      error: (error) => {
        console.error('Failed to delete all images:', error);
        this.loading.set(false);
      }
    });
  }

  formatFileSize(bytes: number): string {
    return this.uploadService.formatFileSize(bytes);
  }
}
