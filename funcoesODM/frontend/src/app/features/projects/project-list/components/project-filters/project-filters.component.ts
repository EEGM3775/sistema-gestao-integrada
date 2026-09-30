import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { FilterChipComponent } from '../../../../../shared/components/filter-chip/filter-chip.component';
import { ProjectFilters, SortConfig, SortField, SortDirection } from '../../models/project-list.model';

/**
 * Componente Project Filters
 * 
 * Barra de filtros avançados para listagem de projetos:
 * - Busca por texto
 * - Filtro por status
 * - Filtro por intervalo de datas
 * - Ordenação por campo e direção
 * - Visualização grid/list
 * - Chips de filtros ativos
 * 
 * Responsabilidades:
 * - Renderizar controles de filtro
 * - Emitir eventos de mudança de filtros
 * - Exibir chips removíveis de filtros ativos
 * - Toggle entre visualizações
 */
@Component({
  selector: 'app-project-filters',
  standalone: true,
  imports: [CommonModule, FormsModule, FilterChipComponent],
  templateUrl: './project-filters.component.html',
  styleUrls: ['./project-filters.component.scss']
})
export class ProjectFiltersComponent {
  @Input({ required: true }) filters!: ProjectFilters;
  @Input({ required: true }) sortConfig!: SortConfig;
  @Input({ required: true }) viewMode!: 'grid' | 'list';
  @Input() resultsCount: number = 0;
  @Input() totalCount: number = 0;

  @Output() filtersChange = new EventEmitter<ProjectFilters>();
  @Output() sortChange = new EventEmitter<SortConfig>();
  @Output() viewModeChange = new EventEmitter<'grid' | 'list'>();
  @Output() clearAll = new EventEmitter<void>();

  statusOptions = [
    { label: 'Pendente', value: 'PENDING' },
    { label: 'Processando', value: 'PROCESSING' },
    { label: 'Concluído', value: 'COMPLETED' },
    { label: 'Erro', value: 'ERROR' }
  ];

  sortOptions = [
    { label: 'Data de Criação', value: 'createdAt' },
    { label: 'Nome', value: 'name' },
    { label: 'Última Atualização', value: 'updatedAt' },
    { label: 'Número de Imagens', value: 'imageCount' },
    { label: 'Status', value: 'status' }
  ];

  onSearch(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.filtersChange.emit({ ...this.filters, search: input.value });
  }

  clearSearch(): void {
    this.filtersChange.emit({ ...this.filters, search: '' });
  }

  onStatusChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    this.filtersChange.emit({ ...this.filters, status: select.value });
  }

  onDateFromChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.filtersChange.emit({ ...this.filters, dateFrom: input.value });
  }

  onDateToChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.filtersChange.emit({ ...this.filters, dateTo: input.value });
  }

  onSortFieldChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    this.sortChange.emit({ 
      ...this.sortConfig, 
      field: select.value as SortField 
    });
  }

  toggleSortDirection(): void {
    const newDirection: SortDirection = 
      this.sortConfig.direction === 'asc' ? 'desc' : 'asc';
    this.sortChange.emit({ ...this.sortConfig, direction: newDirection });
  }

  setViewMode(mode: 'grid' | 'list'): void {
    this.viewModeChange.emit(mode);
  }

  hasActiveFilters(): boolean {
    return this.filters.status !== 'all' || 
           !!this.filters.search || 
           !!this.filters.dateFrom || 
           !!this.filters.dateTo;
  }

  removeFilter(type: 'status' | 'search' | 'dateFrom' | 'dateTo'): void {
    const updated = { ...this.filters };
    if (type === 'status') updated.status = 'all';
    else if (type === 'search') updated.search = '';
    else if (type === 'dateFrom') updated.dateFrom = '';
    else if (type === 'dateTo') updated.dateTo = '';
    this.filtersChange.emit(updated);
  }

  clearAllFilters(): void {
    this.clearAll.emit();
  }

  getStatusLabel(value: string): string {
    const option = this.statusOptions.find(o => o.value === value);
    return option?.label || value;
  }
}
