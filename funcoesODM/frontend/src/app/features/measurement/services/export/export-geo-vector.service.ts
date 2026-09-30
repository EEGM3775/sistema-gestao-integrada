/**
 * ExportGeoVectorService
 *
 * Formatos geoespaciais vetoriais:
 *  - GeoJSON : RFC 7946 FeatureCollection
 *  - KML     : CRS fixo WGS84 (Google Earth, Garmin)
 *  - GPX     : CRS fixo WGS84 (GPS track)
 *  - WKT     : Well-Known Text (PostGIS, SpatiaLite)
 *  - GML     : Geography Markup Language (IBGE, GeoServer)
 *
 * KML e GPX usam WGS84 fixo (spec exige).
 * GeoJSON, WKT e GML respeitam o CoordFormat escolhido pelo usuário.
 */

import { Injectable, inject } from '@angular/core';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat
} from './export-base.service';
import { UtmZoneAnalyzerService } from './utm-zone-analyzer.service';

const TYPE_PT: Record<string, string> = {
  distance: 'Distancia',
  area:     'Area',
  volume:   'Volume',
  height:   'Altura'
};

@Injectable({ providedIn: 'root' })
export class ExportGeoVectorService {

  private base     = inject(ExportBaseService);
  private analyzer = inject(UtmZoneAnalyzerService);

  // ==========================================================================
  // GeoJSON — RFC 7946
  // ==========================================================================

  /**
   * Gera um GeoJSON FeatureCollection.
   *
   * Geometria (obrigatoriamente WGS84 per RFC 7946):
   *   distance / height → LineString  [lng, lat, Z?]
   *   area / volume     → Polygon     (anel fechado automaticamente)
   *
   * Properties inclui campo 'pontos' com coordenadas no formato escolhido.
   *
   * @param coordFormat Afeta apenas o campo 'pontos' em properties; geometria é sempre WGS84.
   */
  buildGeoJSON(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84'): string {
    const features = entries.map(m => {
      const isPolygon = m.type === 'area' || m.type === 'volume';

      const toGeoCoord = (c: number[]): number[] => {
        const base = [c[1], c[0]]; // [lng, lat]
        if (c[2] !== undefined && c[2] !== null) base.push(c[2]);
        return base;
      };

      let geometry: object;
      if (isPolygon && m.coordinates.length >= 3) {
        const ring = m.coordinates.map(toGeoCoord);
        // Fechar anel se necessário
        const first = ring[0];
        const last  = ring[ring.length - 1];
        if (first[0] !== last[0] || first[1] !== last[1]) ring.push([...first]);
        geometry = { type: 'Polygon', coordinates: [ring] };
      } else {
        geometry = { type: 'LineString', coordinates: m.coordinates.map(toGeoCoord) };
      }

      const pontos = m.coordinates.map((c, i) => {
        const elev     = c[2];
        const hasElev  = elev !== undefined && elev !== null;
        if (coordFormat === 'utm') {
          const utm = this.base.wgs84ToUtm(c[0], c[1]);
          return {
            pt:    i + 1,
            norte: +utm.northing.toFixed(3),
            este:  +utm.easting.toFixed(3),
            fuso:  `${utm.zone}${utm.band}`,
            ...(hasElev ? { elev_m: +(elev as number).toFixed(3) } : {})
          };
        } else {
          return {
            pt:  i + 1,
            lat: +c[0].toFixed(7),
            lng: +c[1].toFixed(7),
            ...(hasElev ? { elev_m: +(elev as number).toFixed(3) } : {})
          };
        }
      });

      return {
        type: 'Feature',
        geometry,
        properties: {
          id:          m.id,
          nome:        m.name,
          tipo:        TYPE_PT[m.type] ?? m.type,
          valor:       m.value,
          unidade:     m.unit,
          fonteDados:  m.dataSource,
          coordFormat,
          numPontos:   m.coordinates.length,
          criadoEm:    this.base.toIsoString(m.createdAt),
          pontos
        }
      };
    });

    return JSON.stringify({ type: 'FeatureCollection', features }, null, 2);
  }

  // ==========================================================================
  // KML — WGS84 fixo (spec KML 2.2)
  // ==========================================================================

  /**
   * Gera KML 2.2 com um Placemark por medição.
   * Coordenadas sempre em WGS84 decimal.
   */
  buildKML(entries: RawMeasurementEntry[]): string {
    const placemarks = entries.map(m => {
      const coords = m.coordinates
        .map(c => `${c[1]},${c[0]}${c[2] !== undefined && c[2] !== null ? ',' + c[2].toFixed(3) : ''}`)
        .join('\n          ');

      const isPolygon = m.type === 'area' || m.type === 'volume';

      // KML spec exige LinearRing fechado: primeiro ponto == ultimo ponto
      let coordsForPolygon = coords;
      if (isPolygon && m.coordinates.length >= 3) {
        const first = m.coordinates[0];
        const last  = m.coordinates[m.coordinates.length - 1];
        const firstStr = `${first[1]},${first[0]}${first[2] !== undefined && first[2] !== null ? ',' + first[2].toFixed(3) : ''}`;
        const lastStr  = `${last[1]},${last[0]}${last[2] !== undefined && last[2] !== null ? ',' + last[2].toFixed(3) : ''}`;
        if (firstStr !== lastStr) {
          coordsForPolygon = coords + '\n          ' + firstStr;
        }
      }

      // Se algum ponto tiver Z, usar altitudeMode=absolute para que o Google Earth
      // respeite os valores de elevação (padrão clampToGround ignora Z)
      const hasZ = m.coordinates.some(c => c[2] !== undefined && c[2] !== null);
      const altMode = hasZ ? '\n      <altitudeMode>absolute</altitudeMode>' : '';

      const coordBlock = isPolygon
        ? `<Polygon>${altMode}\n      <outerBoundaryIs><LinearRing><coordinates>\n          ${coordsForPolygon}\n        </coordinates></LinearRing></outerBoundaryIs></Polygon>`
        : `<LineString>${altMode}\n      <coordinates>\n          ${coords}\n        </coordinates></LineString>`;

      return `  <Placemark>
    <name>${this.base.escapeXml(m.name)}</name>
    <description><![CDATA[Tipo: ${TYPE_PT[m.type] ?? m.type} | Valor: ${m.value.toFixed(4)} ${m.unit} | ${this.base.toIsoString(m.createdAt).slice(0, 10)}]]></description>
    <ExtendedData>
      <Data name="id"><value>${m.id}</value></Data>
      <Data name="tipo"><value>${TYPE_PT[m.type] ?? m.type}</value></Data>
      <Data name="valor"><value>${m.value}</value></Data>
      <Data name="unidade"><value>${m.unit}</value></Data>
    </ExtendedData>
    ${coordBlock}
  </Placemark>`;
    }).join('\n');

    return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Medições FuncoesODM</name>
    <description>Exportado em ${new Date().toISOString()}</description>
${placemarks}
  </Document>
</kml>`;
  }

  // ==========================================================================
  // GPX — WGS84 fixo (GPX 1.1)
  // ==========================================================================

  /**
   * Gera GPX 1.1.
   *
   * Estratégia por tipo de medição:
   *  - height   → <wpt> para cada um dos 2 pontos (são pontos estáticos, não um percurso)
   *  - distance / area / volume → <trk> com <trkseg> (representam traçados)
   *
   * O schema GPX 1.1 exige a ordem: metadata → wpt* → rte* → trk*
   * Coordenadas sempre em WGS84 decimal (spec GPX).
   */
  buildGPX(entries: RawMeasurementEntry[]): string {
    const heightEntries = entries.filter(m => m.type === 'height');
    const trackEntries  = entries.filter(m => m.type !== 'height');

    // --- Waypoints (medições de altura: ponto A e ponto B) ---
    const wpts = heightEntries.flatMap(m =>
      m.coordinates.map((c, i) => {
        const elev = c[2] !== undefined && c[2] !== null
          ? `\n    <ele>${c[2].toFixed(3)}</ele>`
          : '';
        const label = `${this.base.escapeXml(m.name)} — Pt ${i === 0 ? 'A' : 'B'}`;
        const desc  = `${TYPE_PT[m.type]} | ${m.value.toFixed(4)} ${m.unit} | ${this.base.toIsoString(m.createdAt).slice(0, 10)}`;
        return `  <wpt lat="${c[0].toFixed(7)}" lon="${c[1].toFixed(7)}">${elev}
    <name>${label}</name>
    <desc><![CDATA[${desc}]]></desc>
  </wpt>`;
      })
    ).join('\n');

    // --- Tracks (distância, área, volume) ---
    const tracks = trackEntries.map(m => {
      const pts = m.coordinates.map(c => {
        const elev = c[2] !== undefined && c[2] !== null
          ? `\n        <ele>${c[2].toFixed(3)}</ele>`
          : '';
        return `      <trkpt lat="${c[0].toFixed(7)}" lon="${c[1].toFixed(7)}">${elev}\n      </trkpt>`;
      }).join('\n');
      const desc = `${TYPE_PT[m.type] ?? m.type} | ${m.value.toFixed(4)} ${m.unit} | ${this.base.toIsoString(m.createdAt).slice(0, 10)}`;

      return `  <trk>
    <name>${this.base.escapeXml(m.name)}</name>
    <desc><![CDATA[${desc}]]></desc>
    <type>${TYPE_PT[m.type] ?? m.type}</type>
    <trkseg>
${pts}
    </trkseg>
  </trk>`;
    }).join('\n');

    const body = [wpts, tracks].filter(s => s.length > 0).join('\n');

    return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="FuncoesODM"
     xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>Medições FuncoesODM</name>
    <time>${new Date().toISOString()}</time>
  </metadata>
${body}
</gpx>`;
  }

