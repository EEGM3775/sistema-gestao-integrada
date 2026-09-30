/**
 * ExportBaseService
 *
 * Responsabilidades:
 *  - Tipos e interfaces de exportação (RawMeasurementEntry, CoordFormat, CsvSeparator)
 *  - Conversão WGS84 → UTM (TypeScript puro, 6-term meridian arc, 3 casas decimais)
 *  - Download de string / Blob como arquivo
 *  - Geração de nome de arquivo (convenção documentada em MEASUREMENT.md)
 *
 * NÃO contém lógica de formato (CSV, GeoJSON, DXF, etc.).
 * Todos os serviços de exportação estendem ou injetam este serviço.
 */

import { Injectable } from '@angular/core';
import proj4 from 'proj4';

// ============================================================================
// Tipos públicos
// ============================================================================

/** Estrutura "raw" de uma medição, desacoplada do componente que a cria. */
export interface RawMeasurementEntry {
  id: string;
  name: string;
  type: string;   // 'distance' | 'area' | 'volume' | 'height'
  value: number;
  unit: string;
  dataSource: string;
  coordinates: number[][];  // [[lat, lng, elev?], ...]
  createdAt: Date;
}

/** Sistema de referência de coordenadas escolhido pelo usuário. */
export type CoordFormat = 'wgs84' | 'utm';

/** Separador de campos para formatos tabulares (CSV, PNEZD). */
export type CsvSeparator = ',' | ';' | ' ';

// ============================================================================
// Service
// ============================================================================

@Injectable({ providedIn: 'root' })
export class ExportBaseService {

  // --------------------------------------------------------------------------
  // UTM
  // --------------------------------------------------------------------------

  /**
   * Converte WGS84 (lat, lng) → { easting, northing, zone, band } em metros.
   *
   * Usa proj4js — mesma engine do QGIS, OpenLayers e ArcGIS Online.
   * Garante resultados compatíveis com AutoCAD, Civil 3D e qualquer software GIS.
   *
   * Fonte única: todos os formatos de exportação e a UI usam este método.
   * NÃO duplicar este cálculo em outros lugares (ver docs/dominios/medicoes.md).
   */
  wgs84ToUtm(lat: number, lng: number): { easting: number; northing: number; zone: number; band: string } {
    const zone    = Math.floor((lng + 180) / 6) + 1;
    const isNorth = lat >= 0;
    // proj4 string para UTM WGS84 no fuso correto
    const utmProj = `+proj=utm +zone=${zone}${isNorth ? '' : ' +south'} +datum=WGS84 +units=m +no_defs`;
    // proj4 espera [lng, lat] (ordem GeoJSON), retorna [easting, northing]
    const [easting, northing] = proj4('EPSG:4326', utmProj, [lng, lat]);
    // Banda de latitude UTM (CDEFGHJKLMNPQRSTUVWX, sem I e O)
    const bands = 'CDEFGHJKLMNPQRSTUVWX';
    const band  = bands[Math.min(Math.max(Math.floor((lat + 80) / 8), 0), 19)];
    return { easting, northing, zone, band };
  }

  /**
   * Converte WGS84 (lat, lng) → string formatada pt-BR.
   * Exemplo: "333.000,123 E / 7.394.000,456 N  23K"
   *
   * Delega para wgs84ToUtm() — fonte única de conversão.
   * Use este método na UI; use wgs84ToUtm() quando precisar dos valores numéricos.
   */
  wgs84ToUtmStr(lat: number, lng: number): string {
    const { easting, northing, zone, band } = this.wgs84ToUtm(lat, lng);
    const fmt3 = (n: number) =>
      n.toLocaleString('pt-BR', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
    return `${fmt3(easting)} E / ${fmt3(northing)} N  ${zone}${band}`;
  }

  // --------------------------------------------------------------------------
  // Download
  // --------------------------------------------------------------------------

  /** Faz download de uma string como arquivo no browser. */
  downloadString(content: string, filename: string, mimeType = 'text/plain'): void {
    const blob = new Blob([content], { type: mimeType });
    this.downloadBlob(blob, filename);
  }

  /** Faz download de um Blob como arquivo no browser. */
  downloadBlob(blob: Blob, filename: string): void {
    const url  = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href     = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }

  // --------------------------------------------------------------------------
  // Nome de arquivo
  // --------------------------------------------------------------------------

  /**
   * Gera nome de arquivo segundo a convenção:
   *   medicoes_projeto_{id}_{formato}_{coordFormat}_{YYYYMMDD}.{ext}
   *
   * Formatos com CRS fixo (KML, GPX) devem omitir coordFormat passando null.
   */
  buildFilename(
    projectId: number | string,
    format: string,
    ext: string,
    coordFormat: CoordFormat | null = null
  ): string {
    const date  = this.todayStr();
    const parts = ['medicoes', 'projeto', String(projectId), format];
    if (coordFormat) parts.push(coordFormat);
    parts.push(date);
    return `${parts.join('_')}.${ext}`;
  }

  // --------------------------------------------------------------------------
  // Helpers de data
  // --------------------------------------------------------------------------

  /** Retorna data de hoje no formato YYYYMMDD. */
  todayStr(): string {
    const d = new Date();
    return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}`;
  }

  /** Formata Date para ISO string ou fallback. */
  toIsoString(date: Date | string): string {
    return date instanceof Date ? date.toISOString() : String(date);
  }

  // --------------------------------------------------------------------------
  // Escape XML
  // --------------------------------------------------------------------------

  escapeXml(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }
}

// ----------------------------------------------------------------------------
// Utilitários puros (não exportados — uso interno do módulo)
// ----------------------------------------------------------------------------

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}
