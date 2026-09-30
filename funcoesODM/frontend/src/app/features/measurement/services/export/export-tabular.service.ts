/**
 * ExportTabularService
 *
 * Formatos tabulares (linha/coluna):
 *  - CSV  : 1 linha por ponto, separador configurável, BOM UTF-8
 *  - PNEZD: sempre UTM; Ponto, Norte, Este, Z, Descrição
 *  - JSON : array de medições com pontos aninhados
 *
 * Cada método retorna a string pronta para download.
 * O download em si é responsabilidade do ExportBaseService / facade.
 */

import { Injectable, inject } from '@angular/core';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat,
  CsvSeparator
} from './export-base.service';
import { UtmZoneAnalyzerService } from './utm-zone-analyzer.service';

// ---------------------------------------------------------------------------
// Rótulos de tipo de medição
// ---------------------------------------------------------------------------
const TYPE_LABELS: Record<string, string> = {
  distance: 'Distancia',
  area:     'Area',
  volume:   'Volume',
  height:   'Altura'
};

@Injectable({ providedIn: 'root' })
export class ExportTabularService {

  private base     = inject(ExportBaseService);
  private analyzer = inject(UtmZoneAnalyzerService);

  // ==========================================================================
  // CSV — 1 linha por ponto
  // ==========================================================================

  /**
   * Exporta para CSV.
   *
   * Modelo WGS84:
   *   ID_MEDICAO,NOME,TIPO,VALOR,UNIDADE,N_PONTO,LAT,LNG,ELEV_M,DESCRICAO
   *
   * Modelo UTM:
   *   ID_MEDICAO;NOME;TIPO;VALOR;UNIDADE;N_PONTO;NORTE;ESTE;ELEV_M;FUSO;DESCRICAO
   *
   * @param entries    Lista de medições
   * @param coordFormat 'wgs84' | 'utm'
   * @param sep         Separador: ',' | ';' | ' '
   */
  buildCSV(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat = 'wgs84',
    sep: CsvSeparator = ','
  ): string {
    const BOM = '\uFEFF';

    const headers = coordFormat === 'utm'
      ? ['ID_MEDICAO', 'NOME', 'TIPO', 'VALOR', 'UNIDADE', 'N_PONTO', 'NORTE', 'ESTE', 'ELEV_M', 'FUSO', 'DESCRICAO']
      : ['ID_MEDICAO', 'NOME', 'TIPO', 'VALOR', 'UNIDADE', 'N_PONTO', 'LAT', 'LNG', 'ELEV_M', 'DESCRICAO'];

    const rows: string[][] = [];

    for (const m of entries) {
      const tipo  = TYPE_LABELS[m.type] ?? m.type;
      const valor = m.value.toFixed(4);
      const data  = this.base.toIsoString(m.createdAt);

      for (let i = 0; i < m.coordinates.length; i++) {
        const c    = m.coordinates[i];
        const lat  = c[0];
        const lng  = c[1];
        const elev = c[2] !== undefined && c[2] !== null ? c[2].toFixed(3) : '';

        if (coordFormat === 'utm') {
          const utm  = this.base.wgs84ToUtm(lat, lng);
          const fuso = `${utm.zone}${utm.band}`;
          rows.push([
            m.id, m.name, tipo, valor, m.unit,
            String(i + 1),
            utm.northing.toFixed(3),
            utm.easting.toFixed(3),
            elev,
            fuso,
            data
          ]);
        } else {
          rows.push([
            m.id, m.name, tipo, valor, m.unit,
            String(i + 1),
            lat.toFixed(7),
            lng.toFixed(7),
            elev,
            data
          ]);
        }
      }
    }

    const q = (s: string) => `"${String(s).replace(/"/g, '""')}"`;
    const lines = [
      headers.map(q).join(sep),
      ...rows.map(row => row.map(q).join(sep))
    ];

    return BOM + lines.join('\n');
  }

  // ==========================================================================
  // PNEZD — sempre UTM
  // ==========================================================================

