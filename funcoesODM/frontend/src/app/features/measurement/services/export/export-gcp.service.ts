/**
 * ExportGcpService
 *
 * Gera arquivo GCP (Ground Control Points) no formato ODM/WebODM.
 *
 * Formato de saida:
 *   EPSG:4326
 *   lat lng alt pixel_x pixel_y imagem
 *
 * Regras:
 *   - Apenas medicoes do tipo 'distance' e 'height' geram linhas GCP.
 *     Aread e volumes sao ignorados (poligonos nao sao pontos de controle).
 *   - Cada coordenada da medicao vira uma linha GCP independente.
 *   - pixel_x e pixel_y ficam fixos em 0 0 — o usuario preenche manualmente apos exportar.
 *   - O nome da imagem fica como 'imagem.jpg' por padrao — sem vinculo com arquivos reais.
 *   - Elevacao: terceiro elemento do array de coordenadas, ou '0.000' quando ausente.
 *
 * Referencia: https://docs.opendronemap.org/gcp/#gcp-file-format
 *
 * Ver docs/reference/MEASUREMENT-EXPORT.md secao "GCP — Ground Control Points (ODM)".
 */

import { Injectable, inject } from '@angular/core';
import { ExportBaseService, RawMeasurementEntry } from './export-base.service';

@Injectable({ providedIn: 'root' })
export class ExportGcpService {

  private base = inject(ExportBaseService);

  // --------------------------------------------------------------------------
  // Builder
  // --------------------------------------------------------------------------

  /**
   * Gera o conteudo do arquivo GCP como string.
   * Filtra apenas medicoes do tipo 'distance' ou 'height'.
   * Cada ponto (coordenada) da medicao vira uma linha GCP.
   */
  buildGCP(entries: RawMeasurementEntry[]): string {
    const lines: string[] = ['EPSG:4326'];
    let totalPoints = 0;

    for (const entry of entries) {
      if (entry.type !== 'distance' && entry.type !== 'height') {
        continue;
      }

      for (const coord of entry.coordinates) {
        const lat = coord[0].toFixed(7);
        const lng = coord[1].toFixed(7);
        // Elevacao: terceiro elemento do array, ou 0.000 quando nao disponivel
        const alt = coord[2] != null && !isNaN(coord[2])
          ? coord[2].toFixed(3)
          : '0.000';

        // pixel_x e pixel_y: 0 0 por padrao — usuario edita manualmente para vincular imagens
        lines.push(`${lat} ${lng} ${alt} 0 0 imagem.jpg`);
        totalPoints++;
      }
    }

    if (totalPoints === 0) {
      // Arquivo vazio e invalido para o ODM — adicionar comentario explicativo
      lines.push('# Nenhum ponto GCP encontrado.');
      lines.push('# Adicione medicoes do tipo distancia ou altura para gerar GCPs.');
    }

    return lines.join('\n') + '\n';
  }

  // --------------------------------------------------------------------------
  // Exportacao
  // --------------------------------------------------------------------------

  /**
   * Gera e faz download do arquivo GCP (.txt) para uso no ODM/WebODM.
   *
   * Fluxo de uso:
   *   1. Medir pontos de referencia no viewer (tipo 'distance' ou 'height')
   *   2. Exportar GCP.txt via este metodo
   *   3. Editar pixel_x e pixel_y no arquivo (coordenadas de pixel nas imagens originais)
   *   4. Fazer upload do GCP.txt junto com as imagens no ODM
   *   5. Reprocessar — a ortofoto resultante ficara alinhada ao mapa
   *
   * @param entries Lista de medicoes a converter em GCPs.
   * @param projectId ID do projeto — usado no nome do arquivo.
   */
  exportGCP(entries: RawMeasurementEntry[], projectId: number | string = 0): void {
    const content = this.buildGCP(entries);
    this.base.downloadString(
      content,
      // GCP tem CRS fixo (EPSG:4326) — omitir coordFormat no nome do arquivo (null)
      this.base.buildFilename(projectId, 'gcp', 'txt', null),
      'text/plain;charset=utf-8;'
    );
  }
}
