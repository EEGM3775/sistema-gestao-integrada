/**
 * MeasItemComponent
 * 
 * Item individual da lista de medições: linha principal + painel de detalhes (acordeão).
 * Componente puramente apresentacional — sem estado interno, sem serviços.
 *
 * Inputs:
 *   measurement   — dados da medição
 *   isVisible     — camada exibida no mapa?
 *   isExpanded    — painel de detalhes aberto?
 *   isEditing     — campo de edição de nome ativo?
 *   editingName   — valor atual do input de nome
 *
 * Outputs:
 *   toggleVisibilityChange — usuário marcou/desmarcou o checkbox de visibilidade
 *   focusRequested         — usuário clicou no item (centralizar no mapa)
 *   toggleDetailRequested  — usuário abriu/fechou o acordeão de detalhes
 *   startEditRequested     — usuário iniciou edição de nome
 *   confirmEditRequested   — usuário confirmou o novo nome (emite a string)
 *   cancelEditRequested    — usuário cancelou a edição
 *   deleteRequested        — usuário clicou em deletar
 */

import {
  Component, Input, Output, EventEmitter,
  ChangeDetectionStrategy, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MeasurementData } from '../../models/measurement-data';
import { ExportBaseService } from '../../services/export/export-base.service';
import { ElevationProfileChartComponent } from '../elevation-profile-chart/elevation-profile-chart.component';

