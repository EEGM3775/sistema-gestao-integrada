/**
 * ExportShapefileService
 *
 * Gera Shapefile (ESRI .shp + .shx + .dbf + .prj) totalmente em memória
 * e empacota em .zip usando fflate.
 *
 * Referência: ESRI Shapefile Technical Description (1998)
 *   https://www.esri.com/content/dam/esrisites/sitecore-archive/Files/Pdfs/library/whitepapers/pdfs/shapefile.pdf
 *
 * Geometrias exportadas:
 *   POLYLINE (type 3) : distance, height
 *   POLYGON  (type 5) : area, volume
 *
 * Cada tipo de geometria vai para um arquivo separado dentro do .zip:
 *   medicoes_linhas.shp/shx/dbf/prj/cpg
 *   medicoes_areas.shp/shx/dbf/prj/cpg
 */

import { Injectable, inject } from '@angular/core';
import { zipSync } from 'fflate';
import proj4 from 'proj4';
import {
  ExportBaseService,
  RawMeasurementEntry,
  CoordFormat
} from './export-base.service';

// ============================================================================
// Constantes de formato
// ============================================================================

/** Definição dos campos do arquivo .dbf. */
const DBF_FIELDS = [
  { name: 'ID',        type: 'C', len: 40, dec: 0 },
  { name: 'NOME',      type: 'C', len: 80, dec: 0 },
  { name: 'TIPO',      type: 'C', len: 20, dec: 0 },
  { name: 'VALOR',     type: 'N', len: 15, dec: 3 },
  { name: 'UNIDADE',   type: 'C', len: 10, dec: 0 },
  { name: 'FONTE',     type: 'C', len: 20, dec: 0 },
  { name: 'CRIADO_EM', type: 'C', len: 20, dec: 0 },
] as const;

/** Projeção WKT — WGS84 geográfico (EPSG:4326) */
const PRJ_WGS84 =
  'GEOGCS["GCS_WGS_1984",' +
  'DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],' +
  'PRIMEM["Greenwich",0.0],' +
  'UNIT["Degree",0.0174532925199433]]';

// ============================================================================
// Service
// ============================================================================

@Injectable({ providedIn: 'root' })
export class ExportShapefileService {

  private base = inject(ExportBaseService);

  private readonly enc = new TextEncoder();

  // --------------------------------------------------------------------------
  // Ponto de entrada público
  // --------------------------------------------------------------------------

  /**
   * Constrói um ZIP contendo os Shapefiles de linhas e/ou áreas.
   * Retorna o ZIP como Uint8Array pronto para download.
   *
   * @param targetEpsg Quando fmt='utm' e há multi-fuso, força reprojeção de todos
   *   os pontos para este EPSG (ex: 32723 = UTM 23S). null = fuso nativo por ponto.
   */
  buildShapefileZip(entries: RawMeasurementEntry[], coordFormat: CoordFormat, targetEpsg: number | null = null): Uint8Array {
    const lines    = entries.filter(e => e.type === 'distance' || e.type === 'height');
    const polygons = entries.filter(e => e.type === 'area'     || e.type === 'volume');

    const files: { [path: string]: Uint8Array } = {};

    if (lines.length > 0) {
      const { shp, shx, dbf } = this.buildShapefile(lines, 3, coordFormat, targetEpsg);
      const prj = this.enc.encode(coordFormat === 'utm' ? this.buildPrjUtm(lines, targetEpsg) : PRJ_WGS84);
      files['medicoes_linhas.shp'] = shp;
      files['medicoes_linhas.shx'] = shx;
      files['medicoes_linhas.dbf'] = dbf;
      files['medicoes_linhas.prj'] = prj;
      files['medicoes_linhas.cpg'] = this.enc.encode('UTF-8');
    }
    if (polygons.length > 0) {
      const { shp, shx, dbf } = this.buildShapefile(polygons, 5, coordFormat, targetEpsg);
      const prj = this.enc.encode(coordFormat === 'utm' ? this.buildPrjUtm(polygons, targetEpsg) : PRJ_WGS84);
      files['medicoes_areas.shp'] = shp;
      files['medicoes_areas.shx'] = shx;
      files['medicoes_areas.dbf'] = dbf;
      files['medicoes_areas.prj'] = prj;
      files['medicoes_areas.cpg'] = this.enc.encode('UTF-8');
    }

    return zipSync(files, { level: 6 });
  }

  // --------------------------------------------------------------------------
  // Construção dos arquivos binários
  // --------------------------------------------------------------------------

