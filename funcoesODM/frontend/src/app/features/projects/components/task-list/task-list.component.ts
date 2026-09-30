import { Component, inject, signal, input, output, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TaskService, ProcessingTask, TaskStatus } from '../../services/task.service';
import { WebSocketService, ProgressMessage } from '../../../../core/services/websocket.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-task-list',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="task-list" [class.compact]="mode() === 'compact'">
      @if (loading()) {
        <div class="loading">
          <div class="spinner"></div>
          <p>Carregando...</p>
        </div>
      } @else if (tasks().length === 0) {
        <div class="empty-state">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
          <p>Nenhum processamento</p>
          <button class="start-btn" (click)="startProcessing()">
            ▶️ Iniciar
          </button>
        </div>
      } @else {
        <div class="tasks-header">
          <span>{{ mode() === 'compact' ? 'Chunks' : tasks().length + ' tarefa(s)' }}</span>
          <button class="start-btn small" (click)="startProcessing()" title="Nova Tarefa">
            {{ mode() === 'compact' ? '+' : '+ Nova Tarefa' }}
          </button>
        </div>

        <div class="tasks-container">
          @for (task of tasks(); track task.id) {
            @if (mode() === 'compact') {
              <div 
                class="chunk-item" 
                [class.selected]="isSelected(task)"
                (click)="selectTask(task)"
              >
                <div class="chunk-row">
                  <span class="chunk-icon">📦</span>
                  <span class="chunk-name">{{ task.name || 'Chunk ' + task.id }}</span>
                  @if (task.status === 'RUNNING') {
                    <span class="chunk-progress">{{ task.progress }}%</span>
                  }
                  <span class="chunk-status-dot" [class]="getStatusClass(task.status)" [title]="getStatusLabel(task.status)"></span>
                </div>
                @if (isSelected(task) && (task.status === 'COMPLETED' || task.status === 'COMPLETED_WITH_WARNINGS')) {
                  <div class="chunk-details">
                    <div class="chunk-detail-item">📷 Cameras ({{ task.imagesCount || 0 }})</div>
                    @if (task.outputs?.orthophoto) { <div class="chunk-detail-item">🗺️ Ortofoto</div> }
                    @if (task.outputs?.dsm) { <div class="chunk-detail-item">🗻 DSM</div> }
                    @if (task.outputs?.pointCloud) { <div class="chunk-detail-item">☁️ Nuvem de Pontos</div> }
                    @if (task.outputs?.model3d) { <div class="chunk-detail-item">🎲 Modelo 3D</div> }
                  </div>
                }
              </div>
            } @else {
              <div 
                class="task-card" 
                [class]="getStatusClass(task.status)"
                [class.selected]="isSelected(task)"
                (click)="selectTask(task)"
              >
                <div class="task-header">
                  <div class="task-info">
                    <h4>{{ task.name || 'Tarefa #' + task.id }}</h4>
                    <span class="task-status">{{ getStatusLabel(task.status) }}</span>
                  </div>
                  @if (task.status === 'RUNNING') {
                    <button class="cancel-btn" (click)="cancelTask(task.id); $event.stopPropagation()">
                      ✕ Cancelar
                    </button>
                  }
                  @if (task.status === 'COMPLETED' || task.status === 'COMPLETED_WITH_WARNINGS') {
                    <button class="view-btn" (click)="selectTask(task); $event.stopPropagation()">
                      👁️ Ver Resultados
                    </button>
                  }
                </div>

                @if (task.status === 'RUNNING' || task.status === 'QUEUED') {
                  <div class="task-progress">
                    <div class="progress-bar-container">
                      <div 
                        class="progress-bar" 
                        [style.width.%]="task.progress"
                        [class.animated]="task.status === 'RUNNING'"
                      ></div>
                    </div>
                    <span class="progress-text">{{ task.progress }}%</span>
                  </div>
                  @if (task.statusMessage) {
                    <p class="status-message">{{ task.statusMessage }}</p>
                  }
                }

                @if ((task.status === 'COMPLETED' || task.status === 'COMPLETED_WITH_WARNINGS') && task.outputs) {
                  <div class="task-outputs">
                    <span class="outputs-label">Resultados:</span>
                    <div class="output-buttons">
                      @if (task.outputs.orthophoto) {
                        <button class="output-btn">📷 Ortofoto</button>
                      }
                      @if (task.outputs.dsm) {
                        <button class="output-btn">🗻 DSM</button>
                      }
                      @if (task.outputs.dtm) {
                        <button class="output-btn">📊 DTM</button>
                      }
                      @if (task.outputs.pointCloud) {
                        <button class="output-btn">☁️ Nuvem</button>
                      }
                      @if (task.outputs.model3d) {
                        <button class="output-btn">🎲 3D</button>
                      }
                      @if (task.outputs.report) {
                        <button class="output-btn">📄 Relatório</button>
                      }
                    </div>
                  </div>
                }

                @if (task.status === 'FAILED' && task.errorMessage) {
                  <p class="error-message">{{ task.errorMessage }}</p>
                }

                <div class="task-meta">
                  <span>Criado: {{ task.createdAt | date:'dd/MM/yyyy HH:mm' }}</span>
                  @if (task.completedAt) {
                    <span>Concluído: {{ task.completedAt | date:'dd/MM/yyyy HH:mm' }}</span>
                  }
                </div>
              </div>
            }
          }
        </div>
      }
    </div>
  `,
  styles: [`
    :host {
      display: block;
      height: 100%;
      overflow-y: auto;
      background-color: #1e1e1e; /* Dark background */
      color: #e0e0e0; /* Light text */
    }

    .task-list {
      width: 100%;
    }

    .loading, .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: #a0a0a0;
    }

    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid #3e3e42;
      border-top-color: #007acc;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 16px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .empty-state svg {
      margin-bottom: 16px;
      opacity: 0.5;
      color: #a0a0a0;
    }

    .start-btn {
      margin-top: 16px;
      padding: 10px 20px;
      background: #007acc;
      color: white;
      border: none;
      border-radius: 4px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .start-btn:hover {
      background: #0063a5;
    }

    .start-btn.small {
      margin: 0;
      padding: 6px 12px;
      font-size: 13px;
    }

    .tasks-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding: 0 4px;
      color: #e0e0e0;
    }

    .tasks-container {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .task-card {
      padding: 16px;
      background: #252526;
      border: 1px solid #3e3e42;
      border-radius: 4px;
      margin-bottom: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
    }

    .task-card:hover {
      background: #2d2d2d;
      border-color: #505050;
    }

    .task-card.selected {
      border-color: #007acc;
      background: #2d2d2d;
      box-shadow: inset 3px 0 0 0 #007acc;
    }

    .task-card.status-running {
      border-left: 3px solid #007acc;
    }

    .task-card.status-completed {
      border-left: 3px solid #10b981;
    }

    .task-card.status-warning {
      border-left: 3px solid #f59e0b;
    }

    .task-card.status-failed {
      border-left: 3px solid #ef4444;
    }

    .task-card.status-canceled {
      opacity: 0.6;
      background: #1e1e1e;
    }

    .task-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }

    .task-info h4 {
      margin: 0 0 4px;
      font-size: 14px;
      font-weight: 600;
      color: #e0e0e0;
    }

    .task-status {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 10px;
      background: #3e3e42;
      color: #cccccc;
      text-transform: uppercase;
    }

    .status-running .task-status {
      background: rgba(0, 122, 204, 0.2);
      color: #61dafb;
    }

    .status-completed .task-status {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
    }

    .status-warning .task-status {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
    }

    .status-failed .task-status {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
    }

    .cancel-btn {
      padding: 4px 8px;
      background: none;
      border: 1px solid #ef4444;
      color: #ef4444;
      border-radius: 3px;
      font-size: 11px;
      cursor: pointer;
      text-transform: uppercase;
    }

    .cancel-btn:hover {
      background: #ef4444;
      color: white;
    }

    .view-btn {
      padding: 4px 10px;
      background: #007acc;
      border: none;
      color: white;
      border-radius: 3px;
      font-size: 11px;
      cursor: pointer;
      transition: background 0.2s;
      text-transform: uppercase;
    }

    .view-btn:hover {
      background: #0063a5;
    }

    .task-progress {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 8px;
    }

    .progress-bar-container {
      flex: 1;
      height: 6px;
      background: #3e3e42;
      border-radius: 3px;
      overflow: hidden;
    }

    .progress-bar {
      height: 100%;
      background: #007acc;
      border-radius: 3px;
      transition: width 0.3s ease;
    }

    .progress-bar.animated {
      background: linear-gradient(
        90deg,
        #007acc 0%,
        #4fc1ff 50%,
        #007acc 100%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
    }

    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }

    .progress-text {
      font-size: 12px;
      font-weight: 500;
      color: #007acc;
      min-width: 35px;
      text-align: right;
    }

    .status-message {
      font-size: 12px;
      color: #a0a0a0;
      margin: 0 0 12px;
      font-style: italic;
    }

    .task-outputs {
      margin: 12px 0;
      padding-top: 12px;
      border-top: 1px solid #3e3e42;
    }

    .outputs-label {
      font-size: 11px;
      color: #a0a0a0;
      display: block;
      margin-bottom: 8px;
      text-transform: uppercase;
    }

    .output-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .output-btn {
      padding: 6px 12px;
      background: #2d2d2d;
      border: 1px solid #3e3e42;
      border-radius: 3px;
      font-size: 11px;
      color: #cccccc;
      cursor: pointer;
      transition: all 0.2s;
    }

    .output-btn:hover {
      border-color: #007acc;
      color: #007acc;
      background: #333333;
    }

    .error-message {
      font-size: 12px;
      color: #f87171;
      margin: 8px 0;
      padding: 8px;
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.2);
      border-radius: 4px;
    }

    .task-meta {
      display: flex;
      gap: 16px;
      font-size: 11px;
      color: #808080;
      margin-top: 12px;
      padding-top: 8px;
      border-top: 1px solid #3e3e42;
    }

    /* Compact Mode Styles */
    .task-list.compact {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: #1e1e1e;
    }

    .task-list.compact .tasks-header {
      padding: 8px 12px;
      margin: 0;
      background: #252526;
      border-bottom: 1px solid #3e3e42;
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #cccccc;
    }

    .task-list.compact .tasks-container {
      flex: 1;
      overflow-y: auto;
      padding: 4px;
    }

    .chunk-item {
      padding: 6px 8px;
      border-radius: 3px;
      cursor: pointer;
      margin-bottom: 2px;
      font-size: 12px;
      color: #cccccc;
      border: 1px solid transparent;
    }

    .chunk-item:hover {
      background: #2d2d2d;
      border-color: #3e3e42;
    }

    .chunk-item.selected {
      background: #37373d;
      color: #ffffff;
      border-color: #007acc;
    }

    .chunk-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .chunk-icon {
      font-size: 14px;
      opacity: 0.7;
    }

    .chunk-name {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .chunk-progress {
      font-size: 11px;
      color: #808080;
    }

    .chunk-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #505050;
    }

    .chunk-status-dot.status-running { background: #007acc; box-shadow: 0 0 4px #007acc; }
    .chunk-status-dot.status-completed { background: #10b981; }
    .chunk-status-dot.status-warning { background: #f59e0b; }
    .chunk-status-dot.status-failed { background: #ef4444; }

    .chunk-details {
      margin-top: 4px;
      margin-left: 22px;
      padding-left: 8px;
      border-left: 1px solid #3e3e42;
    }

    .chunk-detail-item {
      padding: 2px 0;
      font-size: 11px;
      color: #a0a0a0;
      display: flex;
      align-items: center;
      gap: 6px;
    }
  `]
})
export class TaskListComponent implements OnInit, OnDestroy {
  private readonly taskService = inject(TaskService);
  private readonly wsService = inject(WebSocketService);
  private subscription?: Subscription;

  // Input
  projectId = input.required<number>();
  mode = input<'default' | 'compact'>('default');

  // Output
  taskSelected = output<ProcessingTask>();

  // State
  tasks = signal<ProcessingTask[]>([]);
  loading = signal(true);
  selectedTaskId = signal<number | null>(null);

  ngOnInit(): void {
    this.loadTasks();
    this.subscribeToProgress();
  }

  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
    this.wsService.unsubscribeFromProject(this.projectId());
  }

  loadTasks(): void {
    this.loading.set(true);
    this.taskService.getProjectTasks(this.projectId()).subscribe({
      next: (tasks) => {
        this.tasks.set(tasks);
        this.loading.set(false);
      },
      error: (error) => {
        console.error('Failed to load tasks:', error);
        this.loading.set(false);
      }
    });
  }

  subscribeToProgress(): void {
    // Connect to WebSocket if not connected
    if (!this.wsService.isConnected()) {
      this.wsService.connect();
    }

    // Subscribe to project progress
    this.subscription = this.wsService.subscribeToProject(this.projectId())
      .subscribe(message => {
        if (message) {
          this.handleProgressMessage(message);
        }
      });
  }

  handleProgressMessage(message: ProgressMessage): void {
    const taskId = message.taskId;
    
    this.tasks.update(tasks => 
      tasks.map(task => {
        if (task.id === taskId) {
          const newStatus = this.mapStatus(message.status);
          
          // When task completes (with or without warnings), the outputs come in message.data
          const isCompleted = newStatus === 'COMPLETED' || newStatus === 'COMPLETED_WITH_WARNINGS';
          const outputs = isCompleted && message.data 
            ? message.data as any 
            : task.outputs;
          
          return {
            ...task,
            progress: message.progress,
            status: newStatus,
            statusMessage: message.message,
            outputs: outputs
          };
        }
        return task;
      })
    );

    // When a task completes (with or without warnings), reload tasks from server to ensure we have fresh data
    if (message.status === 'COMPLETED' || message.status === 'COMPLETED_WITH_WARNINGS') {
      setTimeout(() => this.loadTasks(), 500);
    }
  }

  mapStatus(status: string): TaskStatus {
    const mapping: Record<string, TaskStatus> = {
      'RUNNING': 'RUNNING',
      'COMPLETED': 'COMPLETED',
      'COMPLETED_WITH_WARNINGS': 'COMPLETED_WITH_WARNINGS',
      'FAILED': 'FAILED',
      'CANCELED': 'CANCELED',
      'QUEUED': 'QUEUED'
    };
    return mapping[status] || 'QUEUED';
  }

  startProcessing(): void {
    this.taskService.createTask(this.projectId()).subscribe({
      next: (task) => {
        this.tasks.update(tasks => [task, ...tasks]);
      },
      error: (error) => {
        console.error('Failed to create task:', error);
        alert(error.error?.error || 'Erro ao iniciar processamento');
      }
    });
  }

  cancelTask(taskId: number): void {
    if (confirm('Tem certeza que deseja cancelar esta tarefa?')) {
      this.taskService.cancelTask(this.projectId(), taskId).subscribe({
        next: () => {
          this.tasks.update(tasks =>
            tasks.map(t => t.id === taskId ? { ...t, status: 'CANCELED' as TaskStatus } : t)
          );
        }
      });
    }
  }

  getStatusLabel(status: TaskStatus): string {
    return this.taskService.getStatusLabel(status);
  }

  getStatusClass(status: TaskStatus): string {
    return this.taskService.getStatusClass(status);
  }

  selectTask(task: ProcessingTask): void {
    this.selectedTaskId.set(task.id);
    this.taskSelected.emit(task);
  }

  isSelected(task: ProcessingTask): boolean {
    return this.selectedTaskId() === task.id;
  }
}
