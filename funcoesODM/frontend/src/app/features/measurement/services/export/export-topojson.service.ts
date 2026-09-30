/**
 * ExportTopoJSONService
 *
 * Gera TopoJSON (formato JSON de topologia) a partir das medicoes.
 *
 * TopoJSON é uma extensão do GeoJSON que codifica a topologia das geometrias:
 *  - Arcos são compartilhados entre geometrias adjacentes (economiza tamanho)
 *  - Formato amplamente usado com D3.js, Mapshaper e ferramentas de visualização
 *
 * Especificação: https://github.com/topojson/topojson-specification
 *
 * CRS: WGS84 fixo (como GeoJSON/KML/GPX) — coordenadas sempre [lng, lat].
 * Sem popup de multi-fuso: cada ponto mantém suas coordenadas geográficas.
 *
 * Estrutura gerada:
 *   {
 *     "type": "Topology",
 *     "bbox": [minLng, minLat, maxLng, maxLat],
 *     "objects": {
 *       "medicoes_linhas": GeometryCollection (distance / height),
 *       "medicoes_areas":  GeometryCollection (area / volume)
 *     },
 *     "arcs": [ [[lng,lat], ...], ... ]
 *   }
 */

import { Injectable, inject } from '@angular/core';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat
} from './export-base.service';

// ─── Tipos internos do TopoJSON ──────────────────────────────────────────────

interface TopoGeometry {
  type: 'LineString' | 'Polygon';
  arcs: number[] | number[][];
  properties: Record<string, string | number | null>;
  id?: string | number;
}

interface TopoGeometryCollection {
  type: 'GeometryCollection';
  geometries: TopoGeometry[];
}

interface Topology {
  type: 'Topology';
  bbox: [number, number, number, number];
  objects: Record<string, TopoGeometryCollection>;
  arcs: number[][][];
}

// ─── Rótulos para o campo "tipo" ──────────────────────────────────────────────

const TIPO_PT: Record<string, string> = {
  distance: 'Distancia',
  area:     'Area',
  volume:   'Volume',
  height:   'Altura',
};

// ─── Service ─────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class ExportTopoJSONService {

  private base = inject(ExportBaseService);

  // ──────────────────────────────────────────────────────────────────────────
  // API pública
  // ──────────────────────────────────────────────────────────────────────────

  /**
   * Constrói e faz download de um arquivo .topojson.
   *
   * @param entries    Medições brutas
   * @param projectId  ID do projeto (usado no nome do arquivo)
   */
  exportTopoJSON(
    entries:   RawMeasurementEntry[],
    projectId: number | string = 0,
  ): void {
    const json   = this.buildTopoJSON(entries);
    const text   = JSON.stringify(json);
    const fname  = this.base.buildFilename(projectId, 'topojson', 'topojson', null);
    this.base.downloadString(text, fname, 'application/json;charset=utf-8;');
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Construção do objeto Topology
  // ──────────────────────────────────────────────────────────────────────────

  /** Gera o objeto Topology completo. */
  buildTopoJSON(entries: RawMeasurementEntry[]): Topology {
    const linhas: RawMeasurementEntry[] = entries.filter(
      m => m.type === 'distance' || m.type === 'height',
    );
    const areas: RawMeasurementEntry[] = entries.filter(
      m => m.type === 'area' || m.type === 'volume',
    );

    const allArcs: number[][][] = [];

    // Cada medição contribui com UM arco (ou UM anel para polígono)
    const linhasGeoms = linhas.map(m => this.buildLineString(m, allArcs));
    const areasGeoms  = areas.map(m  => this.buildPolygon(m, allArcs));

    return {
      type: 'Topology',
      bbox: this.computeBbox(entries),
      objects: {
        medicoes_linhas: { type: 'GeometryCollection', geometries: linhasGeoms },
        medicoes_areas:  { type: 'GeometryCollection', geometries: areasGeoms  },
      },
      arcs: allArcs,
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Geometrias individuais
  // ──────────────────────────────────────────────────────────────────────────

  private buildLineString(
    m:       RawMeasurementEntry,
    allArcs: number[][][],
  ): TopoGeometry {
    const coords = m.coordinates.map(c => this.toArcCoord(c));
    const arcIdx = allArcs.length;
    allArcs.push(coords);

    return {
      type:       'LineString',
      arcs:       [arcIdx],
      id:         m.id,
      properties: this.buildProps(m),
    };
  }

  private buildPolygon(
    m:       RawMeasurementEntry,
    allArcs: number[][][],
  ): TopoGeometry {
    const ring = m.coordinates.map(c => this.toArcCoord(c));

    // Garantir que o anel seja fechado (primeiro ponto = último ponto)
    if (ring.length >= 1) {
      const first = ring[0];
      const last  = ring[ring.length - 1];
      if (first[0] !== last[0] || first[1] !== last[1]) {
        ring.push([...first]);
      }
    }

    const arcIdx = allArcs.length;
    allArcs.push(ring);

    return {
      type:       'Polygon',
      arcs:       [[arcIdx]],
      id:         m.id,
      properties: this.buildProps(m),
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────────────────────

  /**
   * Converte um ponto bruto (lat, lng[, Z]) em posição WGS84 para arco.
   * TopoJSON segue a convenção [longitude, latitude] do GeoJSON.
   */
  private toArcCoord(c: number[]): number[] {
    const pos: number[] = [c[1], c[0]]; // [lng, lat]
    if (c[2] !== undefined && c[2] !== null) pos.push(c[2]);
    return pos;
  }

  /** Propriedades da medição (mesmas convenções do GeoJSON e Shapefile). */
  private buildProps(m: RawMeasurementEntry): Record<string, string | number | null> {
    return {
      id:        m.id,
      nome:      m.name,
      tipo:      TIPO_PT[m.type] ?? m.type,
      valor:     m.value != null ? +m.value.toFixed(3) : null,
      unidade:   m.unit,
      n_pontos:  m.coordinates.length,
      fonte:     m.dataSource ?? null,
      criado_em: m.createdAt instanceof Date ? m.createdAt.toISOString() : null,
    };
  }

  /** Bounding box global [minLng, minLat, maxLng, maxLat]. */
  private computeBbox(entries: RawMeasurementEntry[]): [number, number, number, number] {
    let minLat =  Infinity, maxLat = -Infinity;
    let minLng =  Infinity, maxLng = -Infinity;

    for (const m of entries) {
      for (const c of m.coordinates) {
        const lat = c[0], lng = c[1];
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
      }
    }

    if (!isFinite(minLat)) return [0, 0, 0, 0];
    return [
      +minLng.toFixed(7),
      +minLat.toFixed(7),
      +maxLng.toFixed(7),
      +maxLat.toFixed(7),
    ];
  }
}
