/**
 * ElevationProfileChartComponent
 *
 * Renderiza um grafico de linha (distancia x elevacao) usando Chart.js puro (v4).
 * Nao depende de ng2-charts nem de wrappers externos.
 *
 * Inputs:
 *   coordinates    — [[lat, lng, elev], ...] — pontos amostrados do perfil
 *   measurementId  — id da medicao, usado para identificar o hover no servico
 *
 * Comportamento de hover:
 *   Ao mover o cursor sobre o grafico, injeta o estado no ElevationProfileHoverService.
 *   O MeasurementTabComponent reage ao estado colocando um marcador temporario no mapa.
 *   Ao sair do grafico, limpa o estado.
 */

import {
  Component, Input, OnChanges, AfterViewInit, OnDestroy,
  ViewChild, ElementRef, SimpleChanges, ChangeDetectionStrategy, inject
} from '@angular/core';
import { Chart, registerables, ChartConfiguration } from 'chart.js';
import { ElevationProfileHoverService } from '../../services/elevation-profile-hover.service';

// Registra todos os modulos do Chart.js (Line, Scales, Tooltip, etc.)
Chart.register(...registerables);

// ============================================================================
// Helpers de modulo
// ============================================================================

function haversineM(la1: number, lo1: number, la2: number, lo2: number): number {
  const R = 6_371_000;
  const dLat = (la2 - la1) * Math.PI / 180;
  const dLon = (lo2 - lo1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(la1 * Math.PI / 180) * Math.cos(la2 * Math.PI / 180)
    * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

interface ProfilePoint {
  dist: number;
  elev: number;
  lat: number;
  lng: number;
}

// ============================================================================
// Component
// ============================================================================

@Component({
  selector: 'app-elevation-profile-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="profile-wrap">
      <canvas #chartCanvas class="profile-canvas"></canvas>
      @if (!hasData()) {
        <div class="no-data">Sem dados de elevacao disponíveis</div>
      }
    </div>
  `,
  styles: [`
    .profile-wrap {
      position: relative;
      width: 100%;
      height: 160px;
    }

    .profile-canvas {
      width: 100% !important;
      height: 100% !important;
    }

    .no-data {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #8b949e;
      font-size: 11px;
    }
  `]
})
export class ElevationProfileChartComponent implements AfterViewInit, OnChanges, OnDestroy {

  @ViewChild('chartCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;

  /** Pontos amostrados do perfil: [[lat, lng, elev], ...] */
  @Input({ required: true }) coordinates: number[][] = [];

  /** ID da medicao pai — usado para identificar o hover no servico */
  @Input({ required: true }) measurementId!: string;

  private readonly hoverSvc = inject(ElevationProfileHoverService);

  private chart: Chart | null = null;

  // =========================================================================
  // Computed helpers
  // =========================================================================

  hasData(): boolean {
    return this.coordinates.some(c => c.length >= 3 && isFinite(c[2]));
  }

  private buildProfile(): ProfilePoint[] {
    const pts: ProfilePoint[] = [];
    let cumDist = 0;
    for (let i = 0; i < this.coordinates.length; i++) {
      const c = this.coordinates[i];
      if (!c || c.length < 3 || !isFinite(c[2])) continue;
      if (i > 0) {
        const prev = this.coordinates[i - 1];
        if (prev && prev.length >= 2) {
          cumDist += haversineM(prev[0], prev[1], c[0], c[1]);
        }
      }
      pts.push({ dist: cumDist, elev: c[2], lat: c[0], lng: c[1] });
    }
    return pts;
  }

  // =========================================================================
  // Lifecycle
  // =========================================================================

  ngAfterViewInit(): void {
    this.createChart();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['coordinates']) {
      this.updateChart();
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
    this.hoverSvc.clearHover();
  }

  // =========================================================================
  // Chart
  // =========================================================================

  private createChart(): void {
    if (!this.canvasRef?.nativeElement || !this.hasData()) return;

    const profile = this.buildProfile();
    const ctx = this.canvasRef.nativeElement.getContext('2d');
    if (!ctx) return;

    // Gradiente de preenchimento sob a linha
    const gradient = ctx.createLinearGradient(0, 0, 0, 160);
    gradient.addColorStop(0, 'rgba(88, 166, 255, 0.40)');
    gradient.addColorStop(1, 'rgba(88, 166, 255, 0.02)');

    const labels = profile.map(p =>
      p.dist < 1000 ? `${p.dist.toFixed(0)} m` : `${(p.dist / 1000).toFixed(2)} km`
    );
    const data = profile.map(p => p.elev);

    const config: ChartConfiguration<'line'> = {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Elevacao (m)',
          data,
          borderColor: '#58a6ff',
          backgroundColor: gradient,
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: '#58a6ff',
          pointHoverBorderColor: '#fff',
          fill: true,
          tension: 0.25,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1c2128',
            borderColor: '#30363d',
            borderWidth: 1,
            titleColor: '#8b949e',
            bodyColor: '#e6edf3',
            padding: 6,
            callbacks: {
              title: (items) => labels[items[0]?.dataIndex ?? 0] ?? '',
              label: (item) => ` ${(item.raw as number).toFixed(2)} m`
            }
          }
        },
        scales: {
          x: {
            ticks: {
              color: '#8b949e',
              font: { size: 9 },
              maxTicksLimit: 5,
              maxRotation: 0
            },
            grid: { color: '#21262d' }
          },
          y: {
            ticks: {
              color: '#8b949e',
              font: { size: 9 },
              maxTicksLimit: 4
            },
            grid: { color: '#21262d' }
          }
        },
        // Sincroniza marcador no mapa via servico de hover
        onHover: (_event, elements) => {
          if (elements.length > 0) {
            const idx = elements[0].index;
            const pt = profile[idx];
            if (pt) {
              this.hoverSvc.setHover({
                measurementId: this.measurementId,
                lat: pt.lat,
                lng: pt.lng,
                elevation: pt.elev,
                distance: pt.dist
              });
            }
          } else {
            this.hoverSvc.clearHover();
          }
        }
      }
    };

    this.chart = new Chart(ctx, config);
  }

  private updateChart(): void {
    if (!this.chart) {
      this.createChart();
      return;
    }
    const profile = this.buildProfile();
    this.chart.data.labels = profile.map(p =>
      p.dist < 1000 ? `${p.dist.toFixed(0)} m` : `${(p.dist / 1000).toFixed(2)} km`
    );
    this.chart.data.datasets[0].data = profile.map(p => p.elev);
    this.chart.update('none');
  }
}
