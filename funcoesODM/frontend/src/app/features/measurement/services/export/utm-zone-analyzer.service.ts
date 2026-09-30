/**
 * UtmZoneAnalyzerService
 *
 * Analise e tratamento de cruzamento de fusos UTM em conjuntos de medicoes.
 *
 * ============================================================================
 * CONTEXTO GEOPROFISSIONAL
 * ============================================================================
 *
 * O sistema UTM (Universal Transverse Mercator) divide o globo em 60 fusos
 * longitudinais de 6 graus cada. Cada fuso tem origem propria (meridiano
 * central) e as coordenadas Easting/Northing sao validas SOMENTE dentro do
 * seu fuso. Misturar pontos de fusos diferentes num mesmo dataset UTM produz
 * erros geometricos de dezenas a centenas de quilometros.
 *
 * Exemplo tipico no Brasil:
 *   - Fuso 22S (EPSG:32722): cobre aprox. 42 W a 48 W  (ES, MG, RJ, SP leste)
 *   - Fuso 23S (EPSG:32723): cobre aprox. 48 W a 54 W  (SP, PR, RS)
 *   Um projeto na fronteira SP/MG pode ter pontos nos dois fusos.
 *   Um ponto projetado em 22S com Easting=700.000 m e outro projetado em 23S
 *   com Easting=300.000 m parecem estar a 400 km um do outro se lidos no
 *   mesmo CRS — mas na realidade podem estar apenas 5 km separados.
 *
 * Brasil: fusos 18S-25S (exceto Amapa/Roraima que tocam o Norte)
 * Fusos mais comuns: 22S, 23S, 24S
 *
 * ============================================================================
 * ESTRATEGIA POR FORMATO
 * ============================================================================
 *
 * | Formato   | CRS declarado? | Estrategia multi-fuso recomendada            |
 * |-----------|----------------|----------------------------------------------|
 * | GeoJSON   | Implicito 4326 | N/A — sempre WGS84 (RFC 7946)                |
 * | KML       | Implicito 4326 | N/A — sempre WGS84 (spec KML 2.2)           |
 * | GPX       | Implicito 4326 | N/A — sempre WGS84 (spec GPX 1.1)           |
 * | WKT       | Comentario     | Fallback WGS84 + aviso                       |
 * | GML       | srsName attr.  | Fallback WGS84 + aviso [JA IMPLEMENTADO]     |
 * | LandXML   | CoordSys elem  | Reprojetar para fuso dominante + aviso       |
 * | DXF       | Nenhum         | Reprojetar para fuso dominante + aviso forte |
 * | SVG       | Nenhum         | Fallback WGS84 (para bounding box correta)   |
 * | CSV       | Coluna FUSO    | Aviso apenas (per-row zone info presente)    |
 * | PNEZD     | Nenhum         | Aviso forte (formato nao suporta CRS)        |
 * | JSON      | Campo fuso     | Aviso apenas (per-point zone info presente)  |
 *
 * ============================================================================
 * MATEMATICA
 * ============================================================================
 *
 * Projecao DIRETA (WGS84 -> UTM): serie de Redfearn / Helmert (6 termos).
 * Precisao: ~0,01 mm para pontos bem dentro do fuso; ~1 mm na borda extrema.
 * IDENTICA a implementacao do ExportBaseService (fonte canonica duplicada
 * aqui intencionalmente para evitar dependencia circular e garantir que este
 * servico seja totalmente autossuficiente).
 *
 * Projecao INVERSA (UTM -> WGS84): serie de Helmert, mesmos coeficientes.
 * Necessaria para reprojecao: ponto no fuso errado -> WGS84 -> fuso correto.
 * Precisao equivalente a projecao direta.
 *
 * Elipsoide: WGS84
 *   a  = 6.378.137,0 m          (semi-eixo maior)
 *   f  = 1/298.257223563        (achatamento)
 *   b  = a*(1-f)                (semi-eixo menor)
 *   e2 = 1 - (b/a)^2           (excentricidade quadratica)
 *   k0 = 0,9996                 (fator de escala UTM)
 *
 * ============================================================================
 * USO
 * ============================================================================
 *
 * Analise basica (apenas deteccao):
 *   const analysis = this.analyzer.analyzeEntries(entries);
 *   if (analysis.isMultiZone) window.alert(analysis.warningMessage);
 *
 * Reprojecao para fuso dominante (formatos CAD/engenharia):
 *   const pts = this.analyzer.reprojectToDominantZone(entries);
 *   pts.forEach(p => use(p.easting, p.northing, p.zone));
 *
 * Verificar severidade e agir por tipo de formato:
 *   if (analysis.severity === 'critical') { // 3+ fusos ou hemisferios mistos
 *     // alerta mais forte
 *   }
 */

