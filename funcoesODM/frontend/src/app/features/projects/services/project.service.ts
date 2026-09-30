import { Injectable, signal, computed } from '@angular/core';
import { Observable, tap, map, catchError, of } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { ProjectContextService } from '../../../core/services/project-context.service';
import { Project, CreateProjectRequest, ProjectTask, ProjectStatus, ProjectApiResponse } from '../models/project.model';

// Interfaces para paginação e filtros
export interface ProjectQueryParams {
  page?: number;
  size?: number;
  sort?: string;
  direction?: 'asc' | 'desc';
  status?: string;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
}

export interface PagedResponse<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  size: number;
  number: number;
  first: boolean;
  last: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ProjectService {
  private projectsSignal = signal<Project[]>([]);
  private loadingSignal = signal<boolean>(false);
  private errorSignal = signal<string | null>(null);
  private totalElementsSignal = signal<number>(0);

  readonly projects = this.projectsSignal.asReadonly();
  readonly loading = this.loadingSignal.asReadonly();
  readonly error = this.errorSignal.asReadonly();
  readonly totalElements = this.totalElementsSignal.asReadonly();

  readonly completedCount = computed(() => 
    this.projectsSignal().filter(p => p.status === 'COMPLETED').length
  );
  readonly processingCount = computed(() => 
    this.projectsSignal().filter(p => p.status === 'PROCESSING').length
  );
  readonly totalImages = computed(() => 
    this.projectsSignal().reduce((sum, p) => sum + p.imageCount, 0)
  );

  constructor(private api: ApiService, private context: ProjectContextService) {}

  /**
   * Transforma resposta da API para o modelo do frontend
   */
  private mapApiToProject(apiProject: ProjectApiResponse): Project {
    return {
      id: apiProject.id,
      name: apiProject.name,
      description: apiProject.description || '',
      status: this.determineStatus(apiProject),
      createdAt: apiProject.createdAt,
      updatedAt: apiProject.createdAt, // API não tem updatedAt ainda
      taskCount: 0, // Será calculado quando tivermos tasks
      imageCount: 0, // Será calculado quando tivermos imagens
      owner: apiProject.owner?.username || 'Unknown'
    };
  }

  /**
   * Determina status do projeto (pode ser expandido baseado em tasks)
   */
  private determineStatus(apiProject: ProjectApiResponse): ProjectStatus {
    // Por enquanto, projetos novos são PENDING
    // Futuramente, isso será baseado no status das tasks
    return 'PENDING';
  }

  loadProjects(params?: ProjectQueryParams): Observable<Project[]> {
    this.loadingSignal.set(true);
    this.errorSignal.set(null);

    // Constrói query string se houver parâmetros
    let endpoint = '/projects';
    if (params) {
      const queryParams = new URLSearchParams();
      if (params.page !== undefined) queryParams.set('page', params.page.toString());
      if (params.size !== undefined) queryParams.set('size', params.size.toString());
      if (params.sort) queryParams.set('sort', params.sort);
      if (params.direction) queryParams.set('direction', params.direction);
      if (params.status && params.status !== 'all') queryParams.set('status', params.status);
      if (params.search) queryParams.set('search', params.search);
      if (params.dateFrom) queryParams.set('dateFrom', params.dateFrom);
      if (params.dateTo) queryParams.set('dateTo', params.dateTo);
      
      const queryString = queryParams.toString();
      if (queryString) {
        endpoint += `?${queryString}`;
      }
    }

    return this.api.get<ProjectApiResponse[]>(endpoint).pipe(
      map(apiProjects => apiProjects.map(p => this.mapApiToProject(p))),
      tap(projects => {
        this.projectsSignal.set(projects);
        this.totalElementsSignal.set(projects.length);
        this.loadingSignal.set(false);
      }),
      catchError(error => {
        console.error('Erro ao carregar projetos:', error);
        this.errorSignal.set('Falha ao carregar projetos. Tente novamente.');
        this.loadingSignal.set(false);
        return of([]);
      })
    );
  }

  /**
   * Carrega projetos com paginação do servidor (quando backend suportar)
   */
  loadProjectsPaged(params: ProjectQueryParams): Observable<PagedResponse<Project>> {
    this.loadingSignal.set(true);
    this.errorSignal.set(null);

    const queryParams = new URLSearchParams();
    if (params.page !== undefined) queryParams.set('page', params.page.toString());
    if (params.size !== undefined) queryParams.set('size', params.size.toString());
    if (params.sort) queryParams.set('sort', params.sort);
    if (params.direction) queryParams.set('direction', params.direction);
    if (params.status && params.status !== 'all') queryParams.set('status', params.status);
    if (params.search) queryParams.set('search', params.search);
    if (params.dateFrom) queryParams.set('dateFrom', params.dateFrom);
    if (params.dateTo) queryParams.set('dateTo', params.dateTo);

    const endpoint = `/projects/paged?${queryParams.toString()}`;

    return this.api.get<PagedResponse<ProjectApiResponse>>(endpoint).pipe(
      map(response => ({
        ...response,
        content: response.content.map(p => this.mapApiToProject(p))
      })),
      tap(response => {
        this.projectsSignal.set(response.content);
        this.totalElementsSignal.set(response.totalElements);
        this.loadingSignal.set(false);
      }),
      catchError(error => {
        console.error('Erro ao carregar projetos:', error);
        this.errorSignal.set('Falha ao carregar projetos. Tente novamente.');
        this.loadingSignal.set(false);
        // Retorna resposta vazia em caso de erro
        return of({
          content: [],
          totalElements: 0,
          totalPages: 0,
          size: params.size || 12,
          number: params.page || 0,
          first: true,
          last: true
        });
      })
    );
  }

  getProject(id: number): Observable<Project | undefined> {
    // Primeiro tenta encontrar no cache local
    const cached = this.projectsSignal().find(p => p.id === id);
    if (cached) {
      return of(cached);
    }

    // Se não encontrar, busca da API
    return this.api.get<ProjectApiResponse>(`/projects/${id}`).pipe(
      map(apiProject => this.mapApiToProject(apiProject)),
      catchError(error => {
        // Não loga erro 404, pois é esperado quando projeto não existe
        if (error.status !== 404) {
          console.error(`Erro ao carregar projeto ${id}:`, error);
        }
        return of(undefined);
      })
    );
  }

  createProject(data: CreateProjectRequest): Observable<Project> {
    this.loadingSignal.set(true);

    // Vincula o projeto à obra/empreendimento de origem (Fase 3), quando o ERP
    // abriu o drone nesse contexto. IDs explícitos no `data` têm precedência.
    const payload: CreateProjectRequest = {
      ...data,
      empreendimentoId: data.empreendimentoId ?? this.context.empreendimentoId ?? undefined,
      obraId: data.obraId ?? this.context.obraId ?? undefined,
    };

    return this.api.post<ProjectApiResponse>('/projects', payload).pipe(
      map(apiProject => this.mapApiToProject(apiProject)),
      tap(newProject => {
        // Adiciona ao cache local
        this.projectsSignal.update(projects => [...projects, newProject]);
        this.loadingSignal.set(false);
      }),
      catchError(error => {
        console.error('Erro ao criar projeto:', error);
        this.errorSignal.set('Falha ao criar projeto. Tente novamente.');
        this.loadingSignal.set(false);
        throw error;
      })
    );
  }

  deleteProject(id: number): Observable<void> {
    return this.api.delete<void>(`/projects/${id}`).pipe(
      tap(() => {
        this.projectsSignal.update(projects => projects.filter(p => p.id !== id));
      }),
      catchError(error => {
        console.error(`Erro ao excluir projeto ${id}:`, error);
        this.errorSignal.set('Falha ao excluir projeto.');
        throw error;
      })
    );
  }

  getProjectTasks(projectId: number): Observable<ProjectTask[]> {
    // TODO: Implementar quando tivermos endpoint de tasks
    // return this.api.get<ProjectTask[]>(`/projects/${projectId}/tasks`);
    
    // Mock temporário
    const mockTasks: ProjectTask[] = [
      {
        id: 1,
        projectId,
        name: 'Processamento Ortofoto',
        status: 'COMPLETED',
        progress: 100,
        createdAt: '2025-11-20T10:30:00Z',
        completedAt: '2025-11-20T14:00:00Z',
        outputs: {
          orthophoto: '/outputs/ortho_1.tif'
        }
      },
      {
        id: 2,
        projectId,
        name: 'Modelo Digital de Superfície',
        status: 'RUNNING',
        progress: 65,
        createdAt: '2025-11-28T08:00:00Z'
      }
    ];

    return of(mockTasks);
  }

  /**
   * Atualiza um projeto existente
   */
  updateProject(id: number, data: Partial<CreateProjectRequest>): Observable<Project> {
    return this.api.put<ProjectApiResponse>(`/projects/${id}`, data).pipe(
      map((apiProject: ProjectApiResponse) => this.mapApiToProject(apiProject)),
      tap((updatedProject: Project) => {
        const currentProjects = this.projectsSignal();
        const updatedProjects: Project[] = [];
        for (const p of currentProjects) {
          if (p.id === id) {
            updatedProjects.push(updatedProject);
          } else {
            updatedProjects.push(p);
          }
        }
        this.projectsSignal.set(updatedProjects);
      }),
      catchError(error => {
        console.error(`Erro ao atualizar projeto ${id}:`, error);
        this.errorSignal.set('Falha ao atualizar projeto.');
        throw error;
      })
    );
  }

  /**
   * Limpa o estado de erro
   */
  clearError(): void {
    this.errorSignal.set(null);
  }
}
