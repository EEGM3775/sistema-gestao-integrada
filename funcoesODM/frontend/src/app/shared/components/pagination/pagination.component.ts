import { Component, Input, Output, EventEmitter, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface PageEvent {
  pageIndex: number;
  pageSize: number;
  length: number;
}

@Component({
    selector: 'app-pagination',
    imports: [CommonModule],
    template: `
    <div class="pagination-container" *ngIf="totalItems() > 0">
      <div class="pagination-info">
        <span>
          Mostrando {{ startItem() }} - {{ endItem() }} de {{ totalItems() }} itens
        </span>
      </div>
      
      <div class="pagination-controls">
        <div class="page-size-selector">
          <label>Por página:</label>
          <select [value]="pageSize()" (change)="onPageSizeChange($event)">
            <option *ngFor="let size of pageSizeOptions" [value]="size">{{ size }}</option>
          </select>
        </div>

        <div class="page-buttons">
          <button 
            class="page-btn" 
            [disabled]="pageIndex() === 0"
            (click)="goToFirst()"
            title="Primeira página"
          >
            ⟨⟨
          </button>
          <button 
            class="page-btn" 
            [disabled]="pageIndex() === 0"
            (click)="goToPrevious()"
            title="Página anterior"
          >
            ⟨
          </button>

          <div class="page-numbers">
            <button 
              *ngFor="let page of visiblePages()"
              class="page-num"
              [class.active]="page === pageIndex()"
              (click)="goToPage(page)"
            >
              {{ page + 1 }}
            </button>
          </div>

          <button 
            class="page-btn" 
            [disabled]="pageIndex() >= totalPages() - 1"
            (click)="goToNext()"
            title="Próxima página"
          >
            ⟩
          </button>
          <button 
            class="page-btn" 
            [disabled]="pageIndex() >= totalPages() - 1"
            (click)="goToLast()"
            title="Última página"
          >
            ⟩⟩
          </button>
        </div>
      </div>
    </div>
  `,
    styles: [`
    .pagination-container {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem 0;
      flex-wrap: wrap;
      gap: 1rem;
    }

    .pagination-info {
      font-size: 0.875rem;
      color: var(--color-text-secondary);
    }

    .pagination-controls {
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }

    .page-size-selector {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      color: var(--color-text-secondary);
    }

    .page-size-selector select {
      padding: 0.375rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: 4px;
      background: var(--color-bg-white);
      color: var(--color-text);
      cursor: pointer;
    }

    .page-buttons {
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }

    .page-btn {
      padding: 0.375rem 0.625rem;
      border: 1px solid var(--color-border);
      background: var(--color-bg-white);
      color: var(--color-text-secondary);
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.75rem;
      font-weight: 600;
      transition: all 0.15s;
    }

    .page-btn:hover:not(:disabled) {
      background: var(--color-bg-hover);
      color: var(--color-text);
      border-color: var(--color-primary);
    }

    .page-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .page-numbers {
      display: flex;
      gap: 0.25rem;
    }

    .page-num {
      min-width: 32px;
      height: 32px;
      padding: 0 0.5rem;
      border: 1px solid var(--color-border);
      background: var(--color-bg-white);
      color: var(--color-text-secondary);
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.875rem;
      transition: all 0.15s;
    }

    .page-num:hover:not(.active) {
      background: var(--color-bg-hover);
      border-color: var(--color-primary);
    }

    .page-num.active {
      background: var(--color-primary);
      color: white;
      border-color: var(--color-primary);
    }

    @media (max-width: 640px) {
      .pagination-container {
        flex-direction: column;
        align-items: stretch;
      }

      .pagination-controls {
        justify-content: space-between;
      }
    }
  `]
})
export class PaginationComponent {
  @Input() set length(value: number) { this._length.set(value); }
  @Input() set pageSizeInput(value: number) { this._pageSize.set(value); }
  @Input() set pageIndexInput(value: number) { this._pageIndex.set(value); }
  @Input() pageSizeOptions = [6, 12, 24, 48];
  
  @Output() page = new EventEmitter<PageEvent>();

  private _length = signal(0);
  private _pageSize = signal(12);
  private _pageIndex = signal(0);

  readonly totalItems = this._length.asReadonly();
  readonly pageSize = this._pageSize.asReadonly();
  readonly pageIndex = this._pageIndex.asReadonly();

  readonly totalPages = computed(() => 
    Math.ceil(this._length() / this._pageSize()) || 1
  );

  readonly startItem = computed(() => 
    this._length() === 0 ? 0 : this._pageIndex() * this._pageSize() + 1
  );

  readonly endItem = computed(() => 
    Math.min((this._pageIndex() + 1) * this._pageSize(), this._length())
  );

  readonly visiblePages = computed(() => {
    const total = this.totalPages();
    const current = this._pageIndex();
    const pages: number[] = [];
    
    // Mostra até 5 páginas centradas na atual
    let start = Math.max(0, current - 2);
    let end = Math.min(total - 1, current + 2);

    // Ajusta para sempre mostrar 5 páginas se possível
    if (end - start < 4) {
      if (start === 0) {
        end = Math.min(total - 1, 4);
      } else {
        start = Math.max(0, total - 5);
      }
    }

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    
    return pages;
  });

  private emitPageEvent(): void {
    this.page.emit({
      pageIndex: this._pageIndex(),
      pageSize: this._pageSize(),
      length: this._length()
    });
  }

  onPageSizeChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    const newSize = parseInt(select.value, 10);
    this._pageSize.set(newSize);
    this._pageIndex.set(0); // Reset to first page
    this.emitPageEvent();
  }

  goToPage(page: number): void {
    if (page >= 0 && page < this.totalPages()) {
      this._pageIndex.set(page);
      this.emitPageEvent();
    }
  }

  goToFirst(): void {
    this.goToPage(0);
  }

  goToPrevious(): void {
    this.goToPage(this._pageIndex() - 1);
  }

  goToNext(): void {
    this.goToPage(this._pageIndex() + 1);
  }

  goToLast(): void {
    this.goToPage(this.totalPages() - 1);
  }
}
