import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpEventType, HttpProgressEvent, HttpResponse } from '@angular/common/http';
import { Observable, Subject, BehaviorSubject, throwError } from 'rxjs';
import { map, catchError, filter, tap } from 'rxjs/operators';
import { ProjectImage, ImageUploadResponse, UploadProgress, UploadLimits } from '../models/project.model';

@Injectable({
  providedIn: 'root'
})
export class ImageUploadService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api/v1/projects';

  // Upload progress tracking
  private uploadProgressSubject = new BehaviorSubject<UploadProgress | null>(null);
  uploadProgress$ = this.uploadProgressSubject.asObservable();

  private uploadingSubject = new BehaviorSubject<boolean>(false);
  uploading$ = this.uploadingSubject.asObservable();

  private uploadLimitsSubject = new BehaviorSubject<UploadLimits | null>(null);
  uploadLimits$ = this.uploadLimitsSubject.asObservable();

  /**
   * Upload multiple images to a project with progress tracking
   */
  uploadImages(projectId: number, files: File[]): Observable<ImageUploadResponse> {
    const formData = new FormData();
    
    files.forEach((file) => {
      formData.append('files', file, file.name);
    });

    this.uploadingSubject.next(true);
    this.uploadProgressSubject.next({ loaded: 0, total: 0, percentage: 0 });

    return this.http.post<ImageUploadResponse>(
      `${this.apiUrl}/${projectId}/images`,
      formData,
      {
        reportProgress: true,
        observe: 'events'
      }
    ).pipe(
      tap(event => {
        if (event.type === HttpEventType.UploadProgress) {
          const progress: UploadProgress = {
            loaded: event.loaded ?? 0,
            total: event.total ?? 0,
            percentage: event.total ? Math.round((100 * event.loaded) / event.total) : 0
          };
          this.uploadProgressSubject.next(progress);
        }
      }),
      filter((event): event is HttpResponse<ImageUploadResponse> => 
        event.type === HttpEventType.Response
      ),
      map(response => response.body!),
      tap(() => {
        this.uploadingSubject.next(false);
        this.uploadProgressSubject.next(null);
      }),
      catchError(error => {
        this.uploadingSubject.next(false);
        this.uploadProgressSubject.next(null);
        console.error('Upload error:', error);
        return throwError(() => error);
      })
    );
  }

  /**
   * Get all images for a project
   */
  getProjectImages(projectId: number): Observable<ProjectImage[]> {
    return this.http.get<ProjectImage[]>(`${this.apiUrl}/${projectId}/images`);
  }

  /**
   * Delete a single image
   */
  deleteImage(projectId: number, imageId: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${projectId}/images/${imageId}`);
  }

  /**
   * Delete all images from a project
   */
  deleteAllImages(projectId: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${projectId}/images`);
  }

  /**
   * Get current user upload limits
   */
  getUploadLimits(): Observable<UploadLimits> {
    return this.http.get<UploadLimits>('/api/v1/users/me/upload-limits').pipe(
      tap(limits => this.uploadLimitsSubject.next(limits))
    );
  }

  /**
   * Update current user upload limits
   */
  updateUploadLimits(payload: { maxFileSizeMb: number; maxRequestSizeMb: number }): Observable<UploadLimits> {
    return this.http.put<UploadLimits>('/api/v1/users/me/upload-limits', payload).pipe(
      tap(limits => this.uploadLimitsSubject.next(limits))
    );
  }

  /**
   * Validate files before upload
   */
  validateFiles(files: File[], maxFileSizeMb?: number): { valid: File[]; errors: string[] } {
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/tiff', 'image/tif'];
    const maxSize = (maxFileSizeMb ?? 100) * 1024 * 1024;

    const valid: File[] = [];
    const errors: string[] = [];

    files.forEach(file => {
      if (!validTypes.includes(file.type.toLowerCase())) {
        errors.push(`${file.name}: Tipo de arquivo inválido. Use JPEG, PNG ou TIFF.`);
      } else if (file.size > maxSize) {
        errors.push(`${file.name}: Arquivo muito grande. Máximo ${maxFileSizeMb ?? 100}MB.`);
      } else {
        valid.push(file);
      }
    });

    return { valid, errors };
  }

  /**
   * Format file size for display
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
}
