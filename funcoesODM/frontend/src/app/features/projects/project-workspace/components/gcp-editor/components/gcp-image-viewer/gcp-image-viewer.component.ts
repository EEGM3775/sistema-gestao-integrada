/**
 * GcpImageViewerComponent
 *
 * Visualizador de imagens com navegacao, zoom (100%–1000%), HUD de pixel
 * e sistema de pinos de marcacao de GCPs.
 * Responsabilidades: navegar por imagens, fazer zoom, capturar cliques em pixels
 * nativos e emitir GcpMark para o pai.
 */

import {
  Component, Input, Output, EventEmitter,
  signal, computed, input, ElementRef, ViewChild, ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ProjectImage } from '../../../../../models/project.model';
import { GcpPoint, GcpMark } from '../../models/gcp-mark.model';

@Component({
    selector: 'app-gcp-image-viewer',
    imports: [CommonModule],
    changeDetection: ChangeDetectionStrategy.OnPush,
    styleUrl: './gcp-image-viewer.component.scss',
    template: `
@if (images().length === 0) {
      <div class="viewer-empty">
        Nenhuma imagem no chunk. Adicione fotos antes de marcar GCPs.
      </div>
    } @else {

      <!-- Barra de navegacao -->
      <div class="viewer-nav">
        <button
          class="nav-btn"
          [disabled]="currentIndex() === 0"
          (click)="prevImage()"
        >&lt; Anterior</button>
        <div class="viewer-name">
          <span class="filename">{{ currentImage().originalFilename }}</span>
          <span class="page">{{ currentIndex() + 1 }} / {{ images().length }}</span>
        </div>
        <button
          class="nav-btn"
          [disabled]="currentIndex() === images().length - 1"
          (click)="nextImage()"
        >Proxima &gt;</button>
      </div>

      <!-- Barra de zoom + HUD pixel -->
      <div class="zoom-bar">
        <button class="zoom-btn" (click)="zoomOut()" [disabled]="zoom() <= ZOOM_MIN" title="Reduzir zoom">−</button>
        <span class="zoom-label">{{ (zoom() * 100).toFixed(0) }}%</span>
        <button class="zoom-btn" (click)="zoomIn()" [disabled]="zoom() >= ZOOM_MAX" title="Aumentar zoom">+</button>
        @if (zoom() > 1) {
          <button class="zoom-reset" (click)="resetZoom()" title="Resetar zoom">Ajustar</button>
          <span class="zoom-hint">Role / arraste para navegar</span>
        }
        <span class="zoom-separator"></span>
        @if (cursorPixel()) {
          <span class="cursor-pixel-hud">x&nbsp;{{ cursorPixel()!.x }}&nbsp;&nbsp;y&nbsp;{{ cursorPixel()!.y }}</span>
        } @else {
          <span class="cursor-pixel-placeholder">x —&nbsp;&nbsp;y —</span>
        }
      </div>

      <!-- Imagem + marcadores -->
      <div class="image-container" [class.zoomed]="zoom() > 1">
        <div class="image-wrapper"
             #imageWrapper
             [style.width]="zoom() > 1 ? (zoom() * 100) + '%' : 'auto'"
        >
          <img
            #viewerImg
            class="viewer-img"
            [class.cursor-crosshair]="!!selectedGcpId()"
            [class.zoomed-img]="zoom() > 1"
            [src]="imgUrl(currentImage())"
            [alt]="currentImage().originalFilename"
            (click)="onImageClick($event)"
            (mousemove)="onImageMouseMove($event)"
            (mouseleave)="onImageMouseLeave()"
            draggable="false"
          />

          <!-- Pinos de marcacao -->
          @for (mark of marksForCurrentImage(); track mark.gcpId) {
            <div
              class="mark-pin"
              [style.left.%]="mark.pctX * 100"
              [style.top.%]="mark.pctY * 100"
              [style.border-color]="colorOf(mark.gcpId)"
              [title]="labelOf(mark.gcpId) + ' — pixel: ' + mark.pixelX + ', ' + mark.pixelY"
            >
              <span class="pin-inner" [style.background]="colorOf(mark.gcpId)">
                {{ shortLabel(mark.gcpId) }}
              </span>
            </div>
          }
        </div>
      </div>

      <!-- Lista de marcas nesta imagem -->
      @if (marksForCurrentImage().length > 0) {
        <div class="marks-on-image">
          @for (mark of marksForCurrentImage(); track mark.gcpId) {
            <div class="mark-row">
              <span class="dot" [style.background]="colorOf(mark.gcpId)"></span>
              <span class="mark-name">{{ labelOf(mark.gcpId) }}</span>
              <span class="mark-px">x={{ mark.pixelX }} y={{ mark.pixelY }}</span>
              <button class="btn-remove" (click)="onRemoveMark(mark)" title="Remover">
                <svg viewBox="0 0 16 16" fill="currentColor" width="11" height="11">
                  <path d="M11 1.5v1h3.5a.5.5 0 0 1 0 1h-.538l-.853 10.66A2 2 0 0 1 11.115 16h-6.23a2 2 0 0 1-1.994-1.84L2.038 3.5H1.5a.5.5 0 0 1 0-1H5v-1A1.5 1.5 0 0 1 6.5 0h3A1.5 1.5 0 0 1 11 1.5m-5 0v1h4v-1a.5.5 0 0 0-.5-.5h-3a.5.5 0 0 0-.5.5M4.5 5.029l.5 8.5a.5.5 0 1 0 .998-.058l-.5-8.5a.5.5 0 1 0-.998.058m6.53-.528a.5.5 0 0 0-.528.47l-.5 8.5a.5.5 0 0 0 .998.058l.5-8.5a.5.5 0 0 0-.47-.528M8 4.5a.5.5 0 0 0-.5.5v8.5a.5.5 0 0 0 1 0V5a.5.5 0 0 0-.5-.5"/>
                </svg>
              </button>
            </div>
          }
        </div>
      }

    }
  `
})
export class GcpImageViewerComponent {

