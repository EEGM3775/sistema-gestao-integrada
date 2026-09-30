import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { ProjectService } from '../../projects/services/project.service';
import { Project } from '../../projects/models/project.model';

// Sub-componentes
import { StatsBarComponent } from './components/stats-bar/stats-bar.component';
import { SearchHeaderComponent } from './components/search-header/search-header.component';
import { ProjectGridComponent } from './components/project-grid/project-grid.component';
import { ProjectListComponent } from './components/project-list/project-list.component';

// Models
import { ProjectUI, ViewMode } from './models/dashboard.model';

/**
 * Componente Dashboard Home
 * 
 * Dashboard principal da aplicação que exibe todos os projetos do usuário.
 * 
 * Funcionalidades:
 * - Listar todos os projetos (grid ou lista)
 * - Buscar projetos por nome ou descrição
 * - Toggle entre visualização grid/list
 * - Estatísticas de projetos (total, processando, concluídos, imagens)
 * - Navegação para detalhes do projeto
 * - Ações rápidas (mapa, download, menu)
 * 
 * Responsabilidades:
 * - Coordenar sub-componentes
 * - Gerenciar estado da aplicação (projetos, busca, visualização)
 * - Integrar com ProjectService para carregar projetos
 * - Roteamento para páginas de detalhes
 * 
 * Redução de tamanho: 1161 linhas → ~250 linhas (78% de redução)
 */
@Component({
  selector: 'app-dashboard-home',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    StatsBarComponent,
    SearchHeaderComponent,
    ProjectGridComponent,
    ProjectListComponent
  ],
  templateUrl: './dashboard-home.component.html',
  styleUrls: ['./dashboard-home.component.scss']
})
export class DashboardHomeComponent implements OnInit {
  // Injeção de dependências
  private projectService = inject(ProjectService);
  private router = inject(Router);
  public authService = inject(AuthService);

  // Estado reativo com signals
  isLoading = signal(true);
  searchTerm = signal('');
  viewMode = signal<ViewMode>('grid');
  projectsUI = signal<ProjectUI[]>([]);
  errorMessage = signal<string | null>(null);

  /**
   * Estatísticas computadas dos projetos
   */
  stats = computed(() => ({
    totalProjects: this.projectsUI().length,
    processing: this.projectsUI().filter((p: ProjectUI) => p.status === 'PROCESSING').length,
    completed: this.projectsUI().filter((p: ProjectUI) => p.status === 'COMPLETED').length,
    totalImages: this.projectsUI().reduce((sum: number, p: ProjectUI) => sum + p.imageCount, 0)
  }));

  /**
   * Projetos filtrados pela busca
   */
  filteredProjects = computed(() => {
    const term = this.searchTerm().toLowerCase();
    if (!term) return this.projectsUI();
    return this.projectsUI().filter((p: ProjectUI) =>
      p.name.toLowerCase().includes(term) ||
      (p.description?.toLowerCase().includes(term) ?? false)
    );
  });

  ngOnInit(): void {
    this.loadProjects();
  }

  /**
   * Carrega os projetos do backend
   */
  loadProjects(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.projectService.loadProjects().subscribe({
      next: (projects: Project[]) => {
        const uiProjects: ProjectUI[] = projects.map((p: Project) => this.enrichProject(p));
        this.projectsUI.set(uiProjects);
        this.isLoading.set(false);
      },
      error: (err: Error) => {
        console.error('Erro ao carregar projetos:', err);
        this.errorMessage.set('Falha ao carregar projetos. Tente novamente.');
        this.isLoading.set(false);

        // Fallback para dados mock durante desenvolvimento
        this.loadMockProjects();
      }
    });
  }

  /**
   * Enriquece o projeto com dados de UI (thumbnail, área, etc)
   */
  private enrichProject(project: Project): ProjectUI {
    const placeholder = this.getPlaceholderImage(`Projeto ${project.id}`);

    return {
      ...project,
      progress: project.status === 'COMPLETED' ? 100 : project.status === 'PROCESSING' ? 50 : 0,
      area: 'Não definida',
      thumbnail: placeholder,
      location: { lat: -23.5505, lng: -46.6333 }
    };
  }

  /**
   * Carrega dados mock como fallback
   */
  private loadMockProjects(): void {
    const placeholder = this.getPlaceholderImage('Demo');

    const mockProjects: ProjectUI[] = [
      {
        id: 1,
        name: 'Fazenda São João - Mapeamento Aéreo',
        description: 'Levantamento topográfico completo para planejamento agrícola',
        status: 'COMPLETED',
        progress: 100,
        createdAt: '2025-01-15',
        updatedAt: '2025-01-16',
        imageCount: 245,
        taskCount: 3,
        area: '150 ha',
        thumbnail: placeholder,
        location: { lat: -23.5505, lng: -46.6333 },
        owner: 'Demo'
      },
      {
        id: 2,
        name: 'Obra Residencial Parque Verde',
        description: 'Acompanhamento de obra - Etapa fundação',
        status: 'PROCESSING',
        progress: 67,
        createdAt: '2025-01-18',
        updatedAt: '2025-01-20',
        imageCount: 128,
        taskCount: 2,
        area: '2.5 ha',
        thumbnail: placeholder,
        location: { lat: -23.5605, lng: -46.6433 },
        owner: 'Demo'
      },
      {
        id: 3,
        name: 'Inspeção Torre de Transmissão',
        description: 'Inspeção estrutural de linha de alta tensão',
        status: 'PENDING',
        progress: 0,
        createdAt: '2025-01-20',
        updatedAt: '2025-01-20',
        imageCount: 89,
        taskCount: 1,
        area: '0.5 ha',
        thumbnail: placeholder,
        location: { lat: -23.5405, lng: -46.6233 },
        owner: 'Demo'
      }
    ];

    this.projectsUI.set(mockProjects);
  }

  /**
   * Gera uma imagem placeholder SVG inline
   */
  private getPlaceholderImage(label: string): string {
    return 'data:image/svg+xml,' + encodeURIComponent(`
      <svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
        <rect fill="#e2e8f0" width="400" height="300"/>
        <text x="200" y="150" text-anchor="middle" dy=".3em" fill="#94a3b8" font-family="system-ui" font-size="14">
          ${label}
        </text>
        <path d="M175 120h50v40h-50z" fill="none" stroke="#94a3b8" stroke-width="2"/>
        <circle cx="190" cy="135" r="5" fill="#94a3b8"/>
        <path d="M175 155l15-10 10 5 15-15 10 20" fill="none" stroke="#94a3b8" stroke-width="2"/>
      </svg>
    `.trim());
  }

  /**
   * Handler para mudança na busca
   */
  onSearch(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.searchTerm.set(input.value);
  }

  /**
   * Handler para mudança do modo de visualização
   */
  setViewMode(mode: ViewMode): void {
    this.viewMode.set(mode);
  }

  /**
   * Handler para erro de carregamento de imagem
   */
  onImageError(event: Event): void {
    const img = event.target as HTMLImageElement;
    img.src = this.getPlaceholderImage('Sem imagem');
  }

  /**
   * Abre a página de mapa do projeto
   */
  openMap(event: Event, project: ProjectUI): void {
    event.stopPropagation();
    this.router.navigate(['/projects', project.id]);
  }

  /**
   * Abre a página de download do projeto
   */
  download(event: Event, project: ProjectUI): void {
    event.stopPropagation();
    this.router.navigate(['/projects', project.id], { queryParams: { tab: 'downloads' } });
  }

  /**
   * Abre o menu de opções do projeto
   */
  openMenu(event: Event, project: ProjectUI): void {
    event.stopPropagation();
    this.router.navigate(['/projects', project.id]);
  }
}
