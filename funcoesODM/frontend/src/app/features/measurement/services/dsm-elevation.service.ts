/**
 * DsmElevationService
 *
 * Carrega o DSM (GeoTIFF) e consulta o valor de elevacao em coordenadas
 * WGS84 (lat/lng). Suporta rasters em EPSG:4326 e zonas UTM (EPSG:326xx
 * / EPSG:327xx) sem dependencias externas de proj4.
 *
 * Cache em memoria: o arquivo e baixado apenas uma vez por URL de sessao.
 */

import { Injectable } from '@angular/core';
import parseGeoraster, { GeoRaster } from 'georaster';

export interface ElevationResult {
  elevation: number;   // metros
  valid: boolean;      // false se fora dos limites ou sem dado
}

export interface VolumeResult {
  volume: number;          // m³
  baseElevation: number;   // elevacao do ponto mais baixo (base do calculo)
  pixelCount: number;      // pixels amostrados dentro do poligono
  valid: boolean;
}

@Injectable()
export class DsmElevationService {

  /** Cache URL → raster ja carregado */
  private cache = new Map<string, GeoRaster>();

  /** Cache de promises em andamento (evita downloads duplos) */
  private loading = new Map<string, Promise<GeoRaster>>();

  // =========================================================================
  // API publica
  // =========================================================================

  /**
   * Pre-carrega o DSM (opcional, para adiantar o download).
   */
  async preload(url: string): Promise<void> {
    await this.getRaster(url);
  }

  /**
   * Retorna a elevacao no ponto (lat, lng) consultando o DSM.
   * @returns ElevationResult com valid=false se o ponto estiver
   *          fora dos limites do raster ou no noData.
   */
  async getElevationAt(url: string, lat: number, lng: number): Promise<ElevationResult> {
    const invalid: ElevationResult = { elevation: 0, valid: false };

    try {
      const raster = await this.getRaster(url);

      // Converter lat/lng para coordenadas nativas do raster
      const native = this.toNativeCrs(lat, lng, raster.projection);
      if (!native) return invalid;

      const [x, y] = native;

      // Verificar se esta dentro dos limites
      if (x < raster.xmin || x > raster.xmax || y < raster.ymin || y > raster.ymax) {
        return invalid;
      }

      // Calcular indice de pixel
      const col = Math.floor((x - raster.xmin) / raster.pixelWidth);
      const row = Math.floor((raster.ymax - y) / raster.pixelHeight);

      // Garantir dentro dos bounds do array
      if (row < 0 || row >= raster.height || col < 0 || col >= raster.width) {
        return invalid;
      }

      const value = raster.values[0][row][col];

      // Verificar noData
      if (raster.noDataValue !== null && value === raster.noDataValue) {
        return invalid;
      }

      // Verificar valor invalido (NaN, infinito)
      if (!isFinite(value)) return invalid;

      return { elevation: value, valid: true };

    } catch (err) {
      console.warn('[DsmElevationService] Erro ao consultar elevacao:', err);
      return invalid;
    }
  }

  /** Libera o cache (chamar quando a task mudar) */
  clearCache(): void {
    this.cache.clear();
    this.loading.clear();
  }

  /**
   * Amostra o perfil de elevacao ao longo de uma polilinha definida por waypoints.
   *
   * Algoritmo:
   *  1. Calcula o comprimento total da polilinha somando segmentos Haversine.
   *  2. Interpola `numSamples` pontos a distancias iguais ao longo da linha.
   *  3. Para cada ponto interpolado, consulta a elevacao no DSM.
   *  4. Retorna array ordenado de {lat, lng, elevation, distanceFromStart, valid}.
   *
   * @param url         URL do DSM (GeoTIFF)
   * @param waypoints   Vertices da polilinha desenhada pelo usuario
   * @param numSamples  Numero de amostras a gerar (default: 100)
   */
  async sampleElevationProfile(
    url: string,
    waypoints: { lat: number; lng: number }[],
    numSamples = 100
  ): Promise<{ lat: number; lng: number; elevation: number; distanceFromStart: number; valid: boolean }[]> {

    if (waypoints.length < 2) return [];

    // --- Comprimentos acumulados dos segmentos da polilinha ---
    const segCumDist: number[] = [0];
    for (let i = 1; i < waypoints.length; i++) {
      const d = haversineMeters(waypoints[i - 1].lat, waypoints[i - 1].lng,
                                waypoints[i].lat,     waypoints[i].lng);
      segCumDist.push(segCumDist[i - 1] + d);
    }
    const totalLength = segCumDist[segCumDist.length - 1];
    if (totalLength === 0) return [];

    // --- Gerar pontos de amostragem interpolados ---
    const samplePts: { lat: number; lng: number; dist: number }[] = [];
    const step = totalLength / (numSamples - 1);

    for (let i = 0; i < numSamples; i++) {
      const targetDist = Math.min(i * step, totalLength);

      // Encontrar segmento que contem targetDist
      let segIdx = 0;
      for (let s = 1; s < segCumDist.length; s++) {
        if (segCumDist[s] >= targetDist) {
          segIdx = s - 1;
          break;
        }
        segIdx = s - 1; // ultimo segmento para targetDist == totalLength
      }

      const segStart = segCumDist[segIdx];
      const segEnd   = segCumDist[segIdx + 1] ?? segCumDist[segIdx];
      const segLen   = segEnd - segStart;

      let lat: number, lng: number;
      if (segLen === 0) {
        lat = waypoints[segIdx].lat;
        lng = waypoints[segIdx].lng;
      } else {
        const t = (targetDist - segStart) / segLen;
        const wA = waypoints[segIdx];
        const wB = waypoints[segIdx + 1] ?? wA;
        lat = wA.lat + t * (wB.lat - wA.lat);
        lng = wA.lng + t * (wB.lng - wA.lng);
      }

      samplePts.push({ lat, lng, dist: targetDist });
    }

    // --- Consultar DSM em paralelo para todos os pontos ---
    const results = await Promise.all(
      samplePts.map(async pt => {
        const elev = await this.getElevationAt(url, pt.lat, pt.lng);
        return {
          lat: pt.lat,
          lng: pt.lng,
          elevation: elev.valid ? elev.elevation : 0,
          distanceFromStart: pt.dist,
          valid: elev.valid
        };
      })
    );

    return results;
  }