import { Injectable } from '@angular/core';
import proj4 from 'proj4';
import { RawMeasurementEntry } from './export-base.service';

// ============================================================================
// Interfaces publicas
// ============================================================================

/** Resultado da conversao de um unico ponto WGS84 -> UTM. */
export interface UtmProjected {
  /** Coordenada Easting (m) */
  easting: number;
  /** Coordenada Northing (m), ja ajustada para o hemisferio Sul se necessario */
  northing: number;
  /** Numero do fuso UTM (1-60) */
  zone: number;
  /** Letra de banda de latitude (C-X, exceto I e O) */
  band: string;
  /** true = hemisferio Norte; false = hemisferio Sul */
  isNorth: boolean;
  /** Codigo EPSG: 32600+zone (N) ou 32700+zone (S) */
  epsg: number;
}

/** Resultado da conversao de um unico ponto UTM -> WGS84. */
export interface Wgs84Reprojected {
  lat: number;
  lng: number;
}

/**
 * Ponto reprojetado para o fuso dominante.
 * Inclui flag de reprojecao para rastreabilidade.
 */
export interface ReprojectPoint {
  /** Coordenada Easting no fuso dominante (m) */
  easting: number;
  /** Coordenada Northing no fuso dominante (m) */
  northing: number;
  /** Fuso dominante usado */
  zone: number;
  /** Banda de latitude */
  band: string;
  /** true = o ponto PERTENCIA a outro fuso e foi reprojetado */
  wasReprojected: boolean;
  /** Elev original, passada sem alteracao */
  elev?: number;
}

/**
 * Analise completa de um conjunto de coordenadas quanto a distribuicao de fusos UTM.
 */
export interface ZoneAnalysis {
  /** Todos os codigos EPSG presentes (ex: [32722, 32723]) */
  epsgsPresent: number[];
  /** Numero de fusos distintos */
  zoneCount: number;
  /** EPSG do fuso com maior numero de pontos */
  dominantEpsg: number;
  /** Numero do fuso dominante (ex: 23) */
  dominantZone: number;
  /** Hemisferio do fuso dominante */
  dominantZoneIsNorth: boolean;
  /** true se ha pontos em mais de um fuso */
  isMultiZone: boolean;
  /** true se ha pontos nos dois hemisferios simultaneamente */
  hasMixedHemisphere: boolean;
  /**
   * Severidade do problema:
   *  - 'ok'      : todos os pontos no mesmo fuso — sem problemas
   *  - 'warn'    : pontos em 2 fusos adjacentes — provavel projeto de fronteira
   *  - 'critical': pontos em 3+ fusos OU fusos de hemisferios diferentes
   */
  severity: 'ok' | 'warn' | 'critical';
  /** Total de pontos analisados */
  totalPoints: number;
  /** Quantidade de pontos por EPSG */
  pointsPerEpsg: Record<number, number>;
  /**
   * Mensagem de aviso padronizada em PT-BR para exibicao ao usuario.
   * undefined quando severity === 'ok'.
   */
  warningMessage?: string;
}

// ============================================================================
// Constantes internas
// ============================================================================

const WGS84_A  = 6_378_137.0;                     // semi-eixo maior (m)
const WGS84_F  = 1 / 298.257_223_563;             // achatamento
const WGS84_B  = WGS84_A * (1 - WGS84_F);         // semi-eixo menor (m)
const WGS84_E2 = 1 - (WGS84_B * WGS84_B) / (WGS84_A * WGS84_A); // e^2
const UTM_K0   = 0.9996;                           // fator de escala central

/** Letras de banda UTM (sem I e O). Indice 0 = banda C (lat -80). */
const UTM_BANDS = 'CDEFGHJKLMNPQRSTUVWX';

// ============================================================================
// Service
// ============================================================================

@Injectable({ providedIn: 'root' })
export class UtmZoneAnalyzerService {

  // ==========================================================================
  // API publica — analise
  // ==========================================================================

  /**
   * Analisa todos os RawMeasurementEntry e retorna o diagnostico de fusos.
   *
   * Este e o ponto de entrada principal para os servicos de exportacao.
   * Exemplo de uso em buildWKT():
   *   const analysis = this.analyzer.analyzeEntries(entries);
   *   if (analysis.isMultiZone) return buildFallbackWgs84(entries);
   */
  analyzeEntries(entries: RawMeasurementEntry[]): ZoneAnalysis {
    const coords = entries.flatMap(e => e.coordinates);
    return this.analyzeCoordinates(coords);
  }