  @Input({ required: true }) projectId!: number;

  // Signal inputs — o computed() reage automaticamente a mudancas de @Input
  readonly images       = input.required<ProjectImage[]>();
  readonly marks        = input.required<GcpMark[]>();
  readonly gcpPoints    = input.required<GcpPoint[]>();
  readonly selectedGcpId = input<string | null>(null);

  @Output() markAdded   = new EventEmitter<GcpMark>();
  @Output() markRemoved = new EventEmitter<GcpMark>();
  /** Emite o novo selectedGcpId apos auto-selecao do proximo GCP sem marca. */
  @Output() nextGcpSuggested = new EventEmitter<string>();

  @ViewChild('viewerImg')    viewerImgRef?:    ElementRef<HTMLImageElement>;
  @ViewChild('imageWrapper') imageWrapperRef?: ElementRef<HTMLDivElement>;

  readonly ZOOM_STEP = 1;
  readonly ZOOM_MAX  = 10;
  readonly ZOOM_MIN  = 1;

  private readonly PALETTE = [
    '#ff4444', '#44aaff', '#44ff88', '#ffaa00',
    '#aa44ff', '#ff44aa', '#00ccff', '#ffff44'
  ];

  currentIndex = signal(0);
  zoom         = signal(1);
  cursorPixel  = signal<{ x: number; y: number } | null>(null);

  currentImage = computed(() => this.images()[this.currentIndex()]);

  marksForCurrentImage = computed(() => {
    const img = this.currentImage();
    if (!img) return [];
    return this.marks().filter(m => m.imageId === img.id);
  });

  // ==================== ZOOM ====================

  zoomIn():    void { this.zoom.update(z => Math.min(this.ZOOM_MAX, +(z + this.ZOOM_STEP).toFixed(1))); }
  zoomOut():   void { this.zoom.update(z => Math.max(this.ZOOM_MIN, +(z - this.ZOOM_STEP).toFixed(1))); }
  resetZoom(): void { this.zoom.set(1); }

  // ==================== HUD ====================

  onImageMouseMove(event: MouseEvent): void {
    const img = this.viewerImgRef?.nativeElement;
    if (!img) return;
    const iRect = img.getBoundingClientRect();
    const pctX  = (event.clientX - iRect.left) / iRect.width;
    const pctY  = (event.clientY - iRect.top)  / iRect.height;
    if (pctX < 0 || pctX > 1 || pctY < 0 || pctY > 1) { this.cursorPixel.set(null); return; }
    this.cursorPixel.set({
      x: Math.round(pctX * img.naturalWidth),
      y: Math.round(pctY * img.naturalHeight),
    });
  }

  onImageMouseLeave(): void {
    this.cursorPixel.set(null);
  }

  // ==================== NAVIGATION ====================

  prevImage(): void { this.currentIndex.update(i => Math.max(0, i - 1)); this.zoom.set(1); }
  nextImage(): void { this.currentIndex.update(i => Math.min(this.images().length - 1, i + 1)); this.zoom.set(1); }

  // ==================== CLICK ====================

  onImageClick(event: MouseEvent): void {
    const gcpId = this.selectedGcpId();
    const image = this.currentImage();
    if (!gcpId || !image) return;

    const img     = this.viewerImgRef!.nativeElement;
    const wrapper = this.imageWrapperRef!.nativeElement;

    const wRect = wrapper.getBoundingClientRect();
    const pctX  = (event.clientX - wRect.left) / wRect.width;
    const pctY  = (event.clientY - wRect.top)  / wRect.height;

    const iRect  = img.getBoundingClientRect();
    const iPctX  = (event.clientX - iRect.left) / iRect.width;
    const iPctY  = (event.clientY - iRect.top)  / iRect.height;
    const pixelX = Math.round(iPctX * img.naturalWidth);
    const pixelY = Math.round(iPctY * img.naturalHeight);

    this.markAdded.emit({
      gcpId,
      imageId: image.id,
      imageOriginalFilename: image.originalFilename,
      pixelX,
      pixelY,
      pctX,
      pctY,
    });

    // Sugere o proximo GCP sem marca nesta imagem
    const idx = this.gcpPoints().findIndex(g => g.id === gcpId);
    for (let i = 1; i <= this.gcpPoints().length; i++) {
      const next = this.gcpPoints()[(idx + i) % this.gcpPoints().length];
      const jaTemMarca = this.marks().some(
        m => m.gcpId === next.id && m.imageId === image.id
      );
      if (!jaTemMarca) {
        this.nextGcpSuggested.emit(next.id);
        return;
      }
    }
  }

  onRemoveMark(mark: GcpMark): void {
    this.markRemoved.emit(mark);
  }

  // ==================== HELPERS ====================

  imgUrl(image: ProjectImage): string {
    return `/api/v1/projects/${this.projectId}/images/${image.id}/thumbnail`;
  }

  colorOf(gcpId: string): string {
    const idx = this.gcpPoints().findIndex(g => g.id === gcpId);
    return this.PALETTE[Math.max(0, idx) % this.PALETTE.length];
  }

  labelOf(gcpId: string): string {
    return this.gcpPoints().find(g => g.id === gcpId)?.label ?? gcpId;
  }

  shortLabel(gcpId: string): string {
    const label = this.labelOf(gcpId);
    const match = label.match(/(\d+)$/);
    return match ? match[1] : label.slice(0, 2);
  }
}