@Component({
  selector: 'app-meas-item',
  standalone: true,
  imports: [CommonModule, ElevationProfileChartComponent],
  templateUrl: './meas-item.component.html',
  styleUrls: ['./meas-item.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class MeasItemComponent {

  private base = inject(ExportBaseService);

  @Input({ required: true }) measurement!: MeasurementData;
  @Input() isVisible  = false;
  @Input() isExpanded = false;
  @Input() isEditing  = false;
  @Input() editingName = '';

  @Output() toggleVisibilityChange  = new EventEmitter<boolean>();
  @Output() focusRequested          = new EventEmitter<void>();
  @Output() toggleDetailRequested   = new EventEmitter<void>();
  @Output() startEditRequested      = new EventEmitter<void>();
  @Output() confirmEditRequested    = new EventEmitter<string>();
  @Output() cancelEditRequested     = new EventEmitter<void>();
  @Output() deleteRequested         = new EventEmitter<void>();

  getMeasurementIcon(type: string): string {
    return ({
      distance: '📏',
      area: '⬜',
      volume: '📦',
      height: '↕️',
      elevation_profile: '📈'
    } as Record<string, string>)[type] ?? '📍';
  }

  // =========================================================================
  // Painel de detalhes — helpers geométricos
  // =========================================================================

  /**
   * Converte WGS84 → string UTM WGS84 formatada em pt-BR.
   * Delega para ExportBaseService.wgs84ToUtmStr() — mesma função usada
   * por todos os formatos de exportação (DXF, CSV, GeoJSON, etc.).
   * Garante que a UI e os arquivos exportados mostrem SEMPRE o mesmo valor.
   */
  toUtmStr(lat: number, lng: number): string {
    return this.base.wgs84ToUtmStr(lat, lng);
  }

  /** Distância geodésica Vincenty (WGS84 elipsoide, ~0,06 mm de precisão). */
  private haversine2D(la1: number, ln1: number, la2: number, ln2: number): number {
    const a = 6_378_137.0;           // semi-eixo maior WGS84 (m)
    const b = 6_356_752.314_245;     // semi-eixo menor WGS84 (m)
    const f = 1 / 298.257_223_563;

    const φ1 = la1 * Math.PI / 180;  const φ2 = la2 * Math.PI / 180;
    const L  = (ln2 - ln1) * Math.PI / 180;

    const tanU1 = (1 - f) * Math.tan(φ1);  const cosU1 = 1 / Math.sqrt(1 + tanU1 * tanU1);  const sinU1 = tanU1 * cosU1;
    const tanU2 = (1 - f) * Math.tan(φ2);  const cosU2 = 1 / Math.sqrt(1 + tanU2 * tanU2);  const sinU2 = tanU2 * cosU2;

    let λ = L;
    let sinλ = 0, cosλ = 0, sinSigma = 0, cosSigma = 0, sigma = 0;
    let sinAlpha = 0, cos2Alpha = 0, cos2SigmaM = 0, C = 0;
    let iter = 0;
    do {
      const λPrev = λ;
      sinλ = Math.sin(λ);  cosλ = Math.cos(λ);
      const t1 = cosU2 * sinλ;  const t2 = cosU1 * sinU2 - sinU1 * cosU2 * cosλ;
      sinSigma = Math.sqrt(t1 * t1 + t2 * t2);
      if (sinSigma === 0) return 0;
      cosSigma   = sinU1 * sinU2 + cosU1 * cosU2 * cosλ;
      sigma      = Math.atan2(sinSigma, cosSigma);
      sinAlpha   = cosU1 * cosU2 * sinλ / sinSigma;
      cos2Alpha  = 1 - sinAlpha * sinAlpha;
      cos2SigmaM = cos2Alpha !== 0 ? cosSigma - 2 * sinU1 * sinU2 / cos2Alpha : 0;
      C = f / 16 * cos2Alpha * (4 + f * (4 - 3 * cos2Alpha));
      λ = L + (1 - C) * f * sinAlpha * (
        sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM))
      );
      if (Math.abs(λ - λPrev) <= 1e-12) break;
    } while (++iter < 100);

    const u2 = cos2Alpha * (a * a - b * b) / (b * b);
    const A  = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)));
    const B  = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)));
    const Δσ = B * sinSigma * (
      cos2SigmaM + B / 4 * (
        cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM) -
        B / 6 * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) * (-3 + 4 * cos2SigmaM * cos2SigmaM)
      )
    );
    return b * A * (sigma - Δσ);
  }

  getSegments(m: MeasurementData): { label: string; distM: number }[] {
    const c = m.coordinates;
    return c.slice(0, -1).map((pt, i) => ({
      label: `Trecho ${i + 1}→${i + 2}`,
      distM: this.haversine2D(pt[0], pt[1], c[i + 1][0], c[i + 1][1])
    }));
  }

  getPerimeterM(m: MeasurementData): number {
    const c = m.coordinates;
    let total = 0;
    for (let i = 0; i < c.length; i++) {
      const nx = (i + 1) % c.length;
      total += this.haversine2D(c[i][0], c[i][1], c[nx][0], c[nx][1]);
    }
    return total;
  }

  fmtDist(m: number): string {
    return m >= 1000 ? `${(m / 1000).toFixed(3)} km` : `${m.toFixed(2)} m`;
  }

  // =========================================================================
  // Helpers para perfil de elevacao (elevation_profile)
  // =========================================================================

  /**
   * Formata distancia total do perfil com unidade automatica.
   */
  formatProfileDist(distM: number): string {
    return distM >= 1000 ? `${(distM / 1000).toFixed(3)} km` : `${distM.toFixed(1)} m`;
  }

  /**
   * Computa estatísticas basicas do perfil a partir das coordenadas amostradas.
   * Exige que as coordenadas sejam triplas [lat, lng, elev].
   */
  getProfileStats(coords: number[][]): { min: number; max: number; gain: number; loss: number } {
    const elevs = coords.filter(c => c.length >= 3 && isFinite(c[2])).map(c => c[2]);
    if (elevs.length === 0) return { min: 0, max: 0, gain: 0, loss: 0 };
    let gain = 0, loss = 0;
    for (let i = 1; i < elevs.length; i++) {
      const d = elevs[i] - elevs[i - 1];
      if (d > 0) gain += d; else loss += Math.abs(d);
    }
    return { min: Math.min(...elevs), max: Math.max(...elevs), gain, loss };
  }

  // =========================================================================
  // Manipuladores do input de nome (sem lógica de API — emite e pronto)
  // =========================================================================

  onInputChange(event: Event): void {
    // Atualiza o binding externo via emissão do evento de confirmação não é possível
    // sem dois eventos separados; usamos o padrão: emitir o valor atual a cada keystroke
    // é excessivo. O componente pai controla editingName via Two-way binding ou sinal.
    // Aqui apenas trabalhamos com o valor nativo do input ao confirmar.
  }

  onKeydown(event: KeyboardEvent): void {
    const input = event.target as HTMLInputElement;
    if (event.key === 'Enter') {
      event.stopPropagation();
      this.confirmEditRequested.emit(input.value);
    } else if (event.key === 'Escape') {
      event.stopPropagation();
      this.cancelEditRequested.emit();
    }
  }

  onBlur(event: FocusEvent): void {
    const input = event.target as HTMLInputElement;
    this.confirmEditRequested.emit(input.value);
  }
}
