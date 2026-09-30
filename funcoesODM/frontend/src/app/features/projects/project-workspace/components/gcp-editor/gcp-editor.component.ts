/**
 * GcpEditorComponent  Orquestrador
 *
 * Gerencia o estado central (gcpPoints, marks, selectedGcpId) e
 * conecta os sub-componentes:
 *  - GcpImportPanelComponent  -> importar por texto/arquivo
 *  - GcpMapPickerComponent    -> adicionar via mapa satellite
 *  - GcpListComponent         -> lista e selecao de GCPs
 *  - GcpImageViewerComponent  -> navegacao, zoom e marcacao nas fotos
 *
 * Fluxo:
 *  1. Usuario importa GCP parcial (coordenadas de campo, sem pixels)
 *  2. Navega pelas imagens e clica onde cada alvo aparece
 *  3. Clica "Usar"  emite File pronto para upload ao processamento ODM
 */

import {
  Component, Input, Output, EventEmitter,
  signal, computed, inject, ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ProjectImage } from '../../../models/project.model';
import { GcpPoint, GcpMark } from './models/gcp-mark.model';
import { GcpEditorService } from './services/gcp-editor.service';
import { GcpImportPanelComponent } from './components/gcp-import-panel/gcp-import-panel.component';
import { GcpMapPickerComponent } from './components/gcp-map-picker/gcp-map-picker.component';
import { GcpListComponent } from './components/gcp-list/gcp-list.component';
import { GcpImageViewerComponent } from './components/gcp-image-viewer/gcp-image-viewer.component';

@Component({
    selector: 'app-gcp-editor',
    imports: [
        CommonModule,
        GcpImportPanelComponent,
        GcpMapPickerComponent,
        GcpListComponent,
        GcpImageViewerComponent,
    ],
    changeDetection: ChangeDetectionStrategy.OnPush,
    templateUrl: './gcp-editor.component.html',
    styleUrl: './gcp-editor.component.scss'
})
export class GcpEditorComponent {

  @Input({ required: true }) projectId!: number;
  @Input() images: ProjectImage[] = [];

  @Output() gcpFileReady = new EventEmitter<File>();
  @Output() closeEditor  = new EventEmitter<void>();

  private readonly editorService = inject(GcpEditorService);

  // ==================== STATE ====================

  gcpPoints       = signal<GcpPoint[]>([]);
  marks           = signal<GcpMark[]>([]);
  selectedGcpId   = signal<string | null>(null);
  showImportPanel = signal(true);
  showMapPicker   = signal(false);

  // ==================== COMPUTED ====================

  validation = computed(() =>
    this.editorService.isValid(this.gcpPoints(), this.marks())
  );

  uniqueImageCount = computed(() =>
    new Set(this.marks().map(m => m.imageId)).size
  );

  // ==================== EVENT HANDLERS DOS FILHOS ====================

  onPointsImported(result: { points: GcpPoint[]; message: string | null }): void {
    this.gcpPoints.update(pts => [...pts, ...result.points]);
    if (!this.selectedGcpId() && result.points.length > 0) {
      this.selectedGcpId.set(result.points[0].id);
    }
    if (!result.message) {
      this.showImportPanel.set(false);
    }
  }

  onGcpAdded(gcp: GcpPoint): void {
    this.gcpPoints.update(pts => [...pts, gcp]);
    if (!this.selectedGcpId()) {
      this.selectedGcpId.set(gcp.id);
    }
  }

  onGcpRemoved(gcpId: string): void {
    this.gcpPoints.update(pts => pts.filter(g => g.id !== gcpId));
    this.marks.update(ms => ms.filter(m => m.gcpId !== gcpId));
    if (this.selectedGcpId() === gcpId) {
      const remaining = this.gcpPoints();
      this.selectedGcpId.set(remaining.length > 0 ? remaining[0].id : null);
    }
  }

  onMarkAdded(mark: GcpMark): void {
    // Substitui marca anterior do mesmo GCP na mesma imagem
    this.marks.update(ms => [
      ...ms.filter(m => !(m.gcpId === mark.gcpId && m.imageId === mark.imageId)),
      mark,
    ]);
  }

  onMarkRemoved(mark: GcpMark): void {
    this.marks.update(ms =>
      ms.filter(m => !(m.gcpId === mark.gcpId && m.imageId === mark.imageId))
    );
  }

  onOverlayClick(_event: MouseEvent): void {
    this.closeEditor.emit();
  }

  toggleImportPanel(): void {
    this.showImportPanel.update(v => !v);
  }

  // ==================== GENERATE ====================

  generate(): void {
    const file = this.editorService.toFile(this.gcpPoints(), this.marks());
    this.gcpFileReady.emit(file);
    this.closeEditor.emit();
  }
}