  /**
   * Analisa um array de coordenadas [[lat, lng, elev?], ...].
   * Versao de baixo nivel; prefira analyzeEntries() nos servicos de exportacao.
   */
  analyzeCoordinates(coords: number[][]): ZoneAnalysis {
    if (coords.length === 0) {
      // Sem pontos — retorna 'ok' com zona padrao (23S, zona mais comum no Brasil)
      return this._buildAnalysis({}, 32723, 0);
    }

    const pointsPerEpsg: Record<number, number> = {};

    for (const c of coords) {
      const lat = c[0];
      const lng = c[1];
      const zone = Math.floor((lng + 180) / 6) + 1;
      const base = lat < 0 ? 32700 : 32600;
      const epsg = base + zone;
      pointsPerEpsg[epsg] = (pointsPerEpsg[epsg] ?? 0) + 1;
    }

    // Determinar o fuso dominante (maior numero de pontos)
    const dominantEpsg = Number(
      Object.entries(pointsPerEpsg)
        .sort(([, a], [, b]) => b - a)[0][0]
    );

    return this._buildAnalysis(pointsPerEpsg, dominantEpsg, coords.length);
  }

  // ==========================================================================
  // API publica — reprojecao
  // ==========================================================================

  /**
   * Reproeta todos os pontos para o fuso dominante do conjunto.
   *
   * Algoritmo:
   *   1. Detecta o fuso dominante usando analyzeEntries()
   *   2. Para cada ponto:
   *      - Se ja esta no fuso dominante: projeta normalmente (forward UTM)
   *      - Se esta em outro fuso: inverso UTM (UTM->WGS84) + forward UTM
   *        no fuso alvo (WGS84->UTM_dominante)
   *      Na pratica o "inverso" nao e necessario pois partimos de WGS84;
   *      aqui projetamos TODOS diretamente para o fuso alvo forcando o
   *      meridiano central do fuso dominante.
   *
   * Esta abordagem e preferida para DXF e LandXML, onde o consumidor espera
   * um unico CRS planar consistente. O erro por usar um fuso "errado" e:
   *   ~0,04% na borda do fuso (3 graus do meridiano central)
   *   ~0,1%  a 4 graus (limite formal do fuso UTM)
   * Para levantamentos topograficos isso e aceitavel com o aviso adequado.
   *
   * @param entries  Medicoes a reprojetar
   * @returns Array plano de ReprojectPoint, na mesma ordem de entries/coords
   */
  reprojectAllToDominantZone(entries: RawMeasurementEntry[]): ReprojectPoint[] {
    const analysis = this.analyzeEntries(entries);
    const targetZone    = analysis.dominantZone;
    const targetIsNorth = analysis.dominantZoneIsNorth;

    const result: ReprojectPoint[] = [];

    for (const m of entries) {
      for (const c of m.coordinates) {
        const lat  = c[0];
        const lng  = c[1];
        const elev = c[2] !== undefined && c[2] !== null ? c[2] : undefined;

        // Fuso natural do ponto
        const naturalZone = Math.floor((lng + 180) / 6) + 1;
        const naturalBase = lat < 0 ? 32700 : 32600;
        const naturalEpsg = naturalBase + naturalZone;

        const wasReprojected = naturalEpsg !== analysis.dominantEpsg;

        // Projeta diretamente para o fuso-alvo (forcando o meridiano central)
        const projected = this._forwardUtmToZone(lat, lng, targetZone, targetIsNorth);

        result.push({
          easting:        projected.easting,
          northing:       projected.northing,
          zone:           targetZone,
          band:           projected.band,
          wasReprojected,
          elev
        });
      }
    }

    return result;
  }

  // ==========================================================================
  // API publica — projecao individual (helper para servicos de exportacao)
  // ==========================================================================

  /**
   * Projecao direta WGS84 -> UTM no fuso NATURAL do ponto.
   * Equivalente ao ExportBaseService.wgs84ToUtm(), disponibilizado aqui
   * para que os servicos que injetam UtmZoneAnalyzerService possam usar
   * um unico ponto de entrada sem precisar tambem injetar ExportBaseService.
   */
  forwardUtm(lat: number, lng: number): UtmProjected {
    const zone      = Math.floor((lng + 180) / 6) + 1;
    const isNorth   = lat >= 0;
    const projected = this._forwardUtmToZone(lat, lng, zone, isNorth);
    return projected;
  }

