/**
 * ExportXlsxService
 *
 * Gera planilha Excel (.xlsx) com duas abas:
 *  - "Medicoes"   : resumo — uma linha por medição (id, nome, tipo, valor, n° pontos…)
 *  - "Coordenadas": detalhe — uma linha por ponto (lat/lng ou UTM, elevação)
 *
 * Formatação profissional:
 *  - Cabeçalho azul escuro, texto branco, negrito
 *  - Linhas alternadas em branco / azul-claro
 *  - Bordas finas em todas as células
 *  - Coluna de valor com 3 casas decimais
 *  - Primeira linha congelada (freeze pane)
 *  - Larguras ajustadas por coluna
 *
 * Dependência: ExcelJS (npm install exceljs)
 * Download: ExportBaseService.downloadBlob()
 *
 * Como é async (writeBuffer retorna Promise), a facade e o modal também são async.
 */

import { Injectable, inject } from '@angular/core';
import * as ExcelJS from 'exceljs';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat
} from './export-base.service';

// ============================================================================
// Constantes de estilo
// ============================================================================

const COLOR_HEADER_BG   = 'FF1A3A5C';   // azul marinho
const COLOR_HEADER_FG   = 'FFFFFFFF';   // branco
const COLOR_ALT_ROW     = 'FFE8F0F7';   // azul-claro para linhas pares
const COLOR_BORDER      = 'FFB0BEC5';   // cinza médio

const TYPE_LABELS: Record<string, string> = {
  distance: 'Distancia',
  area:     'Area',
  volume:   'Volume',
  height:   'Altura'
};

/** Borda fina padrão usada em todas as células de dados. */
const THIN_BORDER: Partial<ExcelJS.Borders> = {
  top:    { style: 'thin', color: { argb: COLOR_BORDER } },
  left:   { style: 'thin', color: { argb: COLOR_BORDER } },
  bottom: { style: 'thin', color: { argb: COLOR_BORDER } },
  right:  { style: 'thin', color: { argb: COLOR_BORDER } }
};

// ============================================================================
// Service
// ============================================================================

@Injectable({ providedIn: 'root' })
export class ExportXlsxService {

  private base = inject(ExportBaseService);

  // --------------------------------------------------------------------------
  // Ponto de entrada público
  // --------------------------------------------------------------------------

  /**
   * Gera o XLSX completo e faz o download no browser.
   * async porque ExcelJS.writeBuffer() retorna Promise.
   */
  async exportXlsx(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat,
    projectId: number | string
  ): Promise<void> {
    const wb = new ExcelJS.Workbook();
    wb.creator  = 'FuncoesODM';
    wb.created  = new Date();
    wb.modified = new Date();

    this.buildSheetMedicoes(wb, entries);
    this.buildSheetCoordenadas(wb, entries, coordFormat);

    const buffer    = await wb.xlsx.writeBuffer();
    const blob      = new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    });
    const filename  = this.base.buildFilename(projectId, 'xlsx', 'xlsx', coordFormat);
    this.base.downloadBlob(blob, filename);
  }

  // --------------------------------------------------------------------------
  // Aba "Medicoes" — resumo, uma linha por medição
  // --------------------------------------------------------------------------

  private buildSheetMedicoes(wb: ExcelJS.Workbook, entries: RawMeasurementEntry[]): void {
    const ws = wb.addWorksheet('Medicoes', {
      views: [{ state: 'frozen', ySplit: 1 }]
    });

    ws.columns = [
      { key: 'id',         width: 36  },
      { key: 'nome',       width: 30  },
      { key: 'tipo',       width: 14  },
      { key: 'valor',      width: 14  },
      { key: 'unidade',    width: 10  },
      { key: 'n_pontos',   width: 10  },
      { key: 'fonte',      width: 18  },
      { key: 'criado_em',  width: 20  },
    ];

    // Cabeçalho
    const headers = ['ID', 'Nome', 'Tipo', 'Valor', 'Unidade', 'N. Pontos', 'Fonte de Dados', 'Criado Em'];
    const headerRow = ws.addRow(headers);
    this.styleHeaderRow(headerRow, headers.length);

    // Dados
    for (let i = 0; i < entries.length; i++) {
      const e   = entries[i];
      const row = ws.addRow([
        e.id,
        e.name,
        TYPE_LABELS[e.type] ?? e.type,
        e.value,
        e.unit,
        e.coordinates.length,
        e.dataSource,
        this.fmtDate(e.createdAt)
      ]);
      this.styleDataRow(row, 8, i);

      // Coluna "Valor" (D) com 3 casas decimais
      const valorCell = row.getCell(4);
      valorCell.numFmt = '#,##0.000';
    }
  }

  // --------------------------------------------------------------------------
  // Aba "Coordenadas" — detalhe, uma linha por ponto
  // --------------------------------------------------------------------------

  private buildSheetCoordenadas(
    wb: ExcelJS.Workbook,
    entries: RawMeasurementEntry[],
    fmt: CoordFormat
  ): void {
    const ws = wb.addWorksheet('Coordenadas', {
      views: [{ state: 'frozen', ySplit: 1 }]
    });

    const isUtm = fmt === 'utm';

    if (isUtm) {
      ws.columns = [
        { key: 'id_med',    width: 36 },
        { key: 'nome',      width: 26 },
        { key: 'tipo',      width: 13 },
        { key: 'n_ponto',   width: 10 },
        { key: 'norte',     width: 16 },
        { key: 'este',      width: 16 },
        { key: 'elev',      width: 12 },
        { key: 'fuso',      width: 8  },
        { key: 'epsg',      width: 10 },
      ];
    } else {
      ws.columns = [
        { key: 'id_med',    width: 36 },
        { key: 'nome',      width: 26 },
        { key: 'tipo',      width: 13 },
        { key: 'n_ponto',   width: 10 },
        { key: 'lat',       width: 16 },
        { key: 'lng',       width: 16 },
        { key: 'elev',      width: 12 },
      ];
    }

    // Cabeçalho
    const headers = isUtm
      ? ['ID Medicao', 'Nome', 'Tipo', 'N. Ponto', 'Norte (m)', 'Este (m)', 'Elevacao (m)', 'Fuso', 'EPSG']
      : ['ID Medicao', 'Nome', 'Tipo', 'N. Ponto', 'Latitude', 'Longitude', 'Elevacao (m)'];

    const headerRow = ws.addRow(headers);
    this.styleHeaderRow(headerRow, headers.length);

    // Formatos numéricos
    const fmtCoord3 = '#,##0.000';
    const fmtCoord7 = '0.0000000';

    // Dados
    let rowIdx = 0;
    for (const e of entries) {
      const tipo = TYPE_LABELS[e.type] ?? e.type;
      for (let pi = 0; pi < e.coordinates.length; pi++) {
        const [lat, lng, elev] = e.coordinates[pi];
        let dataRow: ExcelJS.Row;

        if (isUtm) {
          const { easting, northing, zone, band } = this.base.wgs84ToUtm(lat, lng);
          const isNorth = band >= 'N';
          const epsg    = isNorth ? 32600 + zone : 32700 + zone;
          dataRow = ws.addRow([
            e.id, e.name, tipo, pi + 1,
            northing, easting,
            elev != null ? elev : null,
            `${zone}${band}`,
            epsg
          ]);
          this.styleDataRow(dataRow, headers.length, rowIdx);
          dataRow.getCell(5).numFmt = fmtCoord3;  // Norte
          dataRow.getCell(6).numFmt = fmtCoord3;  // Este
        } else {
          dataRow = ws.addRow([
            e.id, e.name, tipo, pi + 1,
            lat, lng,
            elev != null ? elev : null
          ]);
          this.styleDataRow(dataRow, headers.length, rowIdx);
          dataRow.getCell(5).numFmt = fmtCoord7;  // Lat
          dataRow.getCell(6).numFmt = fmtCoord7;  // Lng
        }

        // Coluna Elevação — 3 casas, em ambos os casos
        const elevCell = dataRow.getCell(isUtm ? 7 : 7);
        if (elev != null) elevCell.numFmt = fmtCoord3;

        rowIdx++;
      }
    }
  }

  // --------------------------------------------------------------------------
  // Helpers de estilo
  // --------------------------------------------------------------------------

  /** Aplica estilo de cabeçalho (azul escuro + branco + negrito + borda) à linha. */
  private styleHeaderRow(row: ExcelJS.Row, colCount: number): void {
    row.height = 20;
    for (let c = 1; c <= colCount; c++) {
      const cell = row.getCell(c);
      cell.font      = { bold: true, color: { argb: COLOR_HEADER_FG }, size: 11 };
      cell.fill      = { type: 'pattern', pattern: 'solid', fgColor: { argb: COLOR_HEADER_BG } };
      cell.alignment = { vertical: 'middle', horizontal: 'center', wrapText: false };
      cell.border    = THIN_BORDER;
    }
  }

  /** Aplica estilo de linha de dados (alternada + borda) à linha. */
  private styleDataRow(row: ExcelJS.Row, colCount: number, rowIndex: number): void {
    const isAlt = rowIndex % 2 === 1;
    row.height  = 16;
    for (let c = 1; c <= colCount; c++) {
      const cell = row.getCell(c);
      cell.border    = THIN_BORDER;
      cell.alignment = { vertical: 'middle', wrapText: false };
      if (isAlt) {
        cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: COLOR_ALT_ROW } };
      }
    }
  }

  // --------------------------------------------------------------------------
  // Auxiliares
  // --------------------------------------------------------------------------

  /** Formata data para string legível (DD/MM/AAAA HH:MM). */
  private fmtDate(d: Date | string): string {
    const dt = d instanceof Date ? d : new Date(d);
    if (isNaN(dt.getTime())) return String(d);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${pad(dt.getDate())}/${pad(dt.getMonth() + 1)}/${dt.getFullYear()} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
  }
}
