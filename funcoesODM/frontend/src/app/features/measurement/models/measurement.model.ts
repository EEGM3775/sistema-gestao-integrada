/**
 * Models para Sistema de Medição
 * 
 * Define tipos, enums e interfaces para medições em projetos de fotogrametria
 */

import * as L from 'leaflet';

// ============================================================================
// ENUMS
// ============================================================================

/**
 * Tipo de medição
 */
export enum MeasurementType {
  DISTANCE = 'distance',        // Distância linear (2D/3D)
  AREA = 'area',                // Área de polígono
  VOLUME = 'volume',            // Volume entre superfícies
  ELEVATION = 'elevation',      // Perfil de elevação
  SLOPE = 'slope',              // Inclinação
  PERIMETER = 'perimeter',      // Perímetro
  ANGLE = 'angle',              // Ângulo entre linhas
  HEIGHT = 'height'             // Altura de objeto
}

/**
 * Unidades de medida
 */
export enum MeasurementUnit {
  // Distância
  METERS = 'm',
  KILOMETERS = 'km',
  FEET = 'ft',
  MILES = 'mi',
  
  // Área
  SQUARE_METERS = 'm²',
  SQUARE_KILOMETERS = 'km²',
  HECTARES = 'ha',
  SQUARE_FEET = 'ft²',
  ACRES = 'ac',
  
  // Volume
  CUBIC_METERS = 'm³',
  CUBIC_FEET = 'ft³',
  LITERS = 'L',
  
  // Ângulo
  DEGREES = '°',
  RADIANS = 'rad',
  PERCENT = '%'
}

/**
 * Modo de visualização da medição
 */
export enum MeasurementMode {
  ORTHOPHOTO = 'orthophoto',    // Medição 2D em ortofoto
  DEM = 'dem',                  // Medição em modelo digital de elevação
  POINTCLOUD = 'pointcloud',    // Medição 3D em nuvem de pontos
  MESH = 'mesh'                 // Medição 3D em mesh
}

/**
 * Status da medição
 */
export enum MeasurementStatus {
  DRAFT = 'draft',              // Em edição
  COMPLETED = 'completed',      // Finalizada
  EXPORTED = 'exported',        // Exportada
  ARCHIVED = 'archived'         // Arquivada
}

// ============================================================================
// INTERFACES
// ============================================================================

/**
 * Ponto de medição (2D ou 3D)
 */
export interface MeasurementPoint {
  id: string;
  lat: number;
  lng: number;
  elevation?: number;           // Z (metros)
  label?: string;
  timestamp: Date;
}

/**
 * Geometria da medição
 */
export interface MeasurementGeometry {
  type: 'Point' | 'LineString' | 'Polygon' | 'MultiPoint';
  coordinates: number[][];      // [lng, lat, z?]
  bounds?: L.LatLngBounds;
}

/**
 * Resultado de medição
 */
export interface MeasurementResult {
  value: number;
  unit: MeasurementUnit;
  precision: number;            // Casas decimais
  displayValue: string;         // Formatado para exibição
  metadata?: {
    method?: string;            // Método de cálculo
    accuracy?: number;          // Precisão estimada
    error?: number;             // Margem de erro
  };
}

/**
 * Objeto de medição completo
 */
export interface Measurement {
  id: string;
  projectId: number;
  name: string;
  description?: string;
  type: MeasurementType;
  mode: MeasurementMode;
  status: MeasurementStatus;
  
  // Geometria
  geometry: MeasurementGeometry;
  points: MeasurementPoint[];
  
  // Resultados
  result: MeasurementResult;
  secondaryResults?: MeasurementResult[]; // Ex: perímetro junto com área
  
  // Metadata
  color?: string;
  style?: MeasurementStyle;
  createdAt: Date;
  updatedAt: Date;
  createdBy?: string;
  
  // Configurações específicas
  options?: MeasurementOptions;
  
  // Exportação
  exported?: {
    format: 'PDF' | 'CSV' | 'DXF' | 'GeoJSON' | 'KML';
    path?: string;
    timestamp: Date;
  }[];
}

/**
 * Estilo de visualização da medição
 */
