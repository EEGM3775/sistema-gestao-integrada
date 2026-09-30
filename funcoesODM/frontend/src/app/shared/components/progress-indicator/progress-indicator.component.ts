import { Component, input, computed } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-progress-indicator',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="progress-indicator" [class]="status()">
      <div class="progress-header">
        <span class="progress-label">{{ label() }}</span>
        <span class="progress-percentage">{{ progress() }}%</span>
      </div>
      
      <div class="progress-bar-container">
        <div 
          class="progress-bar" 
          [style.width.%]="progress()"
          [class.animated]="isAnimated()"
        ></div>
      </div>
      
      @if (message()) {
        <p class="progress-message">{{ message() }}</p>
      }

      @if (showStages() && stages().length > 0) {
        <div class="stages-list">
          @for (stage of stages(); track stage.name; let i = $index) {
            <div class="stage-item" [class.completed]="i < currentStageIndex()" [class.current]="i === currentStageIndex()">
              <span class="stage-icon">
                @if (i < currentStageIndex()) {
                  ✓
                } @else if (i === currentStageIndex()) {
                  ●
                } @else {
                  ○
                }
              </span>
              <span class="stage-name">{{ stage.name }}</span>
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .progress-indicator {
      padding: 16px;
      background: var(--bg-secondary, #f9fafb);
      border-radius: 8px;
      border: 1px solid var(--border-color, #e5e7eb);
    }

    .progress-indicator.running {
      border-color: var(--primary-color, #3b82f6);
      background: #eff6ff;
    }

    .progress-indicator.completed {
      border-color: var(--success-color, #10b981);
      background: #ecfdf5;
    }

    .progress-indicator.failed {
      border-color: var(--error-color, #ef4444);
      background: #fef2f2;
    }

    .progress-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }

    .progress-label {
      font-weight: 500;
      color: var(--text-primary, #111827);
    }

    .progress-percentage {
      font-size: 14px;
      font-weight: 600;
      color: var(--primary-color, #3b82f6);
    }

    .progress-bar-container {
      width: 100%;
      height: 8px;
      background: var(--border-color, #e5e7eb);
      border-radius: 4px;
      overflow: hidden;
    }

    .progress-bar {
      height: 100%;
      background: var(--primary-color, #3b82f6);
      border-radius: 4px;
      transition: width 0.3s ease;
    }

    .progress-bar.animated {
      background: linear-gradient(
        90deg,
        var(--primary-color, #3b82f6) 0%,
        #60a5fa 50%,
        var(--primary-color, #3b82f6) 100%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
    }

    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }

    .progress-message {
      margin: 8px 0 0;
      font-size: 13px;
      color: var(--text-secondary, #6b7280);
    }

    .completed .progress-bar {
      background: var(--success-color, #10b981);
    }

    .failed .progress-bar {
      background: var(--error-color, #ef4444);
    }

    .stages-list {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid var(--border-color, #e5e7eb);
    }

    .stage-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 0;
      font-size: 13px;
      color: var(--text-secondary, #9ca3af);
    }

    .stage-item.completed {
      color: var(--success-color, #10b981);
    }

    .stage-item.current {
      color: var(--primary-color, #3b82f6);
      font-weight: 500;
    }

    .stage-icon {
      width: 16px;
      text-align: center;
    }
  `]
})
export class ProgressIndicatorComponent {
  // Inputs
  progress = input<number>(0);
  label = input<string>('Progresso');
  message = input<string>('');
  status = input<'idle' | 'running' | 'completed' | 'failed'>('idle');
  showStages = input<boolean>(false);
  stages = input<{ name: string; completed?: boolean }[]>([]);
  currentStage = input<number>(0);

  // Computed
  isAnimated = computed(() => this.status() === 'running' && this.progress() < 100);
  currentStageIndex = computed(() => this.currentStage());
}
