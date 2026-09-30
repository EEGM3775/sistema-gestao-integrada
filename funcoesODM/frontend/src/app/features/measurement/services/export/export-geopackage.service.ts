/**
 * ExportGeoPackageService
 *
 * Gera GeoPackage (.gpkg) via chamada HTTP ao backend Java.
 * O servidor gera o arquivo SQLite/GPB completo  sem WASM no browser.
 *
 * Endpoint: GET /api/v1/projects/{projectId}/measurements/export/gpkg
 *   ?coordFormat=wgs84|utm
 *   &epsg=32724  (opcional  EPSG UTM de saída)
 */

import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat
} from './export-base.service';

@Injectable({ providedIn: 'root' })
export class ExportGeoPackageService {

  private base = inject(ExportBaseService);
  private http = inject(HttpClient);

  /**
   * Solicita ao backend Java a geração do GeoPackage e faz o download.
   *
   * @param entries     Medições (usadas apenas para detectar EPSG quando targetEpsg=null e coordFormat=utm)
   * @param coordFormat 'wgs84' ou 'utm'
   * @param projectId   ID do projeto
   * @param targetEpsg  EPSG do fuso UTM escolhido pelo usuário no popup. null = servidor auto-detecta.
   */
  async exportGeoPackage(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat,
    projectId: number | string,
    targetEpsg: number | null = null
  ): Promise<void> {
    const params: Record<string, string> = { coordFormat };

    if (coordFormat === 'utm') {
      // Se o usuário escolheu explicitamente um fuso, passa para o servidor.
      // Se não (targetEpsg=null), o servidor detecta automaticamente pelo DB.
      const epsg = targetEpsg ?? this.detectEpsgFromEntries(entries);
      if (epsg !== null) {
        params['epsg'] = String(epsg);
      }
    }

    const blob = await firstValueFrom(
      this.http.get(`/api/v1/projects/${projectId}/measurements/export/gpkg`, {
        responseType: 'blob',
        params
      })
    );

    const filename = this.base.buildFilename(projectId, 'geopackage', 'gpkg', coordFormat);
    this.base.downloadBlob(blob, filename);
  }

  /**
   * Detecta o EPSG UTM dominante pelas entradas do cliente (fallback local).
   * Usado apenas quando o usuário ainda não selecionou um fuso explicitamente.
   */
  private detectEpsgFromEntries(entries: RawMeasurementEntry[]): number | null {
    const first = entries[0]?.coordinates[0];
    if (!first) return null;
    const { zone, band } = this.base.wgs84ToUtm(first[0], first[1]);
    return band >= 'N' ? 32600 + zone : 32700 + zone;
  }
}