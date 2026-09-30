import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

type ButtonVariant = 'primary' | 'secondary' | 'success' | 'danger' | 'outline';
type ButtonSize = 'sm' | 'md' | 'lg';
type ButtonIcon = 'plus';

@Component({
  selector: 'app-button',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <a
      *ngIf="routerLink; else buttonTpl"
      [class]="getButtonClasses()"
      [routerLink]="routerLink"
      [queryParams]="queryParams"
      [fragment]="fragment || undefined"
      [attr.aria-disabled]="disabled || loading"
      [class.disabled]="disabled || loading"
      (click)="handleClick($event)"
    >
      <span *ngIf="loading" class="spinner"></span>
      <svg *ngIf="icon === 'plus'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 5v14M5 12h14"/>
      </svg>
      <span *ngIf="label">{{ label }}</span>
      <ng-content></ng-content>
    </a>
    <ng-template #buttonTpl>
      <button
        [type]="type"
        [disabled]="disabled || loading"
        [class]="getButtonClasses()"
        (click)="handleClick($event)"
      >
        <span *ngIf="loading" class="spinner"></span>
        <svg *ngIf="icon === 'plus'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        <span *ngIf="label">{{ label }}</span>
        <ng-content></ng-content>
      </button>
    </ng-template>
  `,
  styles: [`
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      border: none;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      font-family: inherit;
      text-decoration: none;
    }

    .btn:disabled,
    .btn.disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    /* Sizes */
    .btn.btn-sm {
      padding: 0.375rem 0.75rem;
      font-size: 0.875rem;
    }

    .btn.btn-md {
      padding: 0.625rem 1.25rem;
      font-size: 1rem;
    }

    .btn.btn-lg {
      padding: 0.875rem 1.75rem;
      font-size: 1.125rem;
    }

    /* Variants */
    .btn.btn-primary {
      background: var(--color-primary);
      color: white;
    }

    .btn.btn-primary:hover:not(:disabled):not(.disabled) {
      background: var(--color-primary-dark);
    }

    .btn.btn-secondary {
      background: var(--color-secondary);
      color: white;
    }

    .btn.btn-secondary:hover:not(:disabled):not(.disabled) {
      background: var(--color-secondary-light);
    }

    .btn.btn-success {
      background: var(--color-success);
      color: white;
    }

    .btn.btn-success:hover:not(:disabled):not(.disabled) {
      background: #0f9d7a;
    }

    .btn.btn-danger {
      background: var(--color-danger);
      color: white;
    }

    .btn.btn-danger:hover:not(:disabled):not(.disabled) {
      background: #d63838;
    }

    .btn.btn-outline {
      background: transparent;
      border: 2px solid var(--color-primary);
      color: var(--color-primary);
    }

    .btn.btn-outline:hover:not(:disabled):not(.disabled) {
      background: var(--color-primary);
      color: white;
    }

    .btn.btn-block {
      width: 100%;
    }

    .btn svg {
      width: 18px;
      height: 18px;
    }

    .btn.btn-cta {
      border-radius: 8px;
      font-size: 0.875rem;
      padding: 0.625rem 1.25rem;
    }

    .btn.btn-cta:hover:not(:disabled):not(.disabled) {
      transform: translateY(-1px);
      box-shadow: var(--shadow-md);
    }

    .spinner {
      width: 1rem;
      height: 1rem;
      border: 2px solid transparent;
      border-top-color: currentColor;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `]
})
export class ButtonComponent {
  @Input() variant: ButtonVariant = 'primary';
  @Input() size: ButtonSize = 'md';
  @Input() type: 'button' | 'submit' | 'reset' = 'button';
  @Input() disabled = false;
  @Input() loading = false;
  @Input() block = false;
  @Input() label?: string;
  @Input() icon?: ButtonIcon;
  @Input() cta = false;
  @Input() routerLink?: string | any[];
  @Input() queryParams?: Record<string, any>;
  @Input() fragment?: string;
  @Output() clicked = new EventEmitter<MouseEvent>();

  getButtonClasses(): string {
    const classes = ['btn', `btn-${this.variant}`, `btn-${this.size}`];
    if (this.block) classes.push('btn-block');
    if (this.cta) classes.push('btn-cta');
    return classes.join(' ');
  }

  handleClick(event: MouseEvent): void {
    if (this.disabled || this.loading) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    this.clicked.emit(event);
  }
}
