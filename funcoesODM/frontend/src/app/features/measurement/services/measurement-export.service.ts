/**
 * MeasurementExportService   Facade de Exportação
 *
 * Ponto único de entrada para o MeasurementTabComponent (e qualquer outro
 * componente) que queira exportar medições.
 *
 * Delega todo o trabalho pesado para os serviços especializados:
 *  - ExportBaseService      : UTM, download, nome de arquivo
 *  - ExportTabularService   : CSV, PNEZD, JSON
 *  - ExportGeoVectorService : GeoJSON, KML, GPX, WKT, GML
 *  - ExportCadService       : DXF, SVG, LandXML
 *
 * NÃO contém lógica de formato aqui  só orquestração.
 */

import { Injectable, inject } from '@angular/core';

import { ExportBaseService, RawMeasurementEntry, CoordFormat, CsvSeparator } from './export/export-base.service';
import { ExportTabularService }     from './export/export-tabular.service';
import { ExportGeoVectorService }   from './export/export-geo-vector.service';
import { ExportCadService }         from './export/export-cad.service';
import { ExportShapefileService }   from './export/export-shapefile.service';
import { ExportXlsxService }        from './export/export-xlsx.service';
import { ExportGeoPackageService }  from './export/export-geopackage.service';
import { ExportTopoJSONService }    from './export/export-topojson.service';
import { ExportPdfService }         from './export/export-pdf.service';
import { ExportGcpService }         from './export/export-gcp.service';
// Lógica de formatos:
//   ExportBaseService        → UTM, download, nome de arquivo
//   ExportTabularService     → CSV, PNEZD, JSON
//   ExportGeoVectorService   → GeoJSON, KML, GPX, WKT, GML
//   ExportCadService         → DXF, SVG, LandXML
//   ExportShapefileService   → Shapefile ZIP (fflate)
//   ExportXlsxService        → Excel XLSX (ExcelJS)
//   ExportGeoPackageService  → GeoPackage .gpkg (servidor Java, sqlite-jdbc)
//   ExportTopoJSONService    → TopoJSON (topologia GeoJSON, puro TS)
//   ExportPdfService         → Relatório PDF (jsPDF + jspdf-autotable)
//   ExportGcpService         → GCP .txt (Ground Control Points para ODM/WebODM)

// Re-exporta tipos para compatibilidade com importadores existentes
export type { RawMeasurementEntry, CoordFormat, CsvSeparator };

@Injectable({ providedIn: 'root' })
export class MeasurementExportService {

  private base      = inject(ExportBaseService);
  private tabular   = inject(ExportTabularService);
  private geoVector = inject(ExportGeoVectorService);
  private cad       = inject(ExportCadService);
  private shapefile = inject(ExportShapefileService);
  private xlsx      = inject(ExportXlsxService);
  private gpkg      = inject(ExportGeoPackageService);
  private topojson  = inject(ExportTopoJSONService);
  private pdf       = inject(ExportPdfService);
  private gcp       = inject(ExportGcpService);

  // ==========================================================================
  // Tabular
  // ==========================================================================

  exportToCSV(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', sep: CsvSeparator = ',', projectId: number | string = 0): void {
    this.base.downloadString(this.tabular.buildCSV(entries, coordFormat, sep), this.base.buildFilename(projectId, 'csv', 'csv', coordFormat), 'text/csv;charset=utf-8;');
  }

  exportToPNEZD(entries: RawMeasurementEntry[], sep: CsvSeparator = ';', projectId: number | string = 0, targetEpsg: number | null = null): string | undefined {
    const result = this.tabular.buildPNEZD(entries, sep, targetEpsg);
    this.base.downloadString(result.content, this.base.buildFilename(projectId, 'pnezd', 'txt', 'utm'), 'text/plain;charset=utf-8;');
    return result.warning;
  }

  exportToJSON(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0): void {
    this.base.downloadString(this.tabular.buildJSON(entries, coordFormat), this.base.buildFilename(projectId, 'json', 'json', coordFormat), 'application/json;charset=utf-8;');
  }

  // ==========================================================================
  // Geo-vetorial
  // ==========================================================================

  exportToGeoJSON(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0): void {
    this.base.downloadString(this.geoVector.buildGeoJSON(entries, coordFormat), this.base.buildFilename(projectId, 'geojson', 'geojson', coordFormat), 'application/geo+json;charset=utf-8;');
  }

  exportToKML(entries: RawMeasurementEntry[], projectId: number | string = 0): void {
    this.base.downloadString(this.geoVector.buildKML(entries), this.base.buildFilename(projectId, 'kml', 'kml', null), 'application/vnd.google-earth.kml+xml;charset=utf-8;');
  }

  exportToGPX(entries: RawMeasurementEntry[], projectId: number | string = 0): void {
    this.base.downloadString(this.geoVector.buildGPX(entries), this.base.buildFilename(projectId, 'gpx', 'gpx', null), 'application/gpx+xml;charset=utf-8;');
  }

  exportToWKT(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0, targetEpsg: number | null = null): string | undefined {
    const result = this.geoVector.buildWKT(entries, coordFormat, targetEpsg);
    this.base.downloadString(result.content, this.base.buildFilename(projectId, 'wkt', 'wkt', coordFormat), 'text/plain;charset=utf-8;');
    return result.warning;
  }

  exportToGML(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0, targetEpsg: number | null = null): string | undefined {
    const result = this.geoVector.buildGML(entries, coordFormat, targetEpsg);
    this.base.downloadString(result.content, this.base.buildFilename(projectId, 'gml', 'gml', coordFormat), 'application/gml+xml;charset=utf-8;');
    return result.warning;
  }

