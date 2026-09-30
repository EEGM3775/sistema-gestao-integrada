/**
 * ExportPdfService
 *
 * Gera um relatório PDF das medições usando jsPDF + jspdf-autotable.
 * Sem dependência de servidor — gerado inteiramente no browser.
 *
 * Estrutura do PDF:
 *  - Cabeçalho: título, nº projeto, data/hora de geração
 *  - Caixa de resumo: total de medições por tipo
 *  - Tabela 1 — Medições: nome, tipo, valor, unidade, nº pontos, fonte
 *  - Tabela 2 — Coordenadas: uma linha por ponto (WGS84 ou UTM)
 *  - Rodapé: paginação e marca FuncoesODM
 *
 * Convenções:
 *  - NUNCA emojis — texto puro ASCII/pt-BR
 *  - Máx 200 linhas, 1 responsabilidade
 */

import { Injectable, inject } from '@angular/core';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat
} from './export-base.service';

// ============================================================================
// Constantes de cores (RGB)
// ============================================================================

const BLUE_DARK  = [26, 58, 92]   as [number, number, number];  // cabeçalho / título
const BLUE_LIGHT = [232, 240, 247] as [number, number, number]; // linhas alternadas
const GREY_LIGHT = [120, 120, 120] as [number, number, number]; // rodapé
const WHITE      = [255, 255, 255] as [number, number, number];

const TYPE_LABELS: Record<string, string> = {
  distance: 'Distancia',
  area:     'Area',
  volume:   'Volume',
  height:   'Altura'
};

// ============================================================================
// Service
// ============================================================================

@Injectable({ providedIn: 'root' })
export class ExportPdfService {

  private base = inject(ExportBaseService);

  /**
   * Gera e faz download do relatório PDF.
   *
   * @param entries     Lista de medições
   * @param coordFormat 'wgs84' ou 'utm' — define o sistema de coordenadas na tabela de pontos
   * @param projectId   ID do projeto (usado no título e nome do arquivo)
   */
  exportPdf(
    entries:     RawMeasurementEntry[],
    coordFormat: CoordFormat,
    projectId:   number | string
  ): void {
    // A4 retrato, unidade mm
    const doc   = new jsPDF('p', 'mm', 'a4');
    const pageW = doc.internal.pageSize.getWidth();

    this.renderHeader(doc, pageW, projectId);
    this.renderSummary(doc, entries);
    this.renderMeasurementsTable(doc, entries);
    this.renderCoordinatesTable(doc, entries, coordFormat);
    this.renderPageFooters(doc, pageW);

    doc.save(this.base.buildFilename(projectId, 'relatorio', 'pdf', coordFormat));
  }

  // --------------------------------------------------------------------------
  // Seções privadas
  // --------------------------------------------------------------------------

  /** Faixa azul no topo com título e metadados do projeto. */
  private renderHeader(doc: jsPDF, pageW: number, projectId: number | string): void {
    const now = new Date();

    doc.setFillColor(...BLUE_DARK);
    doc.rect(0, 0, pageW, 24, 'F');

    doc.setTextColor(...WHITE);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(13);
    doc.text('FuncoesODM - Relatorio de Medicoes', 14, 10);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.text(
      `Projeto #${projectId}   Gerado em ${now.toLocaleDateString('pt-BR')} as ${now.toLocaleTimeString('pt-BR')}`,
      14, 18
    );
  }

  /** Linha de resumo: total + contagem por tipo. */
  private renderSummary(doc: jsPDF, entries: RawMeasurementEntry[]): void {
    const counts: Record<string, number> = { distance: 0, area: 0, volume: 0, height: 0 };
    for (const e of entries) if (e.type in counts) counts[e.type]++;

    const partes = Object.entries(TYPE_LABELS)
      .filter(([t]) => counts[t] > 0)
      .map(([t, label]) => `${counts[t]} ${label.toLowerCase()}${counts[t] > 1 ? 's' : ''}`);

    doc.setTextColor(50, 50, 50);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.text(`Total: ${entries.length} medicao${entries.length !== 1 ? 'oes' : ''}`, 14, 32);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(80, 80, 80);
    doc.text(partes.join('  |  '), 14, 37);
  }

