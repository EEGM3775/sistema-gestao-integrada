/**
 * Types compartilhados entre MeasurementTab e sub-componentes.
 * Independente de Leaflet ou serviços externos.
 */

/** Medição persistida / exibida no painel lateral */
export interface MeasurementData {
  id: string;
  name: string;
  type: 'distance' | 'area' | 'volume' | 'height' | 'elevation_profile';
  value: number;
  unit: string;
  dataSource: string;
  /** [[lat, lng, elev?], ...] — elevação opcional como 3º elemento */
  coordinates: number[][];
  createdAt: Date;
  /** Estado de visibilidade persistido no backend (padrão: true) */
  visible: boolean;
}

/** Ferramenta de desenho ativa (null = nenhuma) */
export type ActiveTool = 'distance' | 'area' | 'volume' | 'height' | 'elevation_profile' | null;