  /**
   * Calcula o volume acima do ponto mais baixo dentro de um polígono.
   *
   * Fluxo:
   *   1. Converte vertices do polígono para CRS nativo do raster
   *   2. Itera todos os pixels no bounding box do polígono
   *   3. Testa ponto-no-polígono (ray casting) para cada pixel
   *   4. Acha elevação mínima (base = ponto mais baixo)
   *   5. Soma (elevation - base) * pixelAreaM2 para cada pixel válido
   */
  async calculateVolume(
    url: string,
    polygon: { lat: number; lng: number }[]
  ): Promise<VolumeResult> {
    const invalid: VolumeResult = { volume: 0, baseElevation: 0, pixelCount: 0, valid: false };

    try {
      const raster = await this.getRaster(url);

      // Converter vertices para CRS nativo
      const nativeVerts: [number, number][] = [];
      for (const pt of polygon) {
        const native = this.toNativeCrs(pt.lat, pt.lng, raster.projection);
        if (!native) return invalid;
        nativeVerts.push(native);
      }

      // Bounding box em índices de pixel
      const xs = nativeVerts.map(v => v[0]);
      const ys = nativeVerts.map(v => v[1]);
      const xmin = Math.min(...xs);
      const xmax = Math.max(...xs);
      const ymin = Math.min(...ys);
      const ymax = Math.max(...ys);

      const colMin = Math.max(0, Math.floor((xmin - raster.xmin) / raster.pixelWidth));
      const colMax = Math.min(raster.width - 1, Math.ceil((xmax - raster.xmin) / raster.pixelWidth));
      const rowMin = Math.max(0, Math.floor((raster.ymax - ymax) / raster.pixelHeight));
      const rowMax = Math.min(raster.height - 1, Math.ceil((raster.ymax - ymin) / raster.pixelHeight));

      // Área de cada pixel em m²
      const pixelAreaM2 = this.pixelAreaInMeters(raster);

      // Primeira passagem: coletar elevações válidas dentro do polígono
      const elevations: number[] = [];

      for (let row = rowMin; row <= rowMax; row++) {
        for (let col = colMin; col <= colMax; col++) {
          // Centro do pixel em CRS nativo
          const cx = raster.xmin + (col + 0.5) * raster.pixelWidth;
          const cy = raster.ymax - (row + 0.5) * raster.pixelHeight;

          if (!pointInPolygon(cx, cy, nativeVerts)) continue;

          const value = raster.values[0][row][col];
          if (raster.noDataValue !== null && value === raster.noDataValue) continue;
          if (!isFinite(value)) continue;

          elevations.push(value);
        }
      }

      if (elevations.length === 0) return invalid;

      // Ponto mais baixo = base do cálculo
      // Uso de loop em vez de Math.min(...elevations) para evitar stack overflow
      // em polígonos grandes com muitos pixels (spread de arrays > ~100k estoura a pilha)
      let baseElevation = elevations[0];
      for (let i = 1; i < elevations.length; i++) {
        if (elevations[i] < baseElevation) baseElevation = elevations[i];
      }

      // Volume = soma de (elev - base) * pixelArea
      let volume = 0;
      for (let i = 0; i < elevations.length; i++) {
        volume += (elevations[i] - baseElevation) * pixelAreaM2;
      }

      return { volume, baseElevation, pixelCount: elevations.length, valid: true };

    } catch (err) {
      console.warn('[DsmElevationService] Erro ao calcular volume:', err);
      return invalid;
    }
  }

  // =========================================================================
  // Internos
  // =========================================================================

