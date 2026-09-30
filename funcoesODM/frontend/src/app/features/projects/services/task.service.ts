import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap, map } from 'rxjs/operators';

export interface ProcessingTask {
  id: number;
  projectId: number;
  name: string;
  status: TaskStatus;
  progress: number;
  statusMessage: string;
  nodeodmTaskId?: string;
  options?: string;
  outputs?: TaskOutputs;
  errorMessage?: string;
  warningMessage?: string;  // Non-critical warnings during processing
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  imagesCount?: number;
}

export type TaskStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'COMPLETED_WITH_WARNINGS' | 'FAILED' | 'CANCELED';

export interface TaskOutputs {
  orthophoto?: string;
  dsm?: string;
  dtm?: string;
  pointCloud?: string;
  model3d?: string;
  report?: string;
}

export interface CreateTaskRequest {
  name?: string;
  options?: Record<string, any>;
}

@Injectable({
  providedIn: 'root'
})
export class TaskService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api/v1/projects';

  // Current tasks state
  private tasksSubject = new BehaviorSubject<ProcessingTask[]>([]);
  tasks$ = this.tasksSubject.asObservable();

  // Loading state
  loading = signal(false);

  /**
   * Parse outputs from string JSON to object if needed
   * Handles various edge cases including malformed JSON
   */
  private parseTaskOutputs(task: any): ProcessingTask {
    if (task.outputs) {
      if (typeof task.outputs === 'string') {
        try {
          // Try standard JSON parse first
          task.outputs = JSON.parse(task.outputs);
        } catch (e) {
          // Try to fix common JSON issues
          try {
            // Remove escaped backslashes that shouldn't be there
            let fixed = task.outputs
              .replace(/\\:/g, ':')
              .replace(/\\\//g, '/')
              .replace(/\\,/g, ',')
              .replace(/\\\\/g, '\\');
            
            // Try parsing the fixed string
            task.outputs = JSON.parse(fixed);
          } catch (e2) {
            console.warn('Failed to parse task outputs, setting to empty:', e);
            task.outputs = {};
          }
        }
      }
      // If outputs is already an object, keep it
    } else {
      task.outputs = {};
    }
    return task as ProcessingTask;
  }

  /**
   * Get all tasks for a project
   */
  getProjectTasks(projectId: number): Observable<ProcessingTask[]> {
    this.loading.set(true);
    return this.http.get<any[]>(`${this.apiUrl}/${projectId}/tasks`).pipe(
      map(tasks => tasks.map(t => this.parseTaskOutputs(t))),
      tap({
        next: tasks => {
          this.tasksSubject.next(tasks);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
        }
      })
    );
  }

  /**
   * Get a specific task
   */
  getTask(projectId: number, taskId: number): Observable<ProcessingTask> {
    return this.http.get<any>(`${this.apiUrl}/${projectId}/tasks/${taskId}`).pipe(
      map(task => this.parseTaskOutputs(task))
    );
  }

  /**
   * Create a new processing task
   */
  createTask(projectId: number, request?: CreateTaskRequest): Observable<ProcessingTask> {
    this.loading.set(true);
    return this.http.post<ProcessingTask>(
      `${this.apiUrl}/${projectId}/tasks`,
      request || { name: 'Processamento ODM' }
    ).pipe(
      tap({
        next: task => {
          const currentTasks = this.tasksSubject.value;
          this.tasksSubject.next([task, ...currentTasks]);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
        }
      })
    );
  }

  /**
   * Cancel a task
   */
  cancelTask(projectId: number, taskId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/${projectId}/tasks/${taskId}/cancel`, {}).pipe(
      tap(() => {
        // Update local state
        const tasks = this.tasksSubject.value.map(t => 
          t.id === taskId ? { ...t, status: 'CANCELED' as TaskStatus } : t
        );
        this.tasksSubject.next(tasks);
      })
    );
  }

  /**
   * Update a task in local state (used by WebSocket updates)
   */
  updateTaskInState(taskId: number, updates: Partial<ProcessingTask>): void {
    const tasks = this.tasksSubject.value.map(t =>
      t.id === taskId ? { ...t, ...updates } : t
    );
    this.tasksSubject.next(tasks);
  }

  /**
   * Get task status label in Portuguese
   */
  getStatusLabel(status: TaskStatus): string {
    const labels: Record<TaskStatus, string> = {
      'QUEUED': 'Na Fila',
      'RUNNING': 'Executando',
      'COMPLETED': 'Concluído',
      'COMPLETED_WITH_WARNINGS': 'Concluído com Avisos',
      'FAILED': 'Falhou',
      'CANCELED': 'Cancelado'
    };
    return labels[status] || status;
  }

  /**
   * Get status color class
   */
  getStatusClass(status: TaskStatus): string {
    const classes: Record<TaskStatus, string> = {
      'QUEUED': 'status-queued',
      'RUNNING': 'status-running',
      'COMPLETED': 'status-completed',
      'COMPLETED_WITH_WARNINGS': 'status-warning',
      'FAILED': 'status-failed',
      'CANCELED': 'status-canceled'
    };
    return classes[status] || '';
  }
}
