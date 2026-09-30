import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap, map } from 'rxjs/operators';
import { Chunk, ChunkCreateRequest, ChunkUpdateRequest, ChunkAddImagesRequest, ProjectImage } from '../models/project.model';

@Injectable({
  providedIn: 'root'
})
export class ChunkService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api/v1/projects';

  // State management
  private chunksSubject = new BehaviorSubject<Chunk[]>([]);
  chunks$ = this.chunksSubject.asObservable();

  private selectedChunkSubject = new BehaviorSubject<Chunk | null>(null);
  selectedChunk$ = this.selectedChunkSubject.asObservable();

  private failedCountSignal = signal(0);
  failedChunksCount = this.failedCountSignal.asReadonly();

  /**
   * Get all chunks for a project
   */
  getChunks(projectId: number): Observable<Chunk[]> {
    return this.http.get<Chunk[]>(`${this.apiUrl}/${projectId}/chunks`).pipe(
      tap(chunks => {
        this.chunksSubject.next(chunks);
        this.failedCountSignal.set(chunks.filter(c => c.status === 'FAILED').length);
      })
    );
  }

  retryChunk(projectId: number, chunkId: number): Observable<Chunk> {
    return this.http.post<Chunk>(`${this.apiUrl}/${projectId}/chunks/${chunkId}/retry`, {}).pipe(
      tap(updated => this.updateChunkInState(updated))
    );
  }

  /**
   * Create a new chunk
   */
  createChunk(projectId: number, request: ChunkCreateRequest): Observable<Chunk> {
    return this.http.post<Chunk>(`${this.apiUrl}/${projectId}/chunks`, request).pipe(
      tap(chunk => {
        const current = this.chunksSubject.value;
        this.chunksSubject.next([...current, chunk]);
      })
    );
  }

  /**
   * Get a specific chunk
   */
  getChunk(projectId: number, chunkId: number): Observable<Chunk> {
    return this.http.get<Chunk>(`${this.apiUrl}/${projectId}/chunks/${chunkId}`);
  }

  /**
   * Update a chunk
   */
  updateChunk(projectId: number, chunkId: number, request: ChunkUpdateRequest): Observable<Chunk> {
    return this.http.put<Chunk>(`${this.apiUrl}/${projectId}/chunks/${chunkId}`, request).pipe(
      tap(updatedChunk => {
        const current = this.chunksSubject.value;
        const index = current.findIndex(c => c.id === chunkId);
        if (index >= 0) {
          current[index] = updatedChunk;
          this.chunksSubject.next([...current]);
        }
        if (this.selectedChunkSubject.value?.id === chunkId) {
          this.selectedChunkSubject.next(updatedChunk);
        }
      })
    );
  }

  /**
   * Delete a chunk
   */
  deleteChunk(projectId: number, chunkId: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${projectId}/chunks/${chunkId}`).pipe(
      tap(() => {
        const current = this.chunksSubject.value;
        this.chunksSubject.next(current.filter(c => c.id !== chunkId));
        if (this.selectedChunkSubject.value?.id === chunkId) {
          this.selectedChunkSubject.next(null);
        }
      })
    );
  }

  /**
   * Add images to a chunk
   */
  addImagesToChunk(projectId: number, chunkId: number, imageIds: number[]): Observable<Chunk> {
    const request: ChunkAddImagesRequest = { imageIds };
    return this.http.post<Chunk>(`${this.apiUrl}/${projectId}/chunks/${chunkId}/images`, request).pipe(
      tap(updatedChunk => {
        this.updateChunkInState(updatedChunk);
      })
    );
  }

  /**
   * Remove images from a chunk
   */
  removeImagesFromChunk(projectId: number, chunkId: number, imageIds: number[]): Observable<Chunk> {
    return this.http.request<Chunk>('DELETE', `${this.apiUrl}/${projectId}/chunks/${chunkId}/images`, {
      body: imageIds
    }).pipe(
      tap(updatedChunk => {
        this.updateChunkInState(updatedChunk);
      })
    );
  }

  /**
   * Get images in a chunk
   */
  getChunkImages(projectId: number, chunkId: number): Observable<ProjectImage[]> {
    return this.http.get<ProjectImage[]>(`${this.apiUrl}/${projectId}/chunks/${chunkId}/images`);
  }

  /**
   * Update processing options for a chunk
   */
  updateProcessingOptions(projectId: number, chunkId: number, options: Record<string, any>): Observable<Chunk> {
    return this.http.put<Chunk>(`${this.apiUrl}/${projectId}/chunks/${chunkId}/options`, options).pipe(
      tap(updatedChunk => {
        this.updateChunkInState(updatedChunk);
      })
    );
  }

  /**
   * Start processing a chunk.
   * Se um gcpFile for fornecido, envia como multipart/form-data com o campo "gcpFile".
   * Caso contrario, envia as opcoes como JSON simples.
   */
  processChunk(
    projectId: number,
    chunkId: number,
    options: Record<string, any> = {},
    gcpFile?: File | null
  ): Observable<Chunk> {
    const url = `${this.apiUrl}/${projectId}/chunks/${chunkId}/process`;

    if (gcpFile) {
      const formData = new FormData();
      formData.append('options', JSON.stringify(options));
      formData.append('gcpFile', gcpFile, 'gcp_list.txt');
      return this.http.post<Chunk>(url, formData).pipe(
        tap(updatedChunk => this.updateChunkInState(updatedChunk))
      );
    }

    return this.http.post<Chunk>(url, options).pipe(
      tap(updatedChunk => this.updateChunkInState(updatedChunk))
    );
  }

  /**
   * Ensure project has chunks (migration)
   */
  ensureProjectHasChunks(projectId: number): Observable<Chunk[]> {
    return this.http.post<Chunk[]>(`${this.apiUrl}/${projectId}/chunks/ensure`, {}).pipe(
      tap(chunks => this.chunksSubject.next(chunks))
    );
  }

  /**
   * Select a chunk
   */
  selectChunk(chunk: Chunk | null): void {
    this.selectedChunkSubject.next(chunk);
  }

  /**
   * Get currently selected chunk
   */
  getSelectedChunk(): Chunk | null {
    return this.selectedChunkSubject.value;
  }

  /**
   * Clear chunks state
   */
  clearState(): void {
    this.chunksSubject.next([]);
    this.selectedChunkSubject.next(null);
  }

  /**
   * Helper to update chunk in state
   */
  private updateChunkInState(chunk: Chunk): void {
    const current = this.chunksSubject.value;
    const index = current.findIndex(c => c.id === chunk.id);
    if (index >= 0) {
      current[index] = chunk;
      this.chunksSubject.next([...current]);
      this.failedCountSignal.set(current.filter(c => c.status === 'FAILED').length);
    }
    if (this.selectedChunkSubject.value?.id === chunk.id) {
      this.selectedChunkSubject.next(chunk);
    }
  }

  /**
   * Get status label for display
   */
  getStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      'EMPTY': 'Vazio',
      'READY': 'Pronto',
      'QUEUED': 'Na fila',
      'RUNNING': 'Processando',
      'COMPLETED': 'Concluído',
      'FAILED': 'Falhou',
      'CANCELED': 'Cancelado'
    };
    return labels[status] || status;
  }

  /**
   * Get status icon for display
   */
  getStatusIcon(status: string): string {
    const icons: Record<string, string> = {
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

  /**
   * Format processing time for display
   */
  formatProcessingTime(seconds: number | undefined): string {
    if (!seconds) return '-';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }
}