  private buildShapefile(
    entries: RawMeasurementEntry[],
    shapeType: 3 | 5,
    fmt: CoordFormat,
    targetEpsg: number | null = null
  ): { shp: Uint8Array; shx: Uint8Array; dbf: Uint8Array } {

    // Converte coordenadas e fecha anéis de polígono se necessário
    const shapes: number[][][] = entries.map(e => {
      let pts = e.coordinates.map(c => this.toXY(c[0], c[1], fmt, targetEpsg));
      if (shapeType === 5 && pts.length >= 3) {
        const f = pts[0], l = pts[pts.length - 1];
        if (f[0] !== l[0] || f[1] !== l[1]) pts = [...pts, f];
      }
      return pts;
    });

    // Bounding box global
    let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
    for (const pts of shapes) {
      for (const [x, y] of pts) {
        xMin = Math.min(xMin, x); yMin = Math.min(yMin, y);
        xMax = Math.max(xMax, x); yMax = Math.max(yMax, y);
      }
    }

    // Conteúdo de cada record
    const recBufs = shapes.map(pts => this.buildRecordContent(shapeType, pts));

    // .shp
    const shpBodyLen = recBufs.reduce((acc, b) => acc + 8 + b.byteLength, 0);
    const shpBuf = new ArrayBuffer(100 + shpBodyLen);
    const sv = new DataView(shpBuf);
    this.writeFileHeader(sv, shapeType, (100 + shpBodyLen) / 2, xMin, yMin, xMax, yMax);

    // .shx
    const shxBuf = new ArrayBuffer(100 + recBufs.length * 8);
    const xv = new DataView(shxBuf);
    this.writeFileHeader(xv, shapeType, (100 + recBufs.length * 8) / 2, xMin, yMin, xMax, yMax);

    let shpOff = 100, shxOff = 100;
    for (let i = 0; i < recBufs.length; i++) {
      const rec  = recBufs[i];
      const clen = rec.byteLength / 2; // content length in 16-bit words

      // SHX: offset (em words de 16 bits) e content length (em words de 16 bits)
      xv.setInt32(shxOff,     shpOff / 2, false);
      xv.setInt32(shxOff + 4, clen,       false);
      shxOff += 8;

      // SHP: record header (record number 1-based, content length) — ambos big-endian
      sv.setInt32(shpOff,     i + 1, false);
      sv.setInt32(shpOff + 4, clen,  false);
      shpOff += 8;

      // SHP: record content
      new Uint8Array(shpBuf, shpOff, rec.byteLength).set(rec);
      shpOff += rec.byteLength;
    }

    return {
      shp: new Uint8Array(shpBuf),
      shx: new Uint8Array(shxBuf),
      dbf: this.buildDbf(entries)
    };
  }

  /** Constrói o conteúdo de um record de um POLYLINE ou POLYGON. */
  private buildRecordContent(shapeType: 3 | 5, pts: number[][]): Uint8Array {
    // 4 (type) + 32 (bbox) + 4 (numParts) + 4 (numPoints) + 4 (parts[0]) + 16*n (points)
    const buf = new ArrayBuffer(4 + 32 + 4 + 4 + 4 + pts.length * 16);
    const v   = new DataView(buf);
    let off   = 0;

    const xMin = Math.min(...pts.map(p => p[0]));
    const yMin = Math.min(...pts.map(p => p[1]));
    const xMax = Math.max(...pts.map(p => p[0]));
    const yMax = Math.max(...pts.map(p => p[1]));

    v.setInt32(off, shapeType, true); off += 4;
    v.setFloat64(off, xMin,    true); off += 8;
    v.setFloat64(off, yMin,    true); off += 8;
    v.setFloat64(off, xMax,    true); off += 8;
    v.setFloat64(off, yMax,    true); off += 8;
    v.setInt32(off, 1,         true); off += 4; // numParts
    v.setInt32(off, pts.length,true); off += 4; // numPoints
    v.setInt32(off, 0,         true); off += 4; // parts[0] = 0

    for (const [x, y] of pts) {
      v.setFloat64(off, x, true); off += 8;
      v.setFloat64(off, y, true); off += 8;
    }
    return new Uint8Array(buf);
  }

  /** Escreve o cabeçalho de 100 bytes de um arquivo .shp ou .shx. */
  private writeFileHeader(
    v: DataView, shapeType: number, fileLenWords: number,
    xMin: number, yMin: number, xMax: number, yMax: number
  ): void {
    v.setInt32(0,  9994,          false); // file code (BE)
    v.setInt32(24, fileLenWords,  false); // file length em words de 16 bits (BE)
    v.setInt32(28, 1000,          true);  // version (LE)
    v.setInt32(32, shapeType,     true);  // shape type (LE)
    v.setFloat64(36, xMin,        true);  // Xmin (LE)
    v.setFloat64(44, yMin,        true);  // Ymin (LE)
    v.setFloat64(52, xMax,        true);  // Xmax (LE)
    v.setFloat64(60, yMax,        true);  // Ymax (LE)
    // bytes 68-99: Zmin, Zmax, Mmin, Mmax — todos 0 (buffer já inicializado com zeros)
  }

  // --------------------------------------------------------------------------
  // DBF (dBASE III)
  // --------------------------------------------------------------------------

