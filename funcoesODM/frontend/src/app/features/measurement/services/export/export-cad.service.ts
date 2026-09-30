/**
 * ExportCadService
 *
 * Formatos CAD / Engenharia:
 *  - DXF     : AutoCAD DXF R12 ASCII
 *  - SVG     : Scalable Vector Graphics (diagrama 2D)
 *  - LandXML : Civil 3D / Trimble / 12d (topografia)
 *
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
export class ExportCadService {

  private base     = inject(ExportBaseService);
  private analyzer = inject(UtmZoneAnalyzerService);

  // ==========================================================================
  // DXF — AutoCAD DXF R12 ASCII
  // ==========================================================================

  /**
   * Gera um arquivo DXF R12 ASCII.
   * Cada medição → entidade POLYLINE (linha aberta ou fechada).
   *
   * @param coordFormat 'utm' (padrão — CAD espera metros) ou 'wgs84' (graus decimais)
   * @param targetEpsg  Quando não-nulo, força todos os pontos para aquele fuso UTM.
   *                    Quando nulo em cenário multi-fuso, cai de volta para WGS84.
   */
  buildDXF(
    entries: RawMeasurementEntry[],
    coordFormat: CoordFormat = 'utm',
    targetEpsg: number | null = null
  ): string {
    const analysis    = coordFormat === 'utm' ? this.analyzer.analyzeEntries(entries) : null;
    const isMultiZone = analysis?.isMultiZone ?? false;

    // Determina formato efetivo:
    //   multi-fuso + targetEpsg → força aquele fuso
    //   multi-fuso sem targetEpsg → cai para WGS84 (evita mistura de fusos no DXF)
    //   fuso único → usa UTM nativo de cada ponto
    let effectiveFmt: CoordFormat;
    if (coordFormat === 'utm' && isMultiZone && targetEpsg !== null) {
      effectiveFmt = 'utm';
    } else if (coordFormat === 'utm' && isMultiZone && targetEpsg === null) {
      effectiveFmt = 'wgs84';
    } else {
      effectiveFmt = coordFormat;
    }

    const reprZone    = targetEpsg !== null ? targetEpsg % 100 : undefined;
    const reprIsNorth = targetEpsg !== null ? targetEpsg < 32700 : false;

    const entities = entries.map((m, _idx) => {
      const isPolygon = m.type === 'area' || m.type === 'volume';
      const pts = m.coordinates.map(c => {
        if (effectiveFmt === 'utm') {
          const utm = (isMultiZone && reprZone !== undefined)
            ? this.analyzer.projectToZone(c[0], c[1], reprZone, reprIsNorth)
            : this.base.wgs84ToUtm(c[0], c[1]);
          return { x: utm.easting, y: utm.northing, z: c[2] ?? 0 };
        }
        return { x: c[1], y: c[0], z: c[2] ?? 0 };
      });

      const vertLines = pts.map(p =>
        `  0\nVERTEX\n  8\n${m.name}\n 10\n${p.x.toFixed(3)}\n 20\n${p.y.toFixed(3)}\n 30\n${p.z.toFixed(3)}`
      ).join('\n');

      const closed = isPolygon ? '  70\n1\n' : '  70\n0\n';

      return `  0
POLYLINE
  8
${m.name}
 66
     1
${closed}${vertLines}
  0
SEQEND`;
    }).join('\n');

    return `  0
SECTION
  2
HEADER
  9
$ACADVER
  1
AC1009
  0
ENDSEC
  0
SECTION
  2
ENTITIES
${entities}
  0
ENDSEC
  0
EOF`;
  }

  // ==========================================================================
  // SVG — Scalable Vector Graphics
  // ==========================================================================

  /**
   * Gera um SVG simples com as medições.
   * Coordenadas normalizadas para o viewBox.
   */
  buildSVG(entries: RawMeasurementEntry[], coordFormat: CoordFormat = 'wgs84'): string {
    if (entries.length === 0 || entries.every(e => e.coordinates.length === 0)) {
      return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><text x="10" y="20">Sem dados</text></svg>';
    }

    // Calcular bounding box
    const allCoords = entries.flatMap(e => e.coordinates);
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

    const toXY = (c: number[]): { x: number; y: number } => {
      if (coordFormat === 'utm') {
        const utm = this.base.wgs84ToUtm(c[0], c[1]);
        return { x: utm.easting, y: utm.northing };
      }
      return { x: c[1], y: c[0] };
    };

    for (const c of allCoords) {
      const { x, y } = toXY(c);
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }

    const W = 800, H = 600, PAD = 40;
    const scaleX = (maxX - minX) === 0 ? 1 : (W - 2 * PAD) / (maxX - minX);
    const scaleY = (maxY - minY) === 0 ? 1 : (H - 2 * PAD) / (maxY - minY);
    const scale  = Math.min(scaleX, scaleY);

    const project = (c: number[]): string => {
      const { x, y } = toXY(c);
      const px = PAD + (x - minX) * scale;
      const py = H - PAD - (y - minY) * scale; // inverter Y (SVG eixo Y vai pra baixo)
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    };

    const COLORS = ['#E53935', '#1E88E5', '#43A047', '#FB8C00', '#8E24AA', '#00ACC1'];

    const shapes = entries.map((m, i) => {
      const color   = COLORS[i % COLORS.length];
      const pts     = m.coordinates.map(project).join(' ');
      const isArea  = m.type === 'area' || m.type === 'volume';
      const shape   = isArea
        ? `<polygon points="${pts}" fill="${color}33" stroke="${color}" stroke-width="1.5"/>`
        : `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/>`;
      // Label no centróide
      const cx = m.coordinates.reduce((s, c) => s + toXY(c).x, 0) / m.coordinates.length;
      const cy = m.coordinates.reduce((s, c) => s + toXY(c).y, 0) / m.coordinates.length;
      const lx = (PAD + (cx - minX) * scale).toFixed(1);
      const ly = (H - PAD - (cy - minY) * scale - 6).toFixed(1);
      const label = `<text x="${lx}" y="${ly}" font-size="10" fill="${color}" text-anchor="middle">${this.base.escapeXml(m.name)}</text>`;

      return `${shape}\n  ${label}`;
    }).join('\n  ');

    return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="#1a1a2e"/>
  <text x="${W / 2}" y="20" font-size="13" fill="#ccc" text-anchor="middle">Medições FuncoesODM — ${new Date().toISOString().slice(0, 10)}</text>
  ${shapes}
</svg>`;
  }

  // ==========================================================================
  // LandXML — Civil 3D / Trimble / 12d
  // ==========================================================================

  /**
   * Gera LandXML 1.2 com geometria visivel no Civil 3D.
   *
   * Estrategia por tipo de medicao:
   *  - distance / height → <Alignments><Alignment><CoordGeom><Line> ...
   *    Civil 3D importa como objeto Alignment (polilinha).
   *  - area / volume     → <Parcels><Parcel><CoordGeom><Line> ...
   *    Civil 3D importa como objeto Parcel (poligono fechado).
   *
   * Coordenadas: UTM WGS84 (Norte Easting), ordem Norte/Leste conforme LandXML 1.2 spec.
   *
   * IMPORTANTE: <Survey><CgPoints> importa apenas como pontos COGO (dots) no
   * Civil 3D — sem geometria linear. Por isso usamos Alignments e Parcels.
   */
  /**
   * @param targetEpsg  Quando nao-nulo, forca todos os pontos para aquele fuso (ex: 32723).
   *                    Quando nulo e ha multi-fuso, usa automaticamente o fuso dominante.
   *                    O modal exibe popup de selecao ao usuario quando isMultiZone === true.
   */
  buildLandXML(entries: RawMeasurementEntry[], targetEpsg: number | null = null): string {
    const alignmentEntries = entries.filter(m => m.type === 'distance' || m.type === 'height');
    const parcelEntries    = entries.filter(m => m.type === 'area'     || m.type === 'volume');

    // --- Detecta fuso dominante e reprojeta todos os pontos para ele ---
    // Sem isso, pontos de fusos diferentes ficam em sistemas de coordenadas
    // distintos e o Civil 3D os desenha deslocados centenas de km.
    const analysis = this.analyzer.analyzeEntries(entries);
    // targetEpsg fornecido pelo usuario (popup multi-fuso) tem prioridade;
    // caso contrario usa o fuso dominante detectado automaticamente.
    const epsg    = targetEpsg ?? analysis.dominantEpsg;
    const zone    = epsg % 100;
    const isNorth = epsg < 32700;

    // Nome do sistema de coordenadas no formato Civil 3D (ex: UTM84-23S)
    // Civil 3D usa este nome para associar o CRS ao projeto e posicionar corretamente.
    const csSide      = isNorth ? 'N' : 'S';
    const csNameC3D   = `UTM84-${zone}${csSide}`;
    const csDesc      = `UTM WGS84 Zone ${zone} ${isNorth ? 'North' : 'South'} (EPSG:${epsg})`;

    // Projeta um ponto WGS84 para o fuso dominante
    const toUtmPt = (c: number[]): { n: string; e: string; z: string } => {
      const utm  = this.analyzer.projectToZone(c[0], c[1], zone, isNorth);
      const elev = c[2] !== undefined && c[2] !== null ? c[2].toFixed(3) : '0.000';
      return { n: utm.northing.toFixed(3), e: utm.easting.toFixed(3), z: elev };
    };

    const buildLines = (pts: { n: string; e: string; z: string }[]): string =>
      pts.slice(0, -1).map((p, i) => {
        const next = pts[i + 1];
        return `        <Line>\n          <Start>${p.n} ${p.e}</Start>\n          <End>${next.n} ${next.e}</End>\n        </Line>`;
      }).join('\n');

    // --- Alignments (distance / height) ---
    const alignmentsXml = alignmentEntries.map(m => {
      const pts  = m.coordinates.map(toUtmPt);
      const desc = `${this.base.escapeXml(TYPE_PT[m.type] ?? m.type)}: ${m.value.toFixed(4)} ${m.unit}`;
      return `    <Alignment name="${this.base.escapeXml(m.name)}" length="${m.value.toFixed(4)}" staStart="0.000" desc="${desc}">
      <CoordGeom>
${buildLines(pts)}
      </CoordGeom>
    </Alignment>`;
    }).join('\n');

    // --- Parcels (area / volume) ---
    const parcelsXml = parcelEntries.map(m => {
      const pts  = m.coordinates.map(toUtmPt);
      // Fechar o anel se necessario (ultimo ponto == primeiro)
      const ring = [...pts];
      if (ring.length >= 2 && (ring[0].n !== ring[ring.length - 1].n || ring[0].e !== ring[ring.length - 1].e)) {
        ring.push(ring[0]);
      }
      const areaVal = m.type === 'area' ? m.value.toFixed(4) : '0.0000';
      const desc    = `${this.base.escapeXml(TYPE_PT[m.type] ?? m.type)}: ${m.value.toFixed(4)} ${m.unit}`;
      return `    <Parcel name="${this.base.escapeXml(m.name)}" area="${areaVal}" desc="${desc}">
      <CoordGeom>
${buildLines(ring)}
      </CoordGeom>
    </Parcel>`;
    }).join('\n');

    // --- CgPoints (formato correto Civil 3D) ---
    // Elemento correto: <CgPoint name="N" desc="..." oID="N"> (nao <P id="N">)
    // Todos os pontos reprojetados para o fuso dominante (zone/isNorth),
    // garantindo consistencia com os Alignments e Parcels acima.
    let globalId = 1;
    const cgPointLines = entries.flatMap(m =>
      m.coordinates.map(c => {
        const utm  = this.analyzer.projectToZone(c[0], c[1], zone, isNorth);
        const elev = c[2] !== undefined && c[2] !== null ? c[2].toFixed(3) : '0.000';
        const desc = this.base.escapeXml(`${m.name} — ${TYPE_PT[m.type] ?? m.type}`);
        const id   = globalId++;
        return `    <CgPoint name="${id}" desc="${desc}" oID="${id}">${utm.northing.toFixed(3)} ${utm.easting.toFixed(3)} ${elev}</CgPoint>`;
      })
    );
    const cgPointsBlock = `  <CgPoints>\n${cgPointLines.join('\n')}\n  </CgPoints>\n`;

    const alignmentsBlock = alignmentsXml.length > 0
      ? `  <Alignments>\n${alignmentsXml}\n  </Alignments>\n` : '';
    const parcelsBlock = parcelsXml.length > 0
      ? `  <Parcels>\n${parcelsXml}\n  </Parcels>\n` : '';

    const now     = new Date();
    const dateStr = now.toISOString().slice(0, 10);
    const timeStr = now.toTimeString().slice(0, 8);

    return `<?xml version="1.0" encoding="UTF-8"?>
<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" version="1.2" date="${dateStr}" time="${timeStr}" readOnly="false">
  <Units>
    <Metric linearUnit="meter" areaUnit="squareMeter" volumeUnit="cubicMeter" temperatureUnit="celsius" pressureUnit="milliBar"/>
  </Units>
  <Application name="FuncoesODM" version="1.0"/>
  <Project name="Medicoes" desc="Pontos e geometrias exportados do FuncoesODM"/>
  <CoordinateSystem name="${csNameC3D}" desc="${csDesc}" epsgCode="${epsg}"/>
${cgPointsBlock}${alignmentsBlock}${parcelsBlock}</LandXML>`;
  }
}