  // ==========================================================================
  // WKT — Well-Known Text
  // ==========================================================================

  /**
   * Gera WKT (uma geometria por linha, com comentário de metadados).
   * Suporta WGS84 e UTM.
   */
  /**
   * @returns { content, warning? }
   *   warning: mensagem PT-BR se houve fallback de UTM para WGS84 por multi-fuso.
   */
  buildWKT(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat = 'wgs84',
    targetEpsg: number | null = null
  ): { content: string; warning?: string } {
    const analysis    = coordFormat === 'utm' ? this.analyzer.analyzeEntries(entries) : null;
    const isMultiZone = analysis?.isMultiZone ?? false;

    // targetEpsg == null  → fallback WGS84 quando multi-fuso
    // targetEpsg == number → reprojetar todos para aquele EPSG
    const reprZone    = targetEpsg !== null ? targetEpsg % 100 : undefined;
    const reprIsNorth = targetEpsg !== null ? targetEpsg < 32700 : false;

    let effectiveFmt: CoordFormat;
    let warning: string | undefined;
    if (isMultiZone && targetEpsg !== null) {
      effectiveFmt = 'utm';
      warning = this.analyzer.buildWarningMessage(analysis!, 'WKT', 'reprojected-to-zone', targetEpsg);
    } else if (isMultiZone) {
      effectiveFmt = 'wgs84';
      warning = this.analyzer.buildWarningMessage(analysis!, 'WKT', 'fallback-wgs84');
    } else {
      effectiveFmt = coordFormat;
    }

    const crsLabel = effectiveFmt === 'utm'
      ? (targetEpsg ? `UTM WGS84 EPSG:${targetEpsg}` : 'UTM WGS84')
      : 'WGS84 decimal (EPSG:4326)';

    const lines: string[] = [
      `-- WKT exportado por FuncoesODM em ${new Date().toISOString()}`,
      `-- CRS: ${crsLabel}`,
      ''
    ];

    for (const m of entries) {
      const isPolygon = m.type === 'area' || m.type === 'volume';

      const toCoord = (c: number[]): string => {
        if (effectiveFmt === 'utm') {
          const utm = (isMultiZone && reprZone !== undefined)
            ? this.analyzer.projectToZone(c[0], c[1], reprZone, reprIsNorth)
            : this.base.wgs84ToUtm(c[0], c[1]);
          const z = c[2] !== undefined && c[2] !== null ? ` ${c[2].toFixed(3)}` : '';
          return `${utm.easting.toFixed(3)} ${utm.northing.toFixed(3)}${z}`;
        } else {
          const z = c[2] !== undefined && c[2] !== null ? ` ${c[2].toFixed(3)}` : '';
          return `${c[1].toFixed(7)} ${c[0].toFixed(7)}${z}`;
        }
      };

      let wkt: string;
      if (isPolygon && m.coordinates.length >= 3) {
        const ring = [...m.coordinates];
        const f = ring[0]; const l = ring[ring.length - 1];
        if (f[0] !== l[0] || f[1] !== l[1]) ring.push([...f]);
        wkt = `POLYGON((${ring.map(toCoord).join(', ')}))`;
      } else if (m.coordinates.length === 1) {
        wkt = `POINT(${toCoord(m.coordinates[0])})`;
      } else {
        wkt = `LINESTRING(${m.coordinates.map(toCoord).join(', ')})`;
      }

      lines.push(`-- id=${m.id} | nome=${m.name} | tipo=${TYPE_PT[m.type] ?? m.type} | valor=${m.value} ${m.unit}`);
      lines.push(wkt);
      lines.push('');
    }

    return { content: lines.join('\n'), warning };
  }