  private buildDbf(entries: RawMeasurementEntry[]): Uint8Array {
    const recordLen  = 1 + DBF_FIELDS.reduce((s, f) => s + f.len, 0); // flag + fields
    const headerSize = 32 + DBF_FIELDS.length * 32 + 1;               // cabeçalho + descritores + 0x0D
    const totalSize  = headerSize + entries.length * recordLen + 1;    // +1 EOF 0x1A

    const buf = new Uint8Array(totalSize); // inicializado com zeros
    const v   = new DataView(buf.buffer);
    const now = new Date();
    let off   = 0;

    // ---- Cabeçalho (32 bytes) ----
    buf[off++] = 3;                          // versão dBASE III
    buf[off++] = now.getFullYear() - 1900;   // ano (aaaa - 1900)
    buf[off++] = now.getMonth() + 1;         // mês
    buf[off++] = now.getDate();              // dia
    v.setInt32(off, entries.length, true); off += 4; // número de registros
    v.setInt16(off, headerSize,     true); off += 2; // bytes no cabeçalho
    v.setInt16(off, recordLen,      true); off += 2; // bytes por registro
    off += 20;                                       // reservado (zeros)

    // ---- Descritores de campo (32 bytes cada) ----
    for (const field of DBF_FIELDS) {
      const nameEnc = this.enc.encode(field.name);
      buf.set(nameEnc.slice(0, 11), off); off += 11; // nome (max 10 chars + null)
      buf[off++] = field.type.charCodeAt(0);          // tipo
      off += 4;                                       // reservado
      buf[off++] = field.len;                         // comprimento do campo
      buf[off++] = field.dec;                         // casas decimais
      off += 14;                                      // reservado
    }
    buf[off++] = 0x0D; // terminador do cabeçalho

    // ---- Registros ----
    for (const entry of entries) {
      buf[off++] = 0x20; // flag de não-deletado

      const createdStr =
        entry.createdAt instanceof Date
          ? entry.createdAt.toISOString().slice(0, 19)
          : String(entry.createdAt).slice(0, 19);

      const rawValues = [
        entry.id,
        entry.name,
        entry.type,
        entry.value.toFixed(3),
        entry.unit,
        entry.dataSource,
        createdStr,
      ];

      for (let i = 0; i < DBF_FIELDS.length; i++) {
        const field = DBF_FIELDS[i];
        const raw   = rawValues[i] ?? '';

        // Numérico: justificado à direita com espaços
        // Caractere: justificado à esquerda com espaços
        const padded = field.type === 'N'
          ? raw.padStart(field.len, ' ')
          : raw.padEnd(field.len,   ' ');

        const encoded = this.enc.encode(padded.slice(0, field.len));
        const cell    = new Uint8Array(field.len); // garante comprimento exato
        cell.set(encoded.slice(0, field.len));
        buf.set(cell, off);
        off += field.len;
      }
    }

    buf[off] = 0x1A; // EOF marker
    return buf;
  }

  // --------------------------------------------------------------------------
  // Auxiliares
  // --------------------------------------------------------------------------

  /** Converte (lat, lng) para (X, Y) conforme o CRS escolhido.
   *  Quando targetEpsg é informado, reprojecta todos os pontos para aquele fuso UTM.
   */
  private toXY(lat: number, lng: number, fmt: CoordFormat, targetEpsg: number | null = null): [number, number] {
    if (fmt === 'utm') {
      if (targetEpsg !== null) {
        // Reprojetar para o fuso alvo escolhido pelo usuário no popup multi-fuso
        const zone    = targetEpsg % 100;
        const isSouth = targetEpsg >= 32700;
        const utmProj = `+proj=utm +zone=${zone}${isSouth ? ' +south' : ''} +datum=WGS84 +units=m +no_defs`;
        const [e, n]  = proj4('EPSG:4326', utmProj, [lng, lat]);
        return [e, n];
      }
      const { easting, northing } = this.base.wgs84ToUtm(lat, lng);
      return [easting, northing];
    }
    return [lng, lat]; // WGS84: X = Longitude, Y = Latitude
  }

  /**
   * Gera string WKT para .prj.
   * Quando targetEpsg é informado, usa aquele fuso — senão detecta pelo primeiro ponto.
   */
  private buildPrjUtm(entries: RawMeasurementEntry[], targetEpsg: number | null = null): string {
    let zone: number;
    let isSouth: boolean;

    if (targetEpsg !== null) {
      zone    = targetEpsg % 100;
      isSouth = targetEpsg >= 32700;
    } else {
      const firstCoord = entries[0]?.coordinates[0];
      if (!firstCoord) return PRJ_WGS84;
      const u = this.base.wgs84ToUtm(firstCoord[0], firstCoord[1]);
      zone    = u.zone;
      isSouth = u.band < 'N';
    }
    const cm            = (zone - 1) * 6 - 180 + 3;
    const falseNorthing = isSouth ? 10_000_000.0 : 0.0;
    const ns            = isSouth ? 'S' : 'N';

    return `PROJCS["WGS_1984_UTM_Zone_${zone}${ns}",` +
           `GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",` +
           `SPHEROID["WGS_1984",6378137.0,298.257223563]],` +
           `PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],` +
           `PROJECTION["Transverse_Mercator"],` +
           `PARAMETER["False_Easting",500000.0],` +
           `PARAMETER["False_Northing",${falseNorthing}],` +
           `PARAMETER["Central_Meridian",${cm}.0],` +
           `PARAMETER["Scale_Factor",0.9996],` +
           `PARAMETER["Latitude_Of_Origin",0.0],` +
           `UNIT["Meter",1.0]]`;
  }
}