  // ==========================================================================
  // CAD / Engenharia
  // ==========================================================================

  exportToDXF(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'utm', projectId: number | string = 0, targetEpsg: number | null = null): void {
    this.base.downloadString(this.cad.buildDXF(entries, coordFormat, targetEpsg), this.base.buildFilename(projectId, 'dxf', 'dxf', coordFormat), 'application/dxf;charset=utf-8;');
  }

  exportToSVG(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0): void {
    this.base.downloadString(this.cad.buildSVG(entries, coordFormat), this.base.buildFilename(projectId, 'svg', 'svg', null), 'image/svg+xml;charset=utf-8;');
  }

  exportToLandXML(entries: RawMeasurementEntry[], projectId: number | string = 0, targetEpsg: number | null = null): void {
    this.base.downloadString(this.cad.buildLandXML(entries, targetEpsg), this.base.buildFilename(projectId, 'landxml', 'xml', 'utm'), 'application/xml;charset=utf-8;');
  }

  // ==========================================================================
  // Shapefile
  // ==========================================================================

  /**
   * Exporta todas as medições como Shapefile (ESRI .shp/.shx/.dbf/.prj).
   * Gera um .zip com arquivos separados para linhas (distance/height)
   * e polígonos (area/volume).
   *
   * @param targetEpsg EPSG do fuso de saída quando coordFormat='utm' e há multi-fuso.
   *   null = usa o fuso nativo de cada ponto (comportamento normal).
   */
  exportToShapefile(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0, targetEpsg: number | null = null): void {
    const zipBytes = this.shapefile.buildShapefileZip(entries, coordFormat, targetEpsg);
    this.base.downloadBlob(
      // `new Uint8Array(...)` copia para um ArrayBuffer comum: desde o TS 5.9 o
      // Blob recusa o `Uint8Array<ArrayBufferLike>`, que pode ser memória compartilhada.
      new Blob([new Uint8Array(zipBytes)], { type: 'application/zip' }),
      this.base.buildFilename(projectId, 'shapefile', 'zip', coordFormat)
    );
  }

  // ==========================================================================
  // XLSX
  // ==========================================================================

  /**
   * Exporta medições para planilha Excel com duas abas:
   *   - "Medicoes"   : resumo por medição
   *   - "Coordenadas": uma linha por ponto, lat/lng ou UTM
   *
   * async: ExcelJS.writeBuffer() retorna Promise.
   */
  async exportToXLSX(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0): Promise<void> {
    return this.xlsx.exportXlsx(entries, coordFormat, projectId);
  }

  // ==========================================================================
  // GeoPackage
  // ==========================================================================

  /**
   * Exporta medições para GeoPackage (.gpkg) — SQLite com geometrias GIS.
   * Requer o asset /sql-wasm.wasm (copiado de node_modules/sql.js/dist/).
   *
   * @param targetEpsg Quando coordFormat='utm' e há multi-fuso,
   *   EPSG do fuso de saída (ex: 32723). null = detecta pelo primeiro ponto.
   */
  async exportToGeoPackage(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0, targetEpsg: number | null = null): Promise<void> {
    return this.gpkg.exportGeoPackage(entries, coordFormat, projectId, targetEpsg);
  }

  // ==========================================================================
  // TopoJSON
  // ==========================================================================

  /**
   * Exporta medições como TopoJSON — JSON de topologia compatível com D3.js.
   * CRS: WGS84 fixo (sem popup de multi-fuso).
   */
  exportToTopoJSON(entries: RawMeasurementEntry[], projectId: number | string = 0): void {
    this.topojson.exportTopoJSON(entries, projectId);
  }

  // ==========================================================================
  // PDF
  // ==========================================================================

  /**
   * Gera um relatório PDF com tabela de medições e tabela de coordenadas.
   * Gerado inteiramente no browser via jsPDF + jspdf-autotable.
   * CRS configurado pelo usuário no modal (WGS84 ou UTM).
   * Não exige popup de multi-fuso: cada linha já inclui o fuso individual.
   */
  exportToPDF(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84', projectId: number | string = 0): void {
    this.pdf.exportPdf(entries, coordFormat, projectId);
  }

  // ==========================================================================
  // GCP (Ground Control Points para ODM/WebODM)
  // ==========================================================================

  /**
   * Gera e faz download do arquivo GCP (.txt) para uso no ODM/WebODM.
   * Apenas medicoes do tipo 'distance' e 'height' geram linhas GCP.
   * CRS fixo: EPSG:4326 — sem popup de multi-fuso.
   *
   * Instrucoes de uso:
   *   1. Medir pontos de referencia no viewer
   *   2. Exportar GCP.txt com este metodo
   *   3. Editar pixel_x / pixel_y no arquivo (coordenadas de pixel nas imagens)
   *   4. Re-enviar imagens + GCP.txt para o ODM e reprocessar
   */
  exportToGCP(entries: RawMeasurementEntry[], projectId: number | string = 0): void {
    this.gcp.exportGCP(entries, projectId);
  }

  // ==========================================================================
  // Retrocompatibilidade (deprecated)
  // ==========================================================================

  /** @deprecated Use exportToCSV() com projectId. */
  exportRawToCSV(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84'): string {
    return this.tabular.buildCSV(entries, coordFormat, ',');
  }

  /** @deprecated Use exportToGeoJSON() com projectId. */
  exportRawToGeoJSON(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84'): string {
    return this.geoVector.buildGeoJSON(entries, coordFormat);
  }

  /** @deprecated Use exportTo*() com projectId. */
  downloadString(content: string, filename: string, mimeType: string): void {
    this.base.downloadString(content, filename, mimeType);
  }
}
