/**
 * Modelos de dados para o Editor de GCP.
 *
 * GcpPoint  — ponto de controle com coordenadas geograficas (GNSS de campo).
 * GcpMark   — marcacao de um ponto GCP dentro de uma imagem especifica.
 */

/** Ponto de controle (referencia geografica de campo). */
export interface GcpPoint {
  /** Identificador unico gerado internamente (ex: "gcp-0"). */
  id: string;
  /** Rotulo exibido ao usuario (ex: "GCP-01"). */
  label: string;
  /** Latitude WGS84. */
  lat: number;
  /** Longitude WGS84. */
  lng: number;
  /** Altitude em metros. */
  alt: number;
}

/**
 * Marcacao de um GcpPoint em uma foto especifica.
 * pixelX/pixelY sao coordenadas na resolucao natural da imagem original.
 * pctX/pctY sao as coordenadas percentuais (0-1) na imagem exibida — usadas
 * apenas para posicionar o marcador visual na tela.
 */
export interface GcpMark {
  gcpId: string;
  imageId: number;
  /** Nome original do arquivo (NodeODM usa este nome para correlacionar). */
  imageOriginalFilename: string;
  /** Pixel X na resolucao NATURAL da imagem. */
  pixelX: number;
  /** Pixel Y na resolucao NATURAL da imagem. */
  pixelY: number;
  /** Posicao percentual X (0-1) dentro da imagem exibida — para overlay visual. */
  pctX: number;
  /** Posicao percentual Y (0-1) dentro da imagem exibida — para overlay visual. */
  pctY: number;
}
