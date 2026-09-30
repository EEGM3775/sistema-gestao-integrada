/**
 * GcpImportPanelComponent
 *
 * Painel lateral de importacao de GCPs via texto colado ou arquivo .txt.
 * Responsabilidade unica: parsing, deduplicacao e emissao dos novos pontos.
 * O componente pai (GcpEditorComponent) gerencia o signal gcpPoints.
 */

import {
  Component, Input, Output, EventEmitter, ElementRef,
  ViewChild, signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { GcpPoint } from '../../models/gcp-mark.model';
import { GcpEditorService } from '../../services/gcp-editor.service';
import { inject } from '@angular/core';

// ===========================================================================
// Tipos internos
// ===========================================================================

/** Par de pontos GCP considerados proximos (~<1 m) */
interface ProximityPair {
  /** Rotulo do ponto do lote sendo importado */
  labelA: string;
  /** Rotulo do ponto de referencia (existente ou outro do lote) */
  labelB: string;
  latA: number; lngA: number;
  latB: number; lngB: number;
  /** Distancia estimada em metros entre os dois pontos */
  distM: number;
  /** 'vs-existing': novo vs existente | 'within-batch': dois pontos do mesmo lote */
  kind: 'vs-existing' | 'within-batch';
}

/** Dados aguardando confirmacao do usuario apos relatorio de proximidade */
interface PendingImport {
  points: GcpPoint[];
  message: string | null;
  pairs: ProximityPair[];
}

@Component({
  selector: 'app-gcp-import-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="import-panel">

      @if (!pendingReport()) {

        <!--- ── Estado normal: formulario de importacao ───────────────────── -->
        <p class="import-title">
          {{ gcpPoints.length > 0 ? 'Adicionar mais pontos GCP' : 'Carregar pontos GCP' }}
        </p>
        <p class="import-hint">
          Cole o conteudo do arquivo exportado pelo sistema (ou dados do campo):
        </p>
        <textarea
          class="import-textarea"
          [(ngModel)]="importText"
          rows="8"
          placeholder="EPSG:4326&#10;-15.1234567 -47.6543210 850.000 0 0 img.jpg&#10;..."
        ></textarea>

        @if (importError()) {
          <p class="import-error">
            {{ importError() }}
          </p>
        }

        @if (importWarn()) {
          <p class="import-warn-msg">
            [AVISO] {{ importWarn() }}
          </p>
        }

        <div class="import-actions">
          <button class="btn-secondary" (click)="triggerFileInput()">Arquivo .txt...</button>
          <button class="btn-map" (click)="openMapRequest.emit()">Via Mapa</button>
          <button class="btn-primary" (click)="parseImport()">Carregar</button>
        </div>

        <input
          #fileInputRef
          type="file"
          accept=".txt"
          class="sr-only"
          (change)="onImportFile($event)"
        />

      } @else {

        <!--- ── Estado de revisao: relatorio de proximidade ──────────────── -->
        <p class="prox-title">
          [AVISO] {{ pendingReport()!.pairs.length }} {{ pendingReport()!.pairs.length === 1 ? 'par de pontos muito proximo' : 'pares de pontos muito proximos' }} (~1 m)
        </p>
        @if (pendingReport()!.message) {
          <p class="prox-info">{{ pendingReport()!.message }}</p>
        }
        <p class="prox-subtitle">
          Revise os pares abaixo antes de confirmar a importacao.
          Pontos muito proximos podem gerar ambiguidade no processamento ODM.
        </p>

        <div class="prox-list">
          @for (pair of pendingReport()!.pairs; track $index) {
            <div class="prox-pair">
              <div class="prox-pair-header">
                <span class="prox-labels">
                  {{ pair.labelA }}
                  <span class="prox-arrow"> {{ pair.kind === 'within-batch' ? '&#8596;' : '&rarr; (existente)' }} </span>
                  {{ pair.labelB }}
                </span>
                <span class="prox-dist">{{ pair.distM.toFixed(3) }} m</span>
              </div>
              <div class="prox-suggestion">{{ suggestionFor(pair) }}</div>
              <div class="prox-coords">
                A: {{ pair.latA.toFixed(6) }}, {{ pair.lngA.toFixed(6) }}
                &nbsp;|&nbsp;
                B: {{ pair.latB.toFixed(6) }}, {{ pair.lngB.toFixed(6) }}
              </div>
            </div>
          }
        </div>

        <div class="import-actions">
          <button class="btn-secondary" (click)="cancelImport()">Cancelar</button>
          <button class="btn-warn" (click)="confirmImport()">Importar mesmo assim</button>
        </div>

      }

    </div>
  `,
  styles: [`
    .import-panel {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .import-title {
      font-size: 12px;
      font-weight: 600;
      color: #e6edf3;
      margin: 0;
    }

    .import-hint {
      font-size: 11px;
      color: #8b949e;
      margin: 0;
      line-height: 1.4;
    }

    .import-textarea {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 6px;
      color: #c9d1d9;
      font-size: 11px;
      font-family: monospace;
      padding: 8px;
      resize: vertical;
      min-height: 100px;
    }

    .import-textarea:focus {
      outline: none;
      border-color: #58a6ff;
    }

    .import-error {
      font-size: 11px;
      color: #f85149;
      margin: 0;
    }

    .import-warn-msg {
      font-size: 11px;
      color: #d29922;
      margin: 0;
      line-height: 1.4;
    }

    .import-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .sr-only {
      position: absolute;
      width: 0;
      height: 0;
      opacity: 0;
      pointer-events: none;
    }

    .btn-primary {
      background: #238636;
      border: 1px solid #2ea043;
      color: #fff;
      padding: 6px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
    }

    .btn-primary:hover:not(:disabled) { background: #2ea043; }

    .btn-secondary {
      background: transparent;
      border: 1px solid #30363d;
      color: #c9d1d9;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
    }

    .btn-secondary:hover { border-color: #58a6ff; color: #58a6ff; }

    .btn-map {
      background: #1a3d6b;
      border: 1px solid #2d6ab0;
      color: #58a6ff;
      padding: 5px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
    }

    .btn-map:hover { background: #1f4d87; border-color: #58a6ff; }

    /* -- Relatorio de proximidade ---------------------------------------------- */

    .prox-title {
      font-size: 12px;
      font-weight: 700;
      color: #d29922;
      margin: 0;
    }

    .prox-info {
      font-size: 11px;
      color: #8b949e;
      margin: 0;
    }

    .prox-subtitle {
      font-size: 11px;
      color: #8b949e;
      margin: 0;
      line-height: 1.4;
    }

    .prox-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-height: 260px;
      overflow-y: auto;
      padding-right: 2px;
    }

    .prox-pair {
      background: #161b22;
      border: 1px solid #30363d;
      border-left: 3px solid #d29922;
      border-radius: 4px;
      padding: 6px 8px;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }

    .prox-pair-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 4px;
    }

    .prox-labels {
      font-size: 12px;
      font-weight: 600;
      color: #e6edf3;
    }

    .prox-arrow {
      color: #8b949e;
      font-weight: 400;
    }

    .prox-dist {
      font-size: 11px;
      font-weight: 700;
      color: #f85149;
      white-space: nowrap;
    }

    .prox-suggestion {
      font-size: 11px;
      color: #d29922;
    }

    .prox-coords {
      font-size: 10px;
      color: #8b949e;
      font-family: monospace;
      line-height: 1.3;
    }

    .btn-warn {
      background: #5a3e00;
      border: 1px solid #d29922;
      color: #d29922;
      padding: 6px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
    }

    .btn-warn:hover { background: #7a5500; border-color: #e3b341; color: #e3b341; }
  `]
})
export class GcpImportPanelComponent {

  /** Pontos ja carregados — usados apenas para deduplicacao de coordenadas. */
  @Input({ required: true }) gcpPoints: GcpPoint[] = [];

  /** Emite a lista de novos pontos validos, prontos para serem adicionados pelo pai. */
  @Output() pointsImported = new EventEmitter<{ points: GcpPoint[]; message: string | null }>();

  /** Solicita ao pai que abra o map picker. */
  @Output() openMapRequest = new EventEmitter<void>();

  @ViewChild('fileInputRef') fileInputRef?: ElementRef<HTMLInputElement>;

  private readonly editorService = inject(GcpEditorService);
  private readonly PROXIMITY_TOL = 0.00001;

  importText = '';
  importError = signal<string | null>(null);
  importWarn  = signal<string | null>(null);

  /** Aguardando confirmacao do usuario (relatorio de proximidade) */
  pendingReport = signal<PendingImport | null>(null);

  triggerFileInput(): void {
    this.fileInputRef?.nativeElement.click();
  }

  onImportFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      this.importText = (e.target?.result as string) ?? '';
      this.parseImport();
    };
    reader.readAsText(file);
  }

  parseImport(): void {
    this.importError.set(null);
    this.importWarn.set(null);
    if (!this.importText.trim()) {
      this.importError.set('Cole o conteudo do arquivo GCP antes de carregar.');
      return;
    }

    try {
      const parsed = this.editorService.parsePartialGcp(this.importText);
      if (parsed.length === 0) {
        this.importError.set('Nenhum ponto GCP foi encontrado. Verifique o formato.');
        return;
      }

      const existing = this.gcpPoints;

      const isExactCoord = (lat: number, lng: number) =>
        existing.some(e => e.lat === lat && e.lng === lng);

      // Remove duplicatas dentro do proprio lote
      const dedupedParsed = parsed.filter((p, idx, arr) =>
        arr.findIndex(q => q.lat === p.lat && q.lng === p.lng) === idx
      );

      const unique  = dedupedParsed.filter(p => !isExactCoord(p.lat, p.lng));
      const skipped = parsed.length - unique.length;

      if (unique.length === 0) {
        this.importError.set(
          `Todos os ${parsed.length} pontos ja existem na lista (coordenadas identicas).`
        );
        return;
      }

      // Gera IDs unicos sem colidir com existentes
      const offset = existing.length;
      const newPoints: GcpPoint[] = unique.map((p, i) => ({
        ...p,
        id: `gcp-${offset + i + 1}-${Date.now()}`,
        label: p.label.replace(/\d+$/, m => String(offset + parseInt(m, 10)).padStart(2, '0')),
      }));

      // ----------------------------------------------------------------
      // Aviso de proximidade — compoe lista de ProximityPair com distancia
      // ----------------------------------------------------------------

      // Novos pontos vs pontos ja existentes na lista
      const nearVsExisting: ProximityPair[] = newPoints
        .flatMap(np =>
          existing
            .filter(e =>
              Math.abs(e.lat - np.lat) < this.PROXIMITY_TOL &&
              Math.abs(e.lng - np.lng) < this.PROXIMITY_TOL
            )
            .map(e => ({
              labelA: np.label,
              labelB: e.label,
              latA: np.lat, lngA: np.lng,
              latB: e.lat,  lngB: e.lng,
              distM: this.haversineM(np.lat, np.lng, e.lat, e.lng),
              kind: 'vs-existing' as const
            }))
        );

      // Pares dentro do proprio lote (par unico a→b, evita duplicar b→a)
      const nearWithinBatch: ProximityPair[] = [];
      for (let i = 0; i < newPoints.length; i++) {
        for (let j = i + 1; j < newPoints.length; j++) {
          const a = newPoints[i], b = newPoints[j];
          if (
            Math.abs(a.lat - b.lat) < this.PROXIMITY_TOL &&
            Math.abs(a.lng - b.lng) < this.PROXIMITY_TOL
          ) {
            nearWithinBatch.push({
              labelA: a.label, labelB: b.label,
              latA: a.lat, lngA: a.lng,
              latB: b.lat, lngB: b.lng,
              distM: this.haversineM(a.lat, a.lng, b.lat, b.lng),
              kind: 'within-batch'
            });
          }
        }
      }

      const allPairs = [...nearVsExisting, ...nearWithinBatch];

      // Mensagem de status (pontos ignorados por coordenadas identicas)
      const skippedMsg = skipped > 0
        ? `${unique.length} ponto(s) carregado(s). ${skipped} ignorado(s) por coordenadas identicas.`
        : null;

      if (allPairs.length > 0) {
        // Ha pares proximos: exibe relatorio de revisao antes de confirmar
        if (skipped > 0) this.importError.set(skippedMsg);
        this.pendingReport.set({ points: newPoints, message: skippedMsg, pairs: allPairs });
        return;
      }

      // Sem pares proximos: importa imediatamente
      if (skipped > 0) this.importError.set(skippedMsg);
      this.importText = '';
      this.pointsImported.emit({ points: newPoints, message: skippedMsg });

    } catch {
      this.importError.set('Erro ao interpretar o arquivo. Verifique o formato.');
    }
  }

  /** Confirma a importacao apos o usuario revisar o relatorio de proximidade. */
  confirmImport(): void {
    const report = this.pendingReport();
    if (!report) return;
    this.importText = '';
    this.importError.set(null);
    this.importWarn.set(null);
    this.pointsImported.emit({ points: report.points, message: report.message });
    this.pendingReport.set(null);
  }

  /** Cancela a importacao e volta ao formulario. */
  cancelImport(): void {
    this.pendingReport.set(null);
  }

  /** Devolve sugestao de acao com base na distancia entre o par. */
  suggestionFor(pair: ProximityPair): string {
    if (pair.distM < 0.25) return '[ACAO] Provavel duplicata — verifique e considere remover um dos pontos';
    if (pair.distM < 0.60) return '[ACAO] Pontos muito proximos — confirme os dados de campo antes de importar';
    return '[ACAO] Pontos proximos — verifique se representam GCPs fisicamente distintos';
  }

  /** Distancia Haversine aproximada em metros entre dois pontos WGS84. */
  private haversineM(la1: number, lo1: number, la2: number, lo2: number): number {
    const R = 6_371_000;
    const dLat = (la2 - la1) * Math.PI / 180;
    const dLon = (lo2 - lo1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2
      + Math.cos(la1 * Math.PI / 180) * Math.cos(la2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
}