  /** Tabela principal: uma linha por medição. */
  private renderMeasurementsTable(doc: jsPDF, entries: RawMeasurementEntry[]): void {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(...BLUE_DARK);
    doc.text('Medicoes', 14, 45);

    autoTable(doc, {
      startY: 48,
      head: [['Nome', 'Tipo', 'Valor', 'Unidade', 'Pontos', 'Fonte']],
      body: entries.map(e => [
        e.name,
        TYPE_LABELS[e.type] ?? e.type,
        e.value.toLocaleString('pt-BR', { minimumFractionDigits: 3, maximumFractionDigits: 4 }),
        e.unit,
        String(e.coordinates.length),
        e.dataSource ?? '—'
      ]),
      headStyles:          { fillColor: BLUE_DARK, textColor: WHITE, fontStyle: 'bold', fontSize: 8 },
      alternateRowStyles:  { fillColor: BLUE_LIGHT },
      styles:              { fontSize: 8, cellPadding: 2 },
      columnStyles: {
        0: { cellWidth: 50 },
        1: { cellWidth: 22 },
        2: { cellWidth: 22, halign: 'right' },
        3: { cellWidth: 16 },
        4: { cellWidth: 16, halign: 'center' },
        5: { cellWidth: 30 }
      },
      margin: { left: 14, right: 14 }
    });
  }

  /** Tabela de coordenadas: uma linha por ponto de cada medição. */
  private renderCoordinatesTable(
    doc:         jsPDF,
    entries:     RawMeasurementEntry[],
    coordFormat: CoordFormat
  ): void {
    const isUtm = coordFormat === 'utm';

    // Monta linhas
    const rows: string[][] = [];
    for (const e of entries) {
      for (let i = 0; i < e.coordinates.length; i++) {
        const [lat, lng, elev] = e.coordinates[i];
        const elevStr = elev != null ? elev.toFixed(3) : '—';

        if (isUtm) {
          const { easting, northing, zone, band } = this.base.wgs84ToUtm(lat, lng);
          rows.push([
            e.name,
            TYPE_LABELS[e.type] ?? e.type,
            String(i + 1),
            northing.toFixed(3),
            easting.toFixed(3),
            `${zone}${band}`,
            elevStr
          ]);
        } else {
          rows.push([
            e.name,
            TYPE_LABELS[e.type] ?? e.type,
            String(i + 1),
            lat.toFixed(7),
            lng.toFixed(7),
            '—',
            elevStr
          ]);
        }
      }
    }

    // Posição após a tabela anterior (jspdf-autotable expõe lastAutoTable)
    const prevFinalY = (doc as any).lastAutoTable?.finalY as number | undefined;
    const startY     = prevFinalY != null ? prevFinalY + 10 : 100;

    // Nova página se não houver espaço
    const pageH = doc.internal.pageSize.getHeight();
    if (startY > pageH - 40) doc.addPage();

    const tableY = startY > pageH - 40 ? 14 : startY;

    const crsLabel = isUtm ? 'UTM WGS84' : 'WGS84 - Lat/Lng decimal';
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(...BLUE_DARK);
    doc.text(`Coordenadas (${crsLabel})`, 14, tableY - 2);

    const head = isUtm
      ? [['Medicao', 'Tipo', 'Pt', 'Norte (m)', 'Este (m)', 'Fuso', 'Elev (m)']]
      : [['Medicao', 'Tipo', 'Pt', 'Lat (grau)', 'Lng (grau)', '—', 'Elev (m)']];

    autoTable(doc, {
      startY: tableY,
      head,
      body: rows,
      headStyles:          { fillColor: BLUE_DARK, textColor: WHITE, fontStyle: 'bold', fontSize: 7 },
      alternateRowStyles:  { fillColor: BLUE_LIGHT },
      styles:              { fontSize: 7, cellPadding: 1.5 },
      columnStyles: {
        0: { cellWidth: 42 },
        1: { cellWidth: 20 },
        2: { cellWidth: 8,  halign: 'center' },
        3: { cellWidth: 30, halign: 'right' },
        4: { cellWidth: 30, halign: 'right' },
        5: { cellWidth: 14, halign: 'center' },
        6: { cellWidth: 22, halign: 'right' }
      },
      margin: { left: 14, right: 14 }
    });
  }

  /** Rodapé "Pág N de T · FuncoesODM" em todas as páginas. */
  private renderPageFooters(doc: jsPDF, pageW: number): void {
    const totalPages = doc.getNumberOfPages();
    const pageH      = doc.internal.pageSize.getHeight();

    for (let p = 1; p <= totalPages; p++) {
      doc.setPage(p);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(7);
      doc.setTextColor(...GREY_LIGHT);
      doc.text('FuncoesODM', 14, pageH - 5);
      doc.text(`Pagina ${p} de ${totalPages}`, pageW - 14, pageH - 5, { align: 'right' });
    }
  }
}
