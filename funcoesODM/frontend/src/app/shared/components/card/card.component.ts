import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-card',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card" [class.clickable]="clickable" [class.elevated]="elevated">
      <div class="card-header" *ngIf="title || subtitle">
        <h3 class="card-title" *ngIf="title">{{ title }}</h3>
        <p class="card-subtitle" *ngIf="subtitle">{{ subtitle }}</p>
      </div>
      <div class="card-content">
        <ng-content></ng-content>
      </div>
      <div class="card-footer" *ngIf="showFooter">
        <ng-content select="[card-footer]"></ng-content>
      </div>
    </div>
  `,
  styles: [`
    .card {
      background: var(--color-bg-white);
      border-radius: var(--radius-lg);
      border: 1px solid var(--color-border);
      box-shadow: var(--shadow-sm);
      overflow: hidden;
      transition: box-shadow 0.2s ease, transform 0.2s ease;
    }

    .card.elevated {
      box-shadow: var(--shadow-lg);
    }

    .card.clickable {
      cursor: pointer;
    }

    .card.clickable:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
    }

    .card-header {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--color-border);
    }

    .card-title {
      margin: 0;
      font-size: 1.125rem;
      font-weight: 600;
      color: var(--color-text);
    }

    .card-subtitle {
      margin: 0.25rem 0 0;
      font-size: 0.875rem;
      color: var(--color-text-secondary);
    }

    .card-content {
      padding: 1.25rem;
    }

    .card-footer {
      padding: 0.75rem 1.25rem;
      background: var(--color-bg);
      border-top: 1px solid var(--color-border);
    }
  `]
})
export class CardComponent {
  @Input() title?: string;
  @Input() subtitle?: string;
  @Input() clickable = false;
  @Input() elevated = false;
  @Input() showFooter = false;
}