  /**
   * Exporta para PNEZD (Point, Norte, Este, Z, Descrição).
   * CRS fixo: UTM WGS84. Separador configurável.
   *
   * Modelo:
   *   N_PONTO;NORTE;ESTE;ELEV_M;DESCRICAO
   *   1;7399000.456;333000.123;854.200;Dist. A-B (pt 1) — 2026-02-28
   */
  /**
   * @returns { content, warning? }
   *   warning: aviso PT-BR se pontos de fusos UTM diferentes forem detectados.
   *   Neste caso o arquivo ainda e exportado em UTM (o formato nao suporta
   *   fallback), mas a coluna FUSO e incluida em cada linha para que o
   *   consumidor possa identificar e separar os pontos por fuso.
   */
  buildPNEZD(
    entries: RawMeasurementEntry[],
    sep: CsvSeparator = ';',
    targetEpsg: number | null = null
  ): { content: string; warning?: string } {
    const analysis    = this.analyzer.analyzeEntries(entries);
    const reprZone    = targetEpsg !== null ? targetEpsg % 100 : analysis.dominantZone;
    const reprIsNorth = targetEpsg !== null ? targetEpsg < 32700 : analysis.dominantZoneIsNorth;

    let warning: string | undefined;
    if (analysis.isMultiZone) {
      warning = targetEpsg !== null
        ? this.analyzer.buildWarningMessage(analysis, 'PNEZD', 'reprojected-to-zone', targetEpsg)
        : this.analyzer.buildWarningMessage(analysis, 'PNEZD', 'warn-only');
    }

    const BOM  = '\uFEFF';
    const header = ['N_PONTO', 'NORTE', 'ESTE', 'ELEV_M', 'FUSO', 'DESCRICAO'].join(sep);
    const rows: string[] = [];
    let globalPt = 1;

    for (const m of entries) {
      const data = this.base.toIsoString(m.createdAt).slice(0, 10);
      for (let i = 0; i < m.coordinates.length; i++) {
        const c   = m.coordinates[i];
        // Se targetEpsg definido: forca aquele fuso para todos os pontos.
        const utm = (analysis.isMultiZone && targetEpsg !== null)
          ? this.analyzer.projectToZone(c[0], c[1], reprZone, reprIsNorth)
          : this.base.wgs84ToUtm(c[0], c[1]);
        const elev = c[2] !== undefined && c[2] !== null ? c[2].toFixed(3) : '0.000';
        const fuso = `${utm.zone}${utm.band}`;
        const desc = `${m.name} (pt ${i + 1}) — ${data}`;

        rows.push([
          String(globalPt++),
          utm.northing.toFixed(3),
          utm.easting.toFixed(3),
          elev,
          fuso,
          desc
        ].join(sep));
      }
    }

    return { content: BOM + [header, ...rows].join('\n'), warning };
  }

  // ==========================================================================
  // JSON
  // ==========================================================================

  /**
   * Exporta para JSON estruturado (array de medições com pontos aninhados).
   * Campo 'coordFormat' registra o sistema escolhido.
   */
  buildJSON(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat = 'wgs84'
  ): string {
    const output = entries.map(m => {
      const points = m.coordinates.map((c, i) => {
        const elev   = c[2] !== undefined && c[2] !== null ? c[2] : null;
        const hasElev = elev !== null;

        if (coordFormat === 'utm') {
          const utm = this.base.wgs84ToUtm(c[0], c[1]);
          return {
            pt: i + 1,
            norte: +utm.northing.toFixed(3),
            este:  +utm.easting.toFixed(3),
            ...(hasElev ? { elev_m: +elev!.toFixed(3) } : {}),
            fuso: `${utm.zone}${utm.band}`
          };
        } else {
          return {
            pt: i + 1,
            lat: +c[0].toFixed(7),
            lng: +c[1].toFixed(7),
            ...(hasElev ? { elev_m: +elev!.toFixed(3) } : {})
          };
        }
      });

      return {
        id:          m.id,
        nome:        m.name,
        tipo:        TYPE_LABELS[m.type] ?? m.type,
        valor:       m.value,
        unidade:     m.unit,
        fonteDados:  m.dataSource,
        coordFormat,
        criadoEm:    this.base.toIsoString(m.createdAt),
        pontos:      points
      };
    });

    return JSON.stringify(output, null, 2);
  }
}