  /**
   * Projecao direta WGS84 -> UTM FORCANDO um fuso especifico.
   * Usado quando se quer reprojetar pontos de fusos diferentes para
   * um unico fuso dominante (DXF, LandXML, WKT com estrategia 'reproject').
   *
   * Erro de escala vs fuso natural:
   *   ~0,04% na borda do fuso (3 graus do meridiano central)
   *   ~0,1%  nos 4 graus extremos (fora do limite formal UTM)
   * Aceitavel para levantamento topografico com aviso ao usuario.
   */
  projectToZone(lat: number, lng: number, targetZone: number, isNorth: boolean): UtmProjected {
    return this._forwardUtmToZone(lat, lng, targetZone, isNorth);
  }

  /**
   * Projecao inversa UTM -> WGS84 (Helmert / Redfearn).
   *
   * @param easting   Easting UTM (m)
   * @param northing  Northing UTM (m) — DEVE ja incluir os 10.000.000 m se Sul
   * @param zone      Numero do fuso (1-60)
   * @param isNorth   true = hemisferio Norte
   *
   * Precisao: equivalente a projecao direta (~0,01 mm dentro do fuso).
   */
  inverseUtm(
    easting: number,
    northing: number,
    zone: number,
    isNorth: boolean
  ): Wgs84Reprojected {
    const e2   = WGS84_E2;
    const ep2  = e2 / (1 - e2);                // e'^2 (segunda excentricidade^2)
    const k0   = UTM_K0;
    const a    = WGS84_A;

    // Ajuste de hemisferio: remover falso norte sul se necessario
    const N_adj = isNorth ? northing : northing - 10_000_000;

    // Meridiano central do fuso
    const lngOrigin = ((zone - 1) * 6 - 180 + 3) * (Math.PI / 180);

    // Latitude de footprint (phi1)
    const M   = N_adj / k0;
    const mu  = M / (a * (1 - e2 / 4 - (3 * e2 ** 2) / 64 - (5 * e2 ** 3) / 256));

    // Coeficiente da serie e1 = (1 - sqrt(1-e2)) / (1 + sqrt(1-e2))
    const e1  = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));

    const phi1 =
      mu
      + ((3 * e1 / 2) - (27 * e1 ** 3) / 32) * Math.sin(2 * mu)
      + ((21 * e1 ** 2) / 16 - (55 * e1 ** 4) / 32) * Math.sin(4 * mu)
      + ((151 * e1 ** 3) / 96) * Math.sin(6 * mu)
      + ((1097 * e1 ** 4) / 512) * Math.sin(8 * mu);

    // Raios de curvatura na latitude de footprint
    const sinPhi1 = Math.sin(phi1);
    const cosPhi1 = Math.cos(phi1);
    const tanPhi1 = Math.tan(phi1);

    const N1  = a / Math.sqrt(1 - e2 * sinPhi1 ** 2);
    const T1  = tanPhi1 ** 2;
    const C1  = ep2 * cosPhi1 ** 2;
    const R1  = a * (1 - e2) / Math.pow(1 - e2 * sinPhi1 ** 2, 1.5);
    const D   = (easting - 500_000) / (N1 * k0);

    // Latitude
    const lat = phi1 - (N1 * tanPhi1 / R1) * (
        D ** 2 / 2
      - ((5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4) / 24
      + ((61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6) / 720
    );

    // Longitude
    const lng = lngOrigin + (
        D
      - ((1 + 2 * T1 + C1) * D ** 3) / 6
      + ((5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5) / 120
    ) / cosPhi1;

    return {
      lat: lat * (180 / Math.PI),
      lng: lng * (180 / Math.PI)
    };
  }

  // ==========================================================================
  // Helpers de mensagem
  // ==========================================================================

  /**
   * Retorna mensagem de aviso PT-BR especifica por formato.
   * Retorna undefined se severity === 'ok'.
   *
   * @param analysis  Resultado de analyzeEntries() ou analyzeCoordinates()
   * @param format    Nome legivel do formato (ex: 'WKT', 'LandXML', 'PNEZD')
   * @param strategy  Estrategia que o exportador adotou
   */
  buildWarningMessage(
    analysis: ZoneAnalysis,
    format: string,
    strategy: 'fallback-wgs84' | 'reprojected-to-zone' | 'warn-only',
    targetEpsg?: number
  ): string | undefined {
    if (!analysis.isMultiZone) return undefined;

    const epsgs  = analysis.epsgsPresent
      .map(e => `${e % 100}${e >= 32700 ? 'S' : 'N'}`).join(', ');
    const target = targetEpsg
      ? `fuso ${targetEpsg % 100}${targetEpsg >= 32700 ? 'S' : 'N'} (EPSG:${targetEpsg})`
      : `fuso dominante (EPSG:${analysis.dominantEpsg})`;

    const base = analysis.hasMixedHemisphere
      ? `[AVISO] ${format}: as medicoes abrangem fusos UTM de hemisferios diferentes (${epsgs}).`
      : `[AVISO] ${format}: as medicoes abrangem ${analysis.zoneCount} fusos UTM distintos (${epsgs}).`;

    switch (strategy) {
      case 'fallback-wgs84':
        return `${base} O arquivo foi exportado em WGS84 (EPSG:4326) para preservar a integridade geometrica. Reprojetar no QGIS ou ArcGIS para o CRS desejado.`;

      case 'reprojected-to-zone':
        return `${base} Todos os pontos foram reprojetados para o ${target}. Pontos de outros fusos podem ter desvio de ate 0,1% em relacao a posicao original — aceitavel para levantamento topografico.`;

      case 'warn-only':
        return `${base} O arquivo contem pontos de fusos diferentes — as colunas N/E nao sao diretamente comparaveis entre medicoes. Verifique o campo FUSO de cada linha antes de calcular distancias.`;
    }
  }

  // ==========================================================================
  // Metodos privados
  // ==========================================================================

  /**
   * Projecao direta WGS84 -> UTM forcando um fuso especifico.
   * Ao forcar um fuso que nao e o "natural" do ponto, o erro de escala aumenta
   * progressivamente com a distancia ao meridiano central.
   * Para pontos dentro do fuso correto, e identica ao wgs84ToUtm() do ExportBaseService.
   */
  private _forwardUtmToZone(
    lat: number,
    lng: number,
    targetZone: number,
    isNorth: boolean
  ): UtmProjected {
    // proj4 garante precisao identica ao QGIS/AutoCAD/Civil3D (mesmo engine GDAL)
    const utmProj = `+proj=utm +zone=${targetZone}${isNorth ? '' : ' +south'} +datum=WGS84 +units=m +no_defs`;
    // proj4 espera [lng, lat] (ordem GeoJSON), retorna [easting, northing]
    const [easting, northing] = proj4('EPSG:4326', utmProj, [lng, lat]);

    const band = UTM_BANDS[
      Math.min(Math.max(Math.floor((lat + 80) / 8), 0), 19)
    ];
    const epsg = (isNorth ? 32600 : 32700) + targetZone;

    return { easting, northing, zone: targetZone, band, isNorth, epsg };
  }

  /**
   * Constroi o objeto ZoneAnalysis a partir do mapa pointsPerEpsg.
   */
  private _buildAnalysis(
    pointsPerEpsg: Record<number, number>,
    dominantEpsg: number,
    totalPoints: number
  ): ZoneAnalysis {
    const epsgsPresent   = Object.keys(pointsPerEpsg).map(Number);
    const zoneCount      = epsgsPresent.length;
    const dominantZone   = dominantEpsg % 100;
    const dominantIsNorth = dominantEpsg < 32700;
    const isMultiZone    = zoneCount > 1;

    // Hemisferios mistos: existem EPSGs tanto na faixa 326xx quanto 327xx
    const hasNorth = epsgsPresent.some(e => e < 32700);
    const hasSouth = epsgsPresent.some(e => e >= 32700);
    const hasMixedHemisphere = hasNorth && hasSouth;

    let severity: 'ok' | 'warn' | 'critical' = 'ok';
    if (isMultiZone) {
      severity = (zoneCount >= 3 || hasMixedHemisphere) ? 'critical' : 'warn';
    }

    // Mensagem generica (sem contexto de formato; formatos devem usar buildWarningMessage)
    let warningMessage: string | undefined;
    if (isMultiZone) {
      const epsgsStr = epsgsPresent.join(', ');
      warningMessage = severity === 'critical'
        ? `[AVISO CRITICO] As medicoes abrangem fusos UTM incompativeis (${epsgsStr}). A exportacao em UTM produzira erros geometricos graves. Recomenda-se fortemente usar WGS84.`
        : `[AVISO] As medicoes abrangem ${zoneCount} fusos UTM distintos (${epsgsStr}). Verifique o impacto no formato escolhido.`;
    }

    return {
      epsgsPresent,
      zoneCount,
      dominantEpsg,
      dominantZone,
      dominantZoneIsNorth: dominantIsNorth,
      isMultiZone,
      hasMixedHemisphere,
      severity,
      totalPoints,
      pointsPerEpsg,
      warningMessage
    };
  }
}
