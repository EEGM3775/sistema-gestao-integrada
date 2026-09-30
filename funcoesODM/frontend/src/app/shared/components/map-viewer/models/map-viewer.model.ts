/**
 * Models para o Map Viewer
 */

import * as L from 'leaflet';

export interface MapLayer {
  id: string;
  name: string;
  type: 'orthomosaic' | 'dsm' | 'dtm' | 'ndvi' | 'markers' | 'measurements';
  url?: string;
  bounds?: L.LatLngBoundsExpression;
  visible: boolean;
  opacity: number;
  color?: string;
}

export interface MapMarker {
  id: string;
  lat: number;
  lng: number;
  label?: string;
  type?: 'gcp' | 'poi' | 'annotation';
  icon?: string;
}

export interface MeasurementResult {
  type: 'distance' | 'area' | 'volume';
  value: number;
  unit: string;
  coordinates: L.LatLng[];
}

export type BasemapType = 'satellite' | 'street' | 'terrain';
export type MeasurementMode = 'distance' | 'area' | 'volume' | null;

export interface MapCoordinates {
  lat: number;
  lng: number;
}

export interface SelectedInfo {
  title: string;
  items: { label: string; value: string }[];
}
