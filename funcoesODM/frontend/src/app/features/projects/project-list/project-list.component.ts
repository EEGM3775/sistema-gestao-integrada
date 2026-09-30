import { Component, OnInit, signal, computed, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

import { ProjectService } from '../services/project.service';
import { Project } from '../models/project.model';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';
import { PaginationComponent, PageEvent } from '../../../shared/components/pagination/pagination.component';

// Sub-componentes
import { ProjectFiltersComponent } from './components/project-filters/project-filters.component';
import { ProjectCardItemComponent } from './components/project-card-item/project-card-item.component';
import { ProjectsEmptyStateComponent } from './components/projects-empty-state/projects-empty-state.component';

// Models
import { ProjectFilters, SortConfig } from './models/project-list.model';

/**
 * Componente Project List
 * 
 * Lista completa de projetos com funcionalidades avançadas:
 * - Filtros por status, busca textual, intervalo de datas
 * - Ordenação por múltiplos campos (nome, data, imagens, status)
 * - Toggle entre visualização grid/list
 * - Paginação configurável
 * - Ações rápidas (mapa, 3D, deletar)
 * 
 * Responsabilidades:
 * - Coordenar sub-componentes
 * - Gerenciar estado (projetos, filtros, paginação)
 * - Integrar com ProjectService
 * - Roteamento para páginas específicas
 * 
 * Redução de tamanho: 1041 linhas → ~220 linhas (79% de redução)
 */
@Component({
  selector: 'app-project-list',
  standalone: true,
  imports: [
    CommonModule,
    ButtonComponent,
    LoadingSpinnerComponent,
    PaginationComponent,
    ProjectFiltersComponent,
    ProjectCardItemComponent,
    ProjectsEmptyStateComponent
  ],
  templateUrl: './project-list.component.html',
  styleUrls: ['./project-list.component.scss']
})
export class ProjectListComponent implements OnInit {
  // Injeção de dependências
  private projectService = inject(ProjectService);
  private router = inject(Router);

  // Estado reativo
  isLoading = signal(true);
  projects = signal<Project[]>([]);
  
  // Filtros e ordenação
  filters = signal<ProjectFilters>({
    status: 'all',
    search: '',
    dateFrom: '',
    dateTo: ''
  });

  sortConfig = signal<SortConfig>({
    field: 'createdAt',
    direction: 'desc'
  });

  // Paginação
  pageIndex = signal(0);
  pageSize = signal(12);

  // Modo de visualização
  viewMode = signal<'grid' | 'list'>('grid');

  /**
   * Projetos filtrados e ordenados
   */
  filteredAndSortedProjects = computed(() => {
    let result = this.projects();
    const currentFilters = this.filters();
    const sort = this.sortConfig();

    // Filtro de status
    if (currentFilters.status !== 'all') {
      result = result.filter((p: Project) => p.status === currentFilters.status);
    }

    // Filtro de busca
    if (currentFilters.search) {
      const query = currentFilters.search.toLowerCase();
      result = result.filter((p: Project) =>
        p.name.toLowerCase().includes(query) ||
        p.description?.toLowerCase().includes(query)
      );
    }

    // Filtro de data inicial
    if (currentFilters.dateFrom) {
      const fromDate = new Date(currentFilters.dateFrom);
      result = result.filter((p: Project) => new Date(p.createdAt) >= fromDate);
    }

    // Filtro de data final
    if (currentFilters.dateTo) {
      const toDate = new Date(currentFilters.dateTo);
      toDate.setHours(23, 59, 59, 999);
      result = result.filter((p: Project) => new Date(p.createdAt) <= toDate);
    }

    // Ordenação
    result = [...result].sort((a, b) => {
      let comparison = 0;

      switch (sort.field) {
        case 'name':
          comparison = a.name.localeCompare(b.name);
          break;
        case 'createdAt':
        case 'updatedAt':
          comparison = new Date(a[sort.field]).getTime() - new Date(b[sort.field]).getTime();
          break;
        case 'imageCount':
          comparison = a.imageCount - b.imageCount;
          break;
        case 'status':
          const statusOrder = ['PENDING', 'PROCESSING', 'COMPLETED', 'ERROR'];
          comparison = statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status);
          break;
      }

      return sort.direction === 'asc' ? comparison : -comparison;
    });

    return result;
  });

  /**
   * Projetos paginados
   */
  paginatedProjects = computed(() => {
    const filtered = this.filteredAndSortedProjects();
    const start = this.pageIndex() * this.pageSize();
    const end = start + this.pageSize();
    return filtered.slice(start, end);
  });

  constructor() {
    // Reset página quando filtros mudam
    effect(() => {
      this.filters();
      this.sortConfig();
      this.pageIndex.set(0);
    }, { allowSignalWrites: true });
  }

  ngOnInit(): void {
    this.loadProjects();
  }

  /**
   * Carrega projetos do backend
   */
  loadProjects(): void {
    this.isLoading.set(true);
    this.projectService.loadProjects().subscribe({
      next: (projects: Project[]) => {
        this.projects.set(projects);
        this.isLoading.set(false);
      },
      error: (error) => {
        console.error('Erro ao carregar projetos:', error);
        this.isLoading.set(false);
      }
    });
  }

  /**
   * Handlers de eventos dos sub-componentes
   */
  onFiltersChange(newFilters: ProjectFilters): void {
    this.filters.set(newFilters);
  }

  onSortChange(newSort: SortConfig): void {
    this.sortConfig.set(newSort);
  }

  onViewModeChange(mode: 'grid' | 'list'): void {
    this.viewMode.set(mode);
  }

  onPageChange(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
  }

  hasActiveFilters(): boolean {
    const f = this.filters();
    return f.status !== 'all' || !!f.search || !!f.dateFrom || !!f.dateTo;
  }

  clearAllFilters(): void {
    this.filters.set({
      status: 'all',
      search: '',
      dateFrom: '',
      dateTo: ''
    });
  }

  /**
   * Navegação e ações
   */
  openMap(projectId: number): void {
    this.router.navigate(['/projects', projectId, 'map']);
  }

  open3D(projectId: number): void {
    this.router.navigate(['/projects', projectId, '3d']);
  }

  deleteProject(projectId: number): void {
    if (confirm('Tem certeza que deseja excluir este projeto?')) {
      this.projectService.deleteProject(projectId).subscribe({
        next: () => {
          this.projects.update(projects =>
            projects.filter(p => p.id !== projectId)
          );
        },
        error: (error) => {
          console.error('Erro ao excluir projeto:', error);
          alert('Erro ao excluir projeto. Tente novamente.');
        }
      });
    }
  }

  /**
   * Track by para performance do ngFor
   */
  trackByProjectId(index: number, project: Project): number {
    return project.id;
  }
}