  private async getRaster(url: string): Promise<GeoRaster> {
    if (this.cache.has(url)) {
      return this.cache.get(url)!;
    }

    if (this.loading.has(url)) {
      return this.loading.get(url)!;
    }

    const promise = fetch(url)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status} ao carregar DSM`);
        return res.arrayBuffer();
      })
      .then(buf => parseGeoraster(buf))
      .then(raster => {
        this.cache.set(url, raster);
        this.loading.delete(url);
        return raster;
      })
      .catch(err => {
        this.loading.delete(url);
        throw err;
      });

    this.loading.set(url, promise);
    return promise;
  }

  /**
   * Converte WGS84 (lat, lng) para as coordenadas nativas do raster.
   * Suporta EPSG:4326 e UTM (EPSG:326xx / EPSG:327xx).
   * Retorna null se a projecao nao for reconhecida.
   */
  private toNativeCrs(lat: number, lng: number, epsg: number): [number, number] | null {
    // WGS84 → sem conversao
    if (epsg === 4326) {
      return [lng, lat];
    }

    // UTM Norte: EPSG 32601–32660 (zona = epsg - 32600)
    if (epsg >= 32601 && epsg <= 32660) {
      return wgs84ToUTM(lat, lng, epsg - 32600, true);
    }

    // UTM Sul: EPSG 32701–32760 (zona = epsg - 32700)
    if (epsg >= 32701 && epsg <= 32760) {
      return wgs84ToUTM(lat, lng, epsg - 32700, false);
    }

    console.warn(`[DsmElevationService] Projecao EPSG:${epsg} nao suportada`);
    return null;
  }

  /**
   * Retorna a área de um pixel em metros quadrados.
   * Para rasters UTM (metros), é simplesmente pixelWidth * pixelHeight.
   * Para EPSG:4326 (graus), converte usando a latitude média do raster.
   */
  private pixelAreaInMeters(raster: GeoRaster): number {
    const pw = raster.pixelWidth;
    const ph = raster.pixelHeight;
    const epsg = raster.projection;

    if (epsg === 4326) {
      const latMid = (raster.ymin + raster.ymax) / 2;
      const mPerDegLat = 110540;
      const mPerDegLng = 111320 * Math.cos(latMid * Math.PI / 180);
      return pw * mPerDegLng * ph * mPerDegLat;
    }

    // UTM e outros projetados: unidades já em metros
    return Math.abs(pw * ph);
  }
}

// ============================================================================
// Distancia Haversine (km-level precision, suficiente para amostragem de perfis)
// ============================================================================

function haversineMeters(la1: number, lo1: number, la2: number, lo2: number): number {
  const R = 6_371_000;
  const dLat = (la2 - la1) * Math.PI / 180;
  const dLon = (lo2 - lo1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(la1 * Math.PI / 180) * Math.cos(la2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ============================================================================
// Teste ponto-no-polígono (ray casting)
// ============================================================================

function pointInPolygon(x: number, y: number, polygon: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    const intersect = ((yi > y) !== (yj > y))
      && (x < ((xj - xi) * (y - yi) / (yj - yi) + xi));
    if (intersect) inside = !inside;
  }
  return inside;
}

// ============================================================================
// Conversao WGS84 → UTM (implementacao pura, sem deps externas)
// Baseada no algoritmo de Karney simplificado (suficiente para DSMs de engenharia)
// ============================================================================

function wgs84ToUTM(
  lat: number, lng: number,
  zone: number, isNorth: boolean
): [number, number] {

  const k0 = 0.9996;
  const a  = 6378137.0;            // semi-eixo maior WGS84
  const f  = 1 / 298.257223563;    // achatamento WGS84
  const e2 = 2 * f - f * f;        // excentricidade^2
  const e4 = e2 * e2;
  const e6 = e4 * e2;

  const phi = lat * Math.PI / 180;
  const lam = lng * Math.PI / 180;
  const lam0 = ((zone - 1) * 6 - 180 + 3) * Math.PI / 180; // meridiano central

  const N1 = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
  const T  = Math.tan(phi) ** 2;
  const C  = (e2 / (1 - e2)) * Math.cos(phi) ** 2;
  const A  = Math.cos(phi) * (lam - lam0);

  // Arco de meridiano
  const M = a * (
    (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256)   * phi
    - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * Math.sin(2 * phi)
    + (15 * e4 / 256 + 45 * e6 / 1024)             * Math.sin(4 * phi)
    - (35 * e6 / 3072)                              * Math.sin(6 * phi)
  );

  const easting = k0 * N1 * (
    A
    + (1 - T + C)                                              * A ** 3 / 6
    + (5 - 18 * T + T ** 2 + 72 * C - 58 * e2 / (1 - e2))   * A ** 5 / 120
  ) + 500_000;

  const northingBase = k0 * (
    M + N1 * Math.tan(phi) * (
      A ** 2 / 2
      + (5 - T + 9 * C + 4 * C ** 2)                                    * A ** 4 / 24
      + (61 - 58 * T + T ** 2 + 600 * C - 330 * e2 / (1 - e2))        * A ** 6 / 720
    )
  );

  const northing = northingBase + (isNorth ? 0 : 10_000_000);

  return [easting, northing];
}
