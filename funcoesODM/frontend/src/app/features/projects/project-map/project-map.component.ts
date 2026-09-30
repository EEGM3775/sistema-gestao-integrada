import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MapViewerComponent } from '../../../shared/components/map-viewer/map-viewer.component';

interface ProjectInfo {
  id: number;
  name: string;
  description: string;
  location: { lat: number; lng: number };
  imageCount: number;
  area: string;
  status: string;
}

@Component({
    selector: 'app-project-map',
    imports: [CommonModule, RouterLink, MapViewerComponent],
    template: `
    <div class="map-page">
      <!-- Top Bar -->
      <div class="top-bar">
        <div class="left-section">
          <a [routerLink]="['/projects', projectId]" class="back-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m15 18-6-6 6-6"/>
            </svg>
          </a>
          <div class="project-info">
            <h1>{{ project()?.name || 'Carregando...' }}</h1>
            <span class="breadcrumb">Mapa • {{ project()?.area }}</span>
          </div>
        </div>
        
        <div class="right-section">
          <div class="view-tabs">
            <a 
              [routerLink]="['/projects', projectId]" 
              class="tab-btn"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              Detalhes
            </a>
            <a 
              [routerLink]="['/projects', projectId, 'map']" 
              class="tab-btn active"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
                <line x1="8" y1="2" x2="8" y2="18"/>
                <line x1="16" y1="6" x2="16" y2="22"/>
              </svg>
              Mapa 2D
            </a>
            <a 
              [routerLink]="['/projects', projectId, '3d']" 
              class="tab-btn"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 3L2 7.5l10 4.5 10-4.5L12 3z"/>
                <path d="M2 17.5l10 4.5 10-4.5"/>
                <path d="M2 12.5l10 4.5 10-4.5"/>
              </svg>
              3D View
            </a>
          </div>
          
          <div class="action-buttons">
            <button class="action-btn" title="Exportar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
            </button>
            <button class="action-btn" title="Compartilhar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="18" cy="5" r="3"/>
                <circle cx="6" cy="12" r="3"/>
                <circle cx="18" cy="19" r="3"/>
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
              </svg>
            </button>
            <button class="action-btn primary" title="Ações">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="1"/>
                <circle cx="19" cy="12" r="1"/>
                <circle cx="5" cy="12" r="1"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Main Map -->
      <div class="map-wrapper">
        <app-map-viewer 
          *ngIf="project()"
          [center]="[project()!.location.lat, project()!.location.lng]"
          [zoom]="15"
          [projectId]="projectId"
          (markerAdded)="onMarkerAdded($event)"
          (measurementComplete)="onMeasurement($event)"
        ></app-map-viewer>
      </div>

      <!-- Side Panel (Optional - for layers/tools) -->
      <div class="side-panel" [class.open]="showSidePanel()">
        <div class="panel-header">
          <h3>Ferramentas</h3>
          <button class="close-btn" (click)="toggleSidePanel()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        
        <div class="panel-content">
          <div class="tool-section">
            <h4>Análise</h4>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 3v18h18"/>
                <path d="m19 9-5 5-4-4-3 3"/>
              </svg>
              Perfil de Elevação
            </button>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m8 3 4 8 5-5 5 15H2L8 3z"/>
              </svg>
              Cálculo de Volume
            </button>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>
                <path d="M2 12h20"/>
              </svg>
              Contornos
            </button>
          </div>
          
          <div class="tool-section">
            <h4>Anotações</h4>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                <circle cx="12" cy="10" r="3"/>
              </svg>
              Adicionar Ponto
            </button>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 3a2 2 0 0 0-2 2"/>
                <path d="M19 3a2 2 0 0 1 2 2"/>
                <path d="M21 19a2 2 0 0 1-2 2"/>
                <path d="M5 21a2 2 0 0 1-2-2"/>
                <path d="M9 3h1"/>
                <path d="M9 21h1"/>
                <path d="M14 3h1"/>
                <path d="M14 21h1"/>
                <path d="M3 9v1"/>
                <path d="M21 9v1"/>
                <path d="M3 14v1"/>
                <path d="M21 14v1"/>
              </svg>
              Desenhar Área
            </button>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="4" y1="21" x2="4" y2="14"/>
                <line x1="4" y1="10" x2="4" y2="3"/>
                <line x1="12" y1="21" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12" y2="3"/>
                <line x1="20" y1="21" x2="20" y2="16"/>
                <line x1="20" y1="12" x2="20" y2="3"/>
                <line x1="1" y1="14" x2="7" y2="14"/>
                <line x1="9" y1="8" x2="15" y2="8"/>
                <line x1="17" y1="16" x2="23" y2="16"/>
              </svg>
              Ajustar Contraste
            </button>
          </div>
          
          <div class="tool-section">
            <h4>Exportar</h4>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
              Exportar Imagem
            </button>
            <button class="tool-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10 9 9 9 8 9"/>
              </svg>
              Gerar Relatório
            </button>
          </div>
        </div>
      </div>

      <!-- Tools Toggle Button -->
      <button class="tools-toggle" (click)="toggleSidePanel()" *ngIf="!showSidePanel()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
      </button>
    </div>
  `,
    styles: [`
    .map-page {
      height: 100vh;
      display: flex;
      flex-direction: column;
      background: #0f172a;
    }

    /* Top Bar */
    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.75rem 1rem;
      background: white;
      border-bottom: 1px solid #e2e8f0;
      z-index: 100;
    }

    .left-section {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .back-btn {
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f1f5f9;
      border-radius: 8px;
      color: #475569;
      text-decoration: none;
      transition: all 0.2s;
    }

    .back-btn:hover {
      background: #e2e8f0;
      color: #1e293b;
    }

    .back-btn svg {
      width: 20px;
      height: 20px;
    }

    .project-info h1 {
      margin: 0;
      font-size: 1.125rem;
      font-weight: 600;
      color: #1e293b;
    }

    .breadcrumb {
      font-size: 0.8rem;
      color: #64748b;
    }

    .right-section {
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }

    .view-tabs {
      display: flex;
      gap: 0.25rem;
      background: #f1f5f9;
      padding: 0.25rem;
      border-radius: 8px;
    }

    .tab-btn {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1rem;
      background: transparent;
      border: none;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 500;
      color: #64748b;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.2s;
    }

    .tab-btn:hover {
      background: white;
      color: #1e293b;
    }

    .tab-btn.active {
      background: white;
      color: #3b82f6;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .tab-btn svg {
      width: 16px;
      height: 16px;
    }

    .action-buttons {
      display: flex;
      gap: 0.5rem;
    }

    .action-btn {
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f1f5f9;
      border: none;
      border-radius: 8px;
      color: #475569;
      cursor: pointer;
      transition: all 0.2s;
    }

    .action-btn:hover {
      background: #e2e8f0;
      color: #1e293b;
    }

    .action-btn.primary {
      background: #3b82f6;
      color: white;
    }

    .action-btn.primary:hover {
      background: #2563eb;
    }

    .action-btn svg {
      width: 18px;
      height: 18px;
    }

    /* Map Wrapper */
    .map-wrapper {
      flex: 1;
      position: relative;
    }

    .map-wrapper app-map-viewer {
      width: 100%;
      height: 100%;
    }

    /* Side Panel */
    .side-panel {
      position: fixed;
      top: 57px;
      right: -320px;
      width: 320px;
      height: calc(100vh - 57px);
      background: white;
      box-shadow: -4px 0 16px rgba(0, 0, 0, 0.1);
      transition: right 0.3s ease;
      z-index: 90;
      display: flex;
      flex-direction: column;
    }

    .side-panel.open {
      right: 0;
    }

    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem;
      border-bottom: 1px solid #e2e8f0;
    }

    .panel-header h3 {
      margin: 0;
      font-size: 1rem;
      font-weight: 600;
      color: #1e293b;
    }

    .close-btn {
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: transparent;
      border: none;
      border-radius: 6px;
      color: #64748b;
      cursor: pointer;
    }

    .close-btn:hover {
      background: #f1f5f9;
      color: #1e293b;
    }

    .close-btn svg {
      width: 18px;
      height: 18px;
    }

    .panel-content {
      flex: 1;
      overflow-y: auto;
      padding: 1rem;
    }

    .tool-section {
      margin-bottom: 1.5rem;
    }

    .tool-section h4 {
      margin: 0 0 0.75rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .tool-btn {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      width: 100%;
      padding: 0.75rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      font-size: 0.875rem;
      color: #334155;
      cursor: pointer;
      transition: all 0.2s;
      margin-bottom: 0.5rem;
    }

    .tool-btn:hover {
      background: #f1f5f9;
      border-color: #cbd5e1;
    }

    .tool-btn svg {
      width: 18px;
      height: 18px;
      color: #64748b;
    }

    /* Tools Toggle Button */
    .tools-toggle {
      position: fixed;
      top: 70px;
      right: 1rem;
      width: 44px;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: white;
      border: none;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      cursor: pointer;
      z-index: 80;
      transition: all 0.2s;
    }

    .tools-toggle:hover {
      background: #f8fafc;
      transform: scale(1.05);
    }

    .tools-toggle svg {
      width: 22px;
      height: 22px;
      color: #475569;
    }

    /* Responsive */
    @media (max-width: 768px) {
      .view-tabs {
        display: none;
      }

      .project-info h1 {
        font-size: 0.95rem;
      }

      .side-panel {
        width: 100%;
        right: -100%;
      }
    }
  `]
})
export class ProjectMapComponent implements OnInit {
  projectId!: number;
  project = signal<ProjectInfo | null>(null);
  showSidePanel = signal(false);

  constructor(private route: ActivatedRoute) {}

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.projectId = +params['id'];
      this.loadProject();
    });
  }

  loadProject(): void {
    // Simulated data - replace with actual API call
    setTimeout(() => {
      this.project.set({
        id: this.projectId,
        name: 'Fazenda São João - Mapeamento Aéreo',
        description: 'Levantamento topográfico completo para planejamento agrícola',
        location: { lat: -23.5505, lng: -46.6333 },
        imageCount: 245,
        area: '150 ha',
        status: 'COMPLETED'
      });
    }, 300);
  }

  toggleSidePanel(): void {
    this.showSidePanel.update(v => !v);
  }

  onMarkerAdded(marker: any): void {
    console.log('Marker added:', marker);
  }

  onMeasurement(result: any): void {
    console.log('Measurement:', result);
  }
}
