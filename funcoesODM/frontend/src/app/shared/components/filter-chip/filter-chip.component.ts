import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-filter-chip',
  standalone: true,
  imports: [CommonModule],
  template: `
    <span class="filter-chip" [class.removable]="removable">
      <span class="chip-label">{{ label }}:</span>
      <span class="chip-value">{{ value }}</span>
      <button 
        *ngIf="removable" 
        class="chip-remove" 
        (click)="remove.emit()"
        title="Remover filtro"
      >
        ×
      </button>
    </span>
  `,
  styles: [`
    .filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      padding: 0.25rem 0.625rem;
      background: var(--color-primary-bg);
      border: 1px solid var(--color-primary);
      border-radius: 9999px;
      font-size: 0.8rem;
      color: var(--color-primary);
    }

    .chip-label {
      font-weight: 500;
      opacity: 0.8;
    }

    .chip-value {
      font-weight: 600;
    }

    .chip-remove {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      padding: 0;
      margin-left: 0.125rem;
      background: var(--color-primary);
      color: white;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      font-size: 0.875rem;
      line-height: 1;
      transition: all 0.15s;
    }

    .chip-remove:hover {
      background: var(--color-primary-dark, #2563eb);
      transform: scale(1.1);
    }
  `]
})
export class FilterChipComponent {
  @Input() label = '';
  @Input() value = '';
  @Input() removable = true;
  @Output() remove = new EventEmitter<void>();
}
