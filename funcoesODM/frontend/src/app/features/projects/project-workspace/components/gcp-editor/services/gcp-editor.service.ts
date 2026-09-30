/**
 * GcpEditorService
 *
 * Responsabilidades:
 *  - Parsear arquivo GCP parcial (com pixel_x/pixel_y = 0 0) gerado pelo ExportGcpService.
 *  - Combinar GcpPoint[] + GcpMark[] para gerar o gcp_list.txt completo.
 *  - Converter o resultado em File para upload direto ao NodeODM.
 *
 * Formato ODM esperado:
 *   EPSG:4326
 *   lat lng alt pixel_x pixel_y nome_imagem.jpg
 *
 * Referencia: https://docs.opendronemap.org/gcp/#gcp-file-format
 */

import { Injectable } from '@angular/core';
import { GcpMark, GcpPoint } from '../models/gcp-mark.model';

@Injectable({ providedIn: 'root' })
export class GcpEditorService {

  // --------------------------------------------------------------------------
  // Parse
  // --------------------------------------------------------------------------

  /**
   * Interpreta o conteudo de um arquivo GCP parcial (gerado pelo ExportGcpService
   * ou preenchido manualmente) e extrai os GcpPoints.
   *
   * Aceita linhas no formato:
   *   lat lng alt [px py] [nome]
   *   EPSG:XXXX   (cabecalho ignorado)
   *   # comentarios (ignorados)
   */
  parsePartialGcp(content: string): GcpPoint[] {
    const points: GcpPoint[] = [];
    let seq = 1;

    for (const raw of content.split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('#') || line.toUpperCase().startsWith('EPSG')) continue;

      const parts = line.split(/\s+/);
      if (parts.length < 2) continue;

      const lat = parseFloat(parts[0]);
      const lng = parseFloat(parts[1]);
      const alt = parts.length >= 3 ? parseFloat(parts[2]) || 0 : 0;

      if (isNaN(lat) || isNaN(lng)) continue;

      points.push({
        id: `gcp-${seq}`,
        label: `GCP-${String(seq).padStart(2, '0')}`,
        lat,
        lng,
        alt,
      });
      seq++;
    }

    return points;
  }

  // --------------------------------------------------------------------------
  // Build
  // --------------------------------------------------------------------------

  /**
   * Gera o conteudo final do gcp_list.txt com pixel_x e pixel_y reais.
   * Apenas marcacoes com pelo menos 1 foto sao incluidas.
   */
  buildGcpListTxt(gcpPoints: GcpPoint[], marks: GcpMark[]): string {
    const lines: string[] = ['EPSG:4326'];

    for (const mark of marks) {
      const gcp = gcpPoints.find(g => g.id === mark.gcpId);
      if (!gcp) continue;

      lines.push(
        `${gcp.lat.toFixed(7)} ${gcp.lng.toFixed(7)} ${gcp.alt.toFixed(3)}` +
        ` ${mark.pixelX} ${mark.pixelY} ${mark.imageOriginalFilename}`
      );
    }

    return lines.join('\n') + '\n';
  }

  /**
   * Converte os dados do editor em um File pronto para upload.
   * Requer pelo menos 3 marcacoes em imagens distintas para ser valido.
   */
  toFile(gcpPoints: GcpPoint[], marks: GcpMark[]): File {
    const content = this.buildGcpListTxt(gcpPoints, marks);
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    return new File([blob], 'gcp_list.txt', { type: 'text/plain' });
  }

  /**
   * Valida se ha marcacoes suficientes para gerar um GCP valido.
   * NodeODM exige ao menos 3 GCPs distintos, cada um em pelo menos 2 fotos.
   */
  isValid(gcpPoints: GcpPoint[], marks: GcpMark[]): { valid: boolean; reason: string } {
    const gcpsComMarca = new Set(marks.map(m => m.gcpId));
    if (gcpsComMarca.size < 3) {
      return {
        valid: false,
        reason: `Minimo de 3 GCPs marcados. Atual: ${gcpsComMarca.size}.`,
      };
    }

    for (const gcpId of gcpsComMarca) {
      const fotos = new Set(marks.filter(m => m.gcpId === gcpId).map(m => m.imageId));
      if (fotos.size < 2) {
        const gcp = gcpPoints.find(g => g.id === gcpId);
        return {
          valid: false,
          reason: `GCP "${gcp?.label}" marcado em apenas ${fotos.size} foto. Minimo: 2.`,
        };
      }
    }

    return { valid: true, reason: '' };
  }
}
