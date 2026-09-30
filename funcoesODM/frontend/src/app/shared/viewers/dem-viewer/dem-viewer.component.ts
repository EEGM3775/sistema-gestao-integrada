/**
 * DemViewerComponent — Wrapper do visualizador de Modelo Digital de Elevação
 *
 * Constrói os AssetInfo usando os nomes padrão de saída do NodeODM
 * (dsm.tif / dtm.tif) e delega a renderização ao DsmTabComponent
 * (georaster + Leaflet + paleta terrain profissional).
 *
 * Não faz chamada a /tasks/{id} — usa diretamente o chunkId para
 * construir as URLs via DsmTabComponent → ResultsService.getChunkAssetDownloadUrl().
 *
 * Usado em: MeasurementTabComponent (aba "DSM" do viewer de medições)
 */

import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  SimpleChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import * as L from 'leaflet';
import { AssetInfo } from '../../../features/projects/services/results.service';
import { DsmTabComponent } from '../../../features/projects/components/results-viewer/components/dsm-tab/dsm-tab.component';

/** Nomes de arquivo padrão gerados pelo NodeODM/ODM */
const ELEVATION_ASSET_DEFS: Array<{ name: string; displayName: string; icon: string }> = [
  { name: 'dsm.tif',  displayName: 'DSM (Modelo Digital de Superfície)', icon: '▲' },
  { name: 'dtm.tif',  displayName: 'DTM (Modelo Digital de Terreno)',     icon: '△' },
];

@Component({
  selector: 'app-dem-viewer',
  standalone: true,
  imports: [CommonModule, DsmTabComponent],
  template: `
    <div class="dem-viewer-wrapper">
      <app-dsm-tab
        [assets]="assets"
        [projectId]="projectId"
        [taskId]="taskId ?? 0"
        (mapReady)="mapReady.emit($event)">
      </app-dsm-tab>
    </div>
  `,
  styles: [`
    .dem-viewer-wrapper {
      width: 100%;
      height: 100%;
    }
    app-dsm-tab {
      display: block;
      width: 100%;
      height: 100%;
    }
  `]
})
export class DemViewerComponent implements OnChanges {
  @Input() projectId!: number;
  @Input() taskId?: number;
  @Input() nodeodmTaskId?: string;

  @Output() mapReady = new EventEmitter<L.Map>();

  assets: AssetInfo[] = [];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['projectId'] || changes['taskId'] || changes['nodeodmTaskId']) {
      this.buildAssets();
    }
  }

  private buildAssets(): void {
    // When nodeodmTaskId is available, build the URL that matches what the
    // backend stores in outputs (/api/v1/chunks/{uuid}/assets/{filename}).
    // That endpoint is served by ChunkAssetController and is permit-all,
    // so GeoTiffCacheService (raw fetch, no JWT) can download it.
    const baseUrl = this.nodeodmTaskId
      ? `/api/v1/chunks/${this.nodeodmTaskId}/assets/`
      : null;

    this.assets = ELEVATION_ASSET_DEFS.map(def => ({
      name: def.name,
      displayName: def.displayName,
      description: def.displayName,
      icon: def.icon,
      extension: 'tif',
      downloadUrl: baseUrl ? `${baseUrl}${def.name}` : '',
      available: true
    }));
  }
}
