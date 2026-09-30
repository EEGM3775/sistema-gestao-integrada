/**
 * MeasurementExportModalComponent
 *
 * Modal standalone de exportação de medições.
 * Recebe a lista de medições e o projectId como @Input,
 * e emite o evento (closed) quando o usuário fecha o modal.
 *
 * O componente é autossuficiente: injeta MeasurementExportService
 * e gerencia o CoordFormat localmente.
 */

import {
  Component, Input, Output, EventEmitter,
  signal, inject, computed, OnInit,
  ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';

import {
  MeasurementExportService,
  CoordFormat,
  RawMeasurementEntry
} from '../../services/measurement-export.service';
import { UtmZoneAnalyzerService, ZoneAnalysis } from '../../services/export/utm-zone-analyzer.service';

@Component({
    selector: 'app-measurement-export-modal',
    imports: [CommonModule],
    templateUrl: './measurement-export-modal.component.html',
    styleUrls: ['./measurement-export-modal.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class MeasurementExportModalComponent implements OnInit {

  @Input({ required: true }) projectId!: number;
  @Input({ required: true }) measurements: RawMeasurementEntry[] = [];

  @Output() closed = new EventEmitter<void>();

  coordFormat = signal<CoordFormat>('wgs84');

  // Analise de fusos UTM — calculada uma vez ao abrir o modal.
  zoneAnalysis = signal<ZoneAnalysis | null>(null);

  // EPSG alvo escolhido pelo usuario no popup multi-fuso.
  // null   = exportar em lat/lng WGS84 (seguro, padrao)
  // number = reprojetar todos os pontos para aquele EPSG (ex: 32722 = fuso 22S)
  selectedEpsg = signal<number | null>(null);

  // Formato pendente de confirmacao quando o popup esta aberto.
  // null = popup fechado.
  pendingExport = signal<'wkt' | 'gml' | 'pnezd' | 'dxf' | 'landxml' | 'shapefile' | 'geopackage' | null>(null);

  // Rotulos legiveis dos fusos presentes (ex: '22S e 23S') para o titulo do popup.
  fusoLabels = computed(() =>
    this.zoneAnalysis()?.epsgsPresent
      .map(e => `${e % 100}${e >= 32700 ? 'S' : 'N'}`)
      .join(' e ') ?? ''
  );

  // Lista de opcoes: um item por EPSG presente nas medicoes.
  availableZones = computed(() =>
    this.zoneAnalysis()?.epsgsPresent.map(epsg => ({
      epsg,
      label: `Fuso ${epsg % 100}${epsg >= 32700 ? 'S' : 'N'}`
    })) ?? []
  );

  private exportService = inject(MeasurementExportService);
  private analyzer      = inject(UtmZoneAnalyzerService);

  ngOnInit(): void {
    // Roda a analise de fusos na abertura do modal.
    // O resultado e exibido como banner antes do download.
    if (this.measurements.length > 0) {
      this.zoneAnalysis.set(this.analyzer.analyzeEntries(this.measurements));
    }
  }

  close(): void { this.closed.emit(); }

  // --------------------------------------------------------------------------
  // Ações de exportação (delegam ao service facade)
  // --------------------------------------------------------------------------

  exportCSV(): void {
    if (!this.measurements.length) return;
    this.exportService.exportToCSV(this.measurements, this.coordFormat(), ',', this.projectId);
    this.close();
  }

  exportGeoJSON(): void {
    if (!this.measurements.length) return;
    this.exportService.exportToGeoJSON(this.measurements, this.coordFormat(), this.projectId);
    this.close();
  }

  exportKML(): void {
    if (!this.measurements.length) return;
    this.exportService.exportToKML(this.measurements, this.projectId);
    this.close();
  }

  exportGPX(): void {
    if (!this.measurements.length) return;
    this.exportService.exportToGPX(this.measurements, this.projectId);
    this.close();
  }

  exportWKT(): void {
    if (!this.measurements.length) return;
    // WKT usa UTM so quando o usuario escolheu UTM — so exibe popup nesse caso.
    if (this.coordFormat() === 'utm' && this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('wkt');
      return;
    }
    this.exportService.exportToWKT(this.measurements, this.coordFormat(), this.projectId, null);
    this.close();
  }

  exportGML(): void {
    if (!this.measurements.length) return;
    if (this.coordFormat() === 'utm' && this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('gml');
      return;
    }
    this.exportService.exportToGML(this.measurements, this.coordFormat(), this.projectId, null);
    this.close();
  }

  exportPNEZD(): void {
    if (!this.measurements.length) return;
    // PNEZD e sempre UTM — exibe popup independente do seletor de coordenadas.
    if (this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('pnezd');
      return;
    }
    this.exportService.exportToPNEZD(this.measurements, ';', this.projectId, null);
    this.close();
  }

  confirmExport(): void {
    const fmt  = this.pendingExport();
    const epsg = this.selectedEpsg();
    if (!fmt) return;
    switch (fmt) {
      case 'wkt':       this.exportService.exportToWKT(this.measurements, this.coordFormat(), this.projectId, epsg);           break;
      case 'gml':       this.exportService.exportToGML(this.measurements, this.coordFormat(), this.projectId, epsg);           break;
      case 'pnezd':     this.exportService.exportToPNEZD(this.measurements, ';', this.projectId, epsg);                        break;
      case 'dxf':       this.exportService.exportToDXF(this.measurements, this.coordFormat(), this.projectId, epsg);           break;
      case 'landxml':   this.exportService.exportToLandXML(this.measurements, this.projectId, epsg);                          break;
      case 'shapefile':   this.exportService.exportToShapefile(this.measurements, this.coordFormat(), this.projectId, epsg);              break;
      case 'geopackage':  this.exportService.exportToGeoPackage(this.measurements, this.coordFormat(), this.projectId, epsg).then(() => {}); break;
    }
    this.pendingExport.set(null);
    this.close();
  }

  cancelExport(): void {
    this.pendingExport.set(null);
    this.selectedEpsg.set(null);
  }

  exportLandXML(): void {
    if (!this.measurements.length) return;
    // LandXML e sempre UTM — exibe popup quando ha multiplos fusos, igual ao DXF.
    if (this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('landxml');
      return;
    }
    this.exportService.exportToLandXML(this.measurements, this.projectId, null);
    this.close();
  }

  exportDXF(): void {
    if (!this.measurements.length) return;
    // DXF usa UTM por padrão (CAD trabalha em metros).
    // Quando há múltiplos fusos UTM, exibe popup para o usuário decidir.
    if (this.coordFormat() === 'utm' && this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('dxf');
      return;
    }
    this.exportService.exportToDXF(this.measurements, this.coordFormat(), this.projectId, null);
    this.close();
  }

  exportSVG(): void {
    if (!this.measurements.length) return;
    this.exportService.exportToSVG(this.measurements, this.coordFormat(), this.projectId);
    this.close();
  }

  exportJSON(): void {
    if (!this.measurements.length) return;
    this.exportService.exportToJSON(this.measurements, this.coordFormat(), this.projectId);
    this.close();
  }

  exportShapefile(): void {
    if (!this.measurements.length) return;
    // Shapefile usa UTM quando o usuario selecionou UTM.
    // Exibe popup quando ha multiplos fusos, igual ao DXF.
    if (this.coordFormat() === 'utm' && this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('shapefile');
      return;
    }
    this.exportService.exportToShapefile(this.measurements, this.coordFormat(), this.projectId, null);
    this.close();
  }

  exportXLSX(): void {
    if (!this.measurements.length) return;
    // XLSX nao exige popup de multi-fuso: cada linha da aba Coordenadas
    // inclui a coluna "Fuso" individual por ponto — sem ambiguidade.
    this.exportService.exportToXLSX(this.measurements, this.coordFormat(), this.projectId)
      .then(() => this.close());
  }

  exportGeoPackage(): void {
    if (!this.measurements.length) return;
    // GeoPackage com UTM + multi-fuso requer popup, igual ao Shapefile.
    if (this.coordFormat() === 'utm' && this.zoneAnalysis()?.isMultiZone) {
      this.pendingExport.set('geopackage');
      return;
    }
    this.exportService.exportToGeoPackage(this.measurements, this.coordFormat(), this.projectId, null)
      .then(() => this.close());
  }
  exportTopoJSON(): void {
    if (!this.measurements.length) return;
    // TopoJSON usa WGS84 fixo (como GeoJSON/KML/GPX) - sem popup de multi-fuso.
    this.exportService.exportToTopoJSON(this.measurements, this.projectId);
    this.close();
  }

  exportPDF(): void {
    if (!this.measurements.length) return;
    // PDF inclui coluna "Fuso" individual por ponto na tabela de coordenadas
    // — nao ha ambiguidade, logo nao exige popup de multi-fuso.
    this.exportService.exportToPDF(this.measurements, this.coordFormat(), this.projectId);
    this.close();
  }

  exportGCP(): void {
    if (!this.measurements.length) return;
    // GCP usa EPSG:4326 fixo — sem popup de multi-fuso.
    // Apenas medicoes do tipo 'distance' e 'height' geram linhas no arquivo.
    this.exportService.exportToGCP(this.measurements, this.projectId);
    this.close();
  }
}