export interface MeasurementStyle {
  strokeColor: string;
  strokeWidth: number;
  strokeOpacity: number;
  fillColor?: string;
  fillOpacity?: number;
  dashArray?: string;
  pointRadius?: number;
  labelSize?: number;
  labelColor?: string;
}

/**
 * Opções de medição
 */
export interface MeasurementOptions {
  // Geral
  unit: MeasurementUnit;
  precision: number;
  includeElevation: boolean;
  
  // Volume
  baseElevation?: number;       // Referência para cálculo de volume
  fillOrCut?: 'fill' | 'cut' | 'both';
  
  // Perfil
  sampleInterval?: number;      // Intervalo de amostragem (metros)
  profileType?: 'terrain' | 'surface';
  
  // Visualização
  showLabels: boolean;
  showVertices: boolean;
  showGrid: boolean;
  snapToTerrain: boolean;
}

/**
 * Configurações globais de medição
 */
export interface MeasurementSettings {
  defaultUnit: MeasurementUnit;
  defaultPrecision: number;
  defaultStyle: MeasurementStyle;
  snapTolerance: number;        // Pixels
  minSegmentLength: number;     // Metros
  maxMeasurements: number;      // Limite de medições por projeto
  autoSave: boolean;
  exportDefaults: {
    format: 'PDF' | 'CSV' | 'DXF';
    includeThumbnail: boolean;
    includeCoordinates: boolean;
  };
}

/**
 * Dados de perfil de elevação
 */
export interface ElevationProfile {
  measurementId: string;
  points: {
    distance: number;           // Distância acumulada (m)
    elevation: number;          // Elevação (m)
    lat: number;
    lng: number;
    slope?: number;             // Inclinação (%)
  }[];
  stats: {
    totalDistance: number;
    minElevation: number;
    maxElevation: number;
    elevationGain: number;      // Ganho total
    elevationLoss: number;      // Perda total
    averageSlope: number;
    maxSlope: number;
  };
}

/**
 * Dados de cálculo de volume
 */
export interface VolumeCalculation {
  measurementId: string;
  method: 'grid' | 'triangulation' | 'contour';
  baseElevation: number;
  cutVolume: number;            // Volume de corte (m³)
  fillVolume: number;           // Volume de aterro (m³)
  netVolume: number;            // Volume líquido
  area: number;                 // Área base (m²)
  gridResolution?: number;      // Resolução da malha (m)
  accuracy?: number;            // Precisão estimada
}

/**
 * Filtros para listagem de medições
 */
export interface MeasurementFilters {
  projectId?: number;
  type?: MeasurementType[];
  mode?: MeasurementMode[];
  status?: MeasurementStatus[];
  dateFrom?: Date;
  dateTo?: Date;
  createdBy?: string;
  searchTerm?: string;
}

/**
 * Estatísticas de medições
 */
export interface MeasurementStats {
  total: number;
  byType: Record<MeasurementType, number>;
  byStatus: Record<MeasurementStatus, number>;
  totalDistance: number;        // Soma de todas as distâncias
  totalArea: number;            // Soma de todas as áreas
  totalVolume: number;          // Soma de todos os volumes
}

// ============================================================================
// DEFAULTS
// ============================================================================

export const DEFAULT_MEASUREMENT_STYLE: MeasurementStyle = {
  strokeColor: '#FF6B6B',
  strokeWidth: 3,
  strokeOpacity: 0.8,
  fillColor: '#FF6B6B',
  fillOpacity: 0.2,
  pointRadius: 6,
  labelSize: 12,
  labelColor: '#FFFFFF'
};

export const DEFAULT_MEASUREMENT_OPTIONS: MeasurementOptions = {
  unit: MeasurementUnit.METERS,
  precision: 2,
  includeElevation: true,
  showLabels: true,
  showVertices: true,
  showGrid: false,
  snapToTerrain: true
};

export const DEFAULT_MEASUREMENT_SETTINGS: MeasurementSettings = {
  defaultUnit: MeasurementUnit.METERS,
  defaultPrecision: 2,
  defaultStyle: DEFAULT_MEASUREMENT_STYLE,
  snapTolerance: 10,
  minSegmentLength: 0.1,
  maxMeasurements: 1000,
  autoSave: true,
  exportDefaults: {
    format: 'PDF',
    includeThumbnail: true,
    includeCoordinates: true
  }
};
