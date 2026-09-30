import { Injectable, signal, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, catchError, of, Subscription } from 'rxjs';
import { Annotation, CreateAnnotationRequest } from '../models/annotation.model';
import { WebSocketService } from '../../../core/services/websocket.service';

@Injectable({ providedIn: 'root' })
export class AnnotationService {
  private http = inject(HttpClient);
  private wsService = inject(WebSocketService);

  private annotationsSignal = signal<Annotation[]>([]);
  private loadingSignal = signal(false);
  private errorSignal = signal<string | null>(null);

  annotations = this.annotationsSignal.asReadonly();
  loading = this.loadingSignal.asReadonly();
  error = this.errorSignal.asReadonly();

  isVisible(id: number): boolean {
    return this.annotationsSignal().find(a => a.id === id)?.visible !== false;
  }

  /**
   * Alterna visibilidade: atualiza o sinal imediatamente (otimista)
   * e persiste no backend. Em caso de erro, reverte.
   */
  toggleVisibility(id: number): void {
    const annotation = this.annotationsSignal().find(a => a.id === id);
    if (!annotation || this.wsProjectId === null) return;

    const newVisible = annotation.visible === false;
    this.annotationsSignal.update(list =>
      list.map(a => a.id === id ? { ...a, visible: newVisible } : a)
    );

    this.http.patch<Annotation>(
      `/api/v1/projects/${this.wsProjectId}/annotations/${id}`,
      { visible: newVisible }
    ).subscribe({
      next: updated => {
        this.annotationsSignal.update(list => list.map(a => a.id === id ? updated : a));
      },
      error: () => {
        // Reverte atualização otimista em caso de erro
        this.annotationsSignal.update(list => list.map(a => a.id === id ? annotation : a));
      }
    });
  }

  private wsProjectId: number | null = null;
  private wsRefCount = 0;
  private wsSub?: Subscription;

  /**
   * Conecta ao projeto: carrega anotações e assina WS.
   * Idempotente para o mesmo projectId; ref-counted para limpeza correta
   * quando múltiplos componentes (Visualizador + Vegetação) usam o serviço.
   */
  connectToProject(projectId: number): void {
    if (this.wsProjectId === projectId) {
      this.wsRefCount++;
      return;
    }
    this.internalDisconnect();
    this.wsProjectId = projectId;
    this.wsRefCount = 1;
    this.loadAnnotations(projectId);
    this.wsSub = this.wsService.subscribeToProject(projectId).subscribe(msg => {
      if (msg) this.handleWebSocketMessage(msg as { type: string; data?: unknown });
    });
  }

  /** Chamado por cada componente no ngOnDestroy. Desconecta quando o último sai. */
  disconnectFromProject(): void {
    this.wsRefCount = Math.max(0, this.wsRefCount - 1);
    if (this.wsRefCount === 0) {
      this.internalDisconnect();
    }
  }

  private internalDisconnect(): void {
    this.wsSub?.unsubscribe();
    this.wsSub = undefined;
    this.wsProjectId = null;
    this.wsRefCount = 0;
    this.annotationsSignal.set([]);
    this.errorSignal.set(null);
  }

  loadAnnotations(projectId: number): void {
    this.loadingSignal.set(true);
    this.errorSignal.set(null);
    this.http.get<Annotation[]>(`/api/v1/projects/${projectId}/annotations`).pipe(
      catchError(() => {
        this.errorSignal.set('Erro ao carregar anotacoes');
        return of([]);
      })
    ).subscribe(list => {
      this.annotationsSignal.set(list);
      this.loadingSignal.set(false);
    });
  }

  createAnnotation(projectId: number, request: CreateAnnotationRequest): Observable<Annotation> {
    return this.http.post<Annotation>(`/api/v1/projects/${projectId}/annotations`, request).pipe(
      tap(created => {
        this.annotationsSignal.update(list => [created, ...list]);
      })
    );
  }

  deleteAnnotation(projectId: number, annotationId: number): Observable<void> {
    return this.http.delete<void>(`/api/v1/projects/${projectId}/annotations/${annotationId}`).pipe(
      tap(() => {
        this.annotationsSignal.update(list => list.filter(a => a.id !== annotationId));
      })
    );
  }

  updateAnnotation(projectId: number, annotationId: number, text: string): Observable<Annotation> {
    return this.http.patch<Annotation>(`/api/v1/projects/${projectId}/annotations/${annotationId}`, { text }).pipe(
      tap(updated => {
        this.annotationsSignal.update(list => list.map(a => a.id === annotationId ? updated : a));
      })
    );
  }

  private handleWebSocketMessage(msg: { type: string; data?: unknown }): void {
    if (msg.type === 'ANNOTATION_CREATED') {
      const annotation = msg.data as Annotation;
      const exists = this.annotationsSignal().some(a => a.id === annotation.id);
      if (!exists) {
        this.annotationsSignal.update(list => [annotation, ...list]);
      }
    } else if (msg.type === 'ANNOTATION_DELETED') {
      const deletedId = msg.data as number;
      this.annotationsSignal.update(list => list.filter(a => a.id !== deletedId));
    } else if (msg.type === 'ANNOTATION_UPDATED') {
      const annotation = msg.data as Annotation;
      this.annotationsSignal.update(list => list.map(a => a.id === annotation.id ? annotation : a));
    }
  }
}