  // ==========================================================================
  // GML — Geography Markup Language 3.2
  // ==========================================================================

  /**
   * Gera GML 3.2 basico.
   * CRS configuravel (WGS84 ou UTM).
   * Retorna { content, warning? } — warning preenchido se houve fallback de fuso.
   */
  buildGML(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat = 'wgs84',
    targetEpsg: number | null = null
  ): { content: string; warning?: string } {
    const analysis    = coordFormat === 'utm' ? this.analyzer.analyzeEntries(entries) : null;
    const isMultiZone = analysis?.isMultiZone ?? false;

    const reprZone    = targetEpsg !== null ? targetEpsg % 100 : undefined;
    const reprIsNorth = targetEpsg !== null ? targetEpsg < 32700 : false;

    let srsName = 'urn:ogc:def:crs:EPSG::4326';
    let warning: string | undefined;
    if (coordFormat === 'utm') {
      if (!isMultiZone && analysis) {
        srsName = `urn:ogc:def:crs:EPSG::${analysis.dominantEpsg}`;
      } else if (isMultiZone && targetEpsg !== null) {
        srsName = `urn:ogc:def:crs:EPSG::${targetEpsg}`;
        warning = this.analyzer.buildWarningMessage(analysis!, 'GML', 'reprojected-to-zone', targetEpsg);
      } else if (isMultiZone) {
        // fallback WGS84 — srsName ja e 4326
        warning = this.analyzer.buildWarningMessage(analysis!, 'GML', 'fallback-wgs84');
      }
    }

    const members = entries.map(m => {
      const isPolygon = m.type === 'area' || m.type === 'volume';

      // srsDimension: OBRIGATORIO quando ha Z — sem ele, leitores (QGIS, GeoServer)
      // interpretam o posList como pares 2D e deslocam os valores de elevacao para
      // a posicao de latitude/longitude do proximo ponto, colocando-os fora do mapa.
      const hasZ  = m.coordinates.some(c => c[2] !== undefined && c[2] !== null);
      const dim   = hasZ ? 3 : 2;
      const dimAttr = ` srsDimension="${dim}"`;

      const toPosList = (coords: number[][]): string =>
        coords.map(c => {
          if (coordFormat === 'utm') {
            const utm = (isMultiZone && reprZone !== undefined)
              ? this.analyzer.projectToZone(c[0], c[1], reprZone, reprIsNorth)
              : this.base.wgs84ToUtm(c[0], c[1]);
            const z   = hasZ ? ` ${c[2] !== undefined && c[2] !== null ? c[2].toFixed(3) : '0.000'}` : '';
            return `${utm.northing.toFixed(3)} ${utm.easting.toFixed(3)}${z}`;
          } else {
            const z   = hasZ ? ` ${c[2] !== undefined && c[2] !== null ? c[2].toFixed(3) : '0.000'}` : '';
            return `${c[0].toFixed(7)} ${c[1].toFixed(7)}${z}`;
          }
        }).join(' ');

      let geom: string;
      if (isPolygon && m.coordinates.length >= 3) {
        const ring = [...m.coordinates];
        const f = ring[0]; const l = ring[ring.length - 1];
        if (f[0] !== l[0] || f[1] !== l[1]) ring.push([...f]);
        geom = `<gml:Polygon srsName="${srsName}">
        <gml:exterior><gml:LinearRing>
          <gml:posList${dimAttr}>${toPosList(ring)}</gml:posList>
        </gml:LinearRing></gml:exterior>
      </gml:Polygon>`;
      } else {
        geom = `<gml:LineString srsName="${srsName}">
        <gml:posList${dimAttr}>${toPosList(m.coordinates)}</gml:posList>
      </gml:LineString>`;
      }

      // gml:id deve ser NCName valido (nao pode comecar com numero)
      const gmlId = `medicao_${m.id}`;

      return `  <gml:featureMember>
    <Medicao gml:id="${gmlId}">
      <nome>${this.base.escapeXml(m.name)}</nome>
      <tipo>${TYPE_PT[m.type] ?? m.type}</tipo>
      <valor>${m.value}</valor>
      <unidade>${m.unit}</unidade>
      <criadoEm>${this.base.toIsoString(m.createdAt)}</criadoEm>
      <geometria>${geom}</geometria>
    </Medicao>
  </gml:featureMember>`;
    }).join('\n');

    const content = `<?xml version="1.0" encoding="UTF-8"?>
<gml:FeatureCollection
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd">
${members}
</gml:FeatureCollection>`;

    return { content, warning };
  }
}
