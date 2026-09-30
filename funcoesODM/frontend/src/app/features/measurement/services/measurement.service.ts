/**
 * Service Core de Medição
 * 
 * Responsabilidades:
 * - Gerenciar medições (CRUD)
 * - Executar cálculos geométricos
 * - Comunicação com backend
 * - Coordenar histórico e exportação
 */

import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, map, catchError, of } from 'rxjs';
import * as L from 'leaflet';

import {
  Measurement,
  MeasurementType,
  MeasurementPoint,
  MeasurementResult,
  MeasurementUnit,
  MeasurementOptions,
  MeasurementGeometry,
  MeasurementStatus,
  MeasurementMode,
  ElevationProfile,
  VolumeCalculation,
  DEFAULT_MEASUREMENT_OPTIONS
} from '../models/measurement.model';

@Injectable()
export class MeasurementService {
  private readonly API_URL = '/api/v1/measurements';
  
  // State
  private measurementsSubject = new BehaviorSubject<Measurement[]>([]);
  measurements$ = this.measurementsSubject.asObservable();
  
  activeMeasurement = signal<Measurement | null>(null);
  isDrawing = signal<boolean>(false);
  currentMode = signal<MeasurementType | null>(null);
  
  // Computed
  measurementCount = computed(() => this.measurementsSubject.value.length);

  constructor(private http: HttpClient) {}

  // ============================================================================
  // CRUD OPERATIONS
  // ============================================================================

  /**
   * Lista medições de um projeto
   */
  getMeasurements(projectId: number): Observable<Measurement[]> {
    return this.http.get<Measurement[]>(`${this.API_URL}/project/${projectId}`).pipe(
      map(measurements => {
        this.measurementsSubject.next(measurements);
        return measurements;
      }),
      catchError(() => of([]))
    );
  }

  /**
   * Obtém uma medição específica
   */
  getMeasurement(id: string): Observable<Measurement | null> {
    return this.http.get<Measurement>(`${this.API_URL}/${id}`).pipe(
      catchError(() => of(null))
    );
  }

  /**
   * Cria nova medição
   */
  createMeasurement(measurement: Partial<Measurement>): Observable<Measurement> {
    return this.http.post<Measurement>(this.API_URL, measurement).pipe(
      map(created => {
        const current = this.measurementsSubject.value;
        this.measurementsSubject.next([...current, created]);
        return created;
      })
    );
  }

  /**
   * Atualiza medição existente
   */
  updateMeasurement(id: string, updates: Partial<Measurement>): Observable<Measurement> {
    return this.http.put<Measurement>(`${this.API_URL}/${id}`, updates).pipe(
      map(updated => {
        const current = this.measurementsSubject.value;
        const index = current.findIndex(m => m.id === id);
        if (index !== -1) {
          current[index] = updated;
          this.measurementsSubject.next([...current]);
        }
        return updated;
      })
    );
  }

  /**
   * Deleta medição
   */
  deleteMeasurement(id: string): Observable<boolean> {
    return this.http.delete<void>(`${this.API_URL}/${id}`).pipe(
      map(() => {
        const current = this.measurementsSubject.value;
        this.measurementsSubject.next(current.filter(m => m.id !== id));
        return true;
      }),
      catchError(() => of(false))
    );
  }

  // ============================================================================
  // MEASUREMENT CALCULATIONS
  // ============================================================================

  /**
   * Calcula distância entre pontos (com elevação se disponível)
   */
  calculateDistance(points: MeasurementPoint[], unit: MeasurementUnit = MeasurementUnit.METERS): MeasurementResult {
    if (points.length < 2) {
      return this.createEmptyResult(unit);
    }

    let totalDistance = 0;
    for (let i = 0; i < points.length - 1; i++) {
      const p1 = points[i];
      const p2 = points[i + 1];
      
      // Distância 2D usando Haversine
      const d2D = this.haversineDistance(p1.lat, p1.lng, p2.lat, p2.lng);
      
      // Se tem elevação, calcula distância 3D
      if (p1.elevation !== undefined && p2.elevation !== undefined) {
        const dZ = Math.abs(p2.elevation - p1.elevation);
        totalDistance += Math.sqrt(d2D * d2D + dZ * dZ);
      } else {
        totalDistance += d2D;
      }
    }

    const converted = this.convertDistance(totalDistance, unit);
    return {
      value: converted,
      unit,
      precision: 2,
      displayValue: `${converted.toFixed(2)} ${unit}`
    };
  }

  /**
   * Calcula área de polígono (método esférico)
   */
  calculateArea(points: MeasurementPoint[], unit: MeasurementUnit = MeasurementUnit.SQUARE_METERS): MeasurementResult {
    if (points.length < 3) {
      return this.createEmptyResult(unit);
    }

    // Converte para LatLng
    const latlngs = points.map(p => L.latLng(p.lat, p.lng));
    
    // Área em m² usando fórmula esférica
    const areaM2 = this.sphericalPolygonArea(latlngs);
    
    const converted = this.convertArea(areaM2, unit);
    return {
      value: converted,
      unit,
      precision: 2,
      displayValue: `${converted.toFixed(2)} ${unit}`
    };
  }

  /**
   * Calcula volume entre superfície e plano base
   */
  calculateVolume(
    points: MeasurementPoint[],
    baseElevation: number,
    options?: { gridResolution?: number }
  ): Observable<VolumeCalculation> {
    // Em produção, isso seria feito no backend com DEM
    // Aqui simulamos o cálculo
    
    const area = this.calculateArea(points).value;
    const avgElevation = points.reduce((sum, p) => sum + (p.elevation || 0), 0) / points.length;
    const heightDiff = avgElevation - baseElevation;
    const volume = area * heightDiff;

    return of({
      measurementId: crypto.randomUUID(),
      method: 'grid',
      baseElevation,
      cutVolume: heightDiff > 0 ? 0 : Math.abs(volume),
      fillVolume: heightDiff > 0 ? volume : 0,
      netVolume: volume,
      area,
      gridResolution: options?.gridResolution || 1.0,
      accuracy: 0.95
    });
  }

  /**
   * Gera perfil de elevação ao longo de linha
   */
  generateElevationProfile(
    points: MeasurementPoint[],
    sampleInterval: number = 1.0
  ): Observable<ElevationProfile> {
    // Em produção, isso seria feito no backend com DEM
    // Aqui simulamos o perfil
    
    const profilePoints = [];
    let cumulativeDistance = 0;
    let elevationGain = 0;
    let elevationLoss = 0;
    let minElev = Infinity;
    let maxElev = -Infinity;

    for (let i = 0; i < points.length; i++) {
      const point = points[i];
      const elevation = point.elevation || 0;
      
      if (i > 0) {
        const prevPoint = points[i - 1];
        const distance = this.haversineDistance(
          prevPoint.lat, prevPoint.lng,
          point.lat, point.lng
        );
        cumulativeDistance += distance;
        
        const elevDiff = elevation - (prevPoint.elevation || 0);
        if (elevDiff > 0) elevationGain += elevDiff;
        else elevationLoss += Math.abs(elevDiff);
      }
      
      minElev = Math.min(minElev, elevation);
      maxElev = Math.max(maxElev, elevation);
      
      const slope = i > 0 
        ? ((elevation - (points[i-1].elevation || 0)) / 
           this.haversineDistance(points[i-1].lat, points[i-1].lng, point.lat, point.lng)) * 100
        : 0;
      
      profilePoints.push({
        distance: cumulativeDistance,
        elevation,
        lat: point.lat,
        lng: point.lng,
        slope
      });
    }

    return of({
      measurementId: crypto.randomUUID(),
      points: profilePoints,
      stats: {
        totalDistance: cumulativeDistance,
        minElevation: minElev,
        maxElevation: maxElev,
        elevationGain,
        elevationLoss,
        averageSlope: profilePoints.reduce((sum, p) => sum + (p.slope || 0), 0) / profilePoints.length,
        maxSlope: Math.max(...profilePoints.map(p => Math.abs(p.slope || 0)))
      }
    });
  }

  // ============================================================================
  // GEOMETRY HELPERS
  // ============================================================================

  /**
   * Distância geodésica Vincenty no elipsoide WGS84 (precisão ~0,06 mm).
   * Substitui Haversine (esfera R=6371000) que introduzia erro direcional de
   * até 0,51% em segmentos N-S em latitudes tropicais (raio meridional WGS84
   * em lat=-13° é 6.338.653 m, não 6.371.000 m).
   */
  private haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
    const a = 6_378_137.0;           // semi-eixo maior WGS84 (m)
    const b = 6_356_752.314_245;     // semi-eixo menor WGS84 (m)
    const f = 1 / 298.257_223_563;  // achatamento WGS84

    const φ1 = lat1 * Math.PI / 180;
    const φ2 = lat2 * Math.PI / 180;
    const L  = (lng2 - lng1) * Math.PI / 180;

    const tanU1 = (1 - f) * Math.tan(φ1);  const cosU1 = 1 / Math.sqrt(1 + tanU1 * tanU1);  const sinU1 = tanU1 * cosU1;
    const tanU2 = (1 - f) * Math.tan(φ2);  const cosU2 = 1 / Math.sqrt(1 + tanU2 * tanU2);  const sinU2 = tanU2 * cosU2;

    let λ = L;
    let sinλ = 0, cosλ = 0, sinSigma = 0, cosSigma = 0, sigma = 0;
    let sinAlpha = 0, cos2Alpha = 0, cos2SigmaM = 0, C = 0;
    let iter = 0;
    do {
      const λPrev = λ;
      sinλ = Math.sin(λ);  cosλ = Math.cos(λ);
      const t1 = cosU2 * sinλ;
      const t2 = cosU1 * sinU2 - sinU1 * cosU2 * cosλ;
      sinSigma = Math.sqrt(t1 * t1 + t2 * t2);
      if (sinSigma === 0) return 0; // pontos coincidentes
      cosSigma    = sinU1 * sinU2 + cosU1 * cosU2 * cosλ;
      sigma       = Math.atan2(sinSigma, cosSigma);
      sinAlpha    = cosU1 * cosU2 * sinλ / sinSigma;
      cos2Alpha   = 1 - sinAlpha * sinAlpha;
      cos2SigmaM  = cos2Alpha !== 0 ? cosSigma - 2 * sinU1 * sinU2 / cos2Alpha : 0;
      C = f / 16 * cos2Alpha * (4 + f * (4 - 3 * cos2Alpha));
      λ = L + (1 - C) * f * sinAlpha * (
        sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM))
      );
      if (Math.abs(λ - λPrev) <= 1e-12) break;
    } while (++iter < 100);

    const u2 = cos2Alpha * (a * a - b * b) / (b * b);
    const A  = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)));
    const B  = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)));
    const Δσ = B * sinSigma * (
      cos2SigmaM + B / 4 * (
        cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM) -
        B / 6 * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) * (-3 + 4 * cos2SigmaM * cos2SigmaM)
      )
    );
    return b * A * (sigma - Δσ);
  }

  /**
   * Área de polígono geodésico (em m²) usando raio médio de Gauss WGS84.
   *
   * Substitui R=6371000 fixo (esfera) pelo raio R_gauss = sqrt(M*N) calculado
   * na latitude média do polígono. Em lat=-13° R_gauss≈6.358.902 m vs
   * 6.371.000 m da esfera → erro sistemático de 0,457% eliminado.
   *
   * Fórmula de área: igual à fórmula esférica de Girard, mas com R local.
   */
  private sphericalPolygonArea(latlngs: L.LatLng[]): number {
    // Raio médio de Gauss WGS84 na latitude média do polígono
    const a   = 6_378_137.0;
    const e2  = 0.006_694_379_990_14; // e² WGS84
    const latMeanRad = latlngs.reduce((s, p) => s + p.lat, 0) / latlngs.length * Math.PI / 180;
    const sin2 = Math.sin(latMeanRad) ** 2;
    const denom = 1 - e2 * sin2;
    const M = a * (1 - e2) / Math.pow(denom, 1.5); // raio meridional
    const N = a / Math.sqrt(denom);                 // raio normal
    const R = Math.sqrt(M * N);                     // raio médio de Gauss

    let area = 0;
    const n = latlngs.length;
    for (let i = 0; i < n; i++) {
      const j   = (i + 1) % n;
      const lat1 = this.toRad(latlngs[i].lat);
      const lat2 = this.toRad(latlngs[j].lat);
      const lng1 = this.toRad(latlngs[i].lng);
      const lng2 = this.toRad(latlngs[j].lng);
      area += (lng2 - lng1) * (2 + Math.sin(lat1) + Math.sin(lat2));
    }
    return Math.abs(area * R * R / 2);
  }

  /**
   * Converte graus para radianos
   */
  private toRad(degrees: number): number {
    return degrees * Math.PI / 180;
  }

  // ============================================================================
  // UNIT CONVERSIONS
  // ============================================================================

  /**
   * Converte distância para unidade especificada
   */
  private convertDistance(meters: number, toUnit: MeasurementUnit): number {
    switch (toUnit) {
      case MeasurementUnit.METERS: return meters;
      case MeasurementUnit.KILOMETERS: return meters / 1000;
      case MeasurementUnit.FEET: return meters * 3.28084;
      case MeasurementUnit.MILES: return meters / 1609.34;
      default: return meters;
    }
  }

  /**
   * Converte área para unidade especificada
   */
  private convertArea(squareMeters: number, toUnit: MeasurementUnit): number {
    switch (toUnit) {
      case MeasurementUnit.SQUARE_METERS: return squareMeters;
      case MeasurementUnit.SQUARE_KILOMETERS: return squareMeters / 1000000;
      case MeasurementUnit.HECTARES: return squareMeters / 10000;
      case MeasurementUnit.SQUARE_FEET: return squareMeters * 10.7639;
      case MeasurementUnit.ACRES: return squareMeters / 4046.86;
      default: return squareMeters;
    }
  }

  /**
   * Cria resultado vazio
   */
  private createEmptyResult(unit: MeasurementUnit): MeasurementResult {
    return {
      value: 0,
      unit,
      precision: 2,
      displayValue: `0.00 ${unit}`
    };
  }

  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  /**
   * Inicia novo desenho de medição
   */
  startMeasurement(type: MeasurementType, mode: MeasurementMode): void {
    this.isDrawing.set(true);
    this.currentMode.set(type);
    
    // Criar medição draft
    this.activeMeasurement.set({
      id: crypto.randomUUID(),
      projectId: 0, // Será definido no contexto
      name: `${type} ${new Date().toLocaleString()}`,
      type,
      mode,
      status: MeasurementStatus.DRAFT,
      geometry: {
        type: this.getGeometryType(type),
        coordinates: [],
        bounds: undefined
      },
      points: [],
      result: this.createEmptyResult(MeasurementUnit.METERS),
      createdAt: new Date(),
      updatedAt: new Date(),
      options: { ...DEFAULT_MEASUREMENT_OPTIONS }
    });
  }

  /**
   * Adiciona ponto à medição ativa
   */
  addPoint(point: MeasurementPoint): void {
    const measurement = this.activeMeasurement();
    if (!measurement) return;

    measurement.points.push(point);
    measurement.updatedAt = new Date();
    
    // Recalcular resultado
    this.updateMeasurementResult(measurement);
    
    this.activeMeasurement.set({ ...measurement });
  }

  /**
   * Finaliza medição
   */
  completeMeasurement(): Observable<Measurement> | null {
    const measurement = this.activeMeasurement();
    if (!measurement) return null;

    measurement.status = MeasurementStatus.COMPLETED;
    measurement.updatedAt = new Date();
    
    this.isDrawing.set(false);
    this.currentMode.set(null);
    this.activeMeasurement.set(null);
    
    return this.createMeasurement(measurement);
  }

  /**
   * Cancela medição
   */
  cancelMeasurement(): void {
    this.isDrawing.set(false);
    this.currentMode.set(null);
    this.activeMeasurement.set(null);
  }

  /**
   * Atualiza resultado da medição
   */
  private updateMeasurementResult(measurement: Measurement): void {
    const { type, points, options } = measurement;
    const unit = options?.unit || MeasurementUnit.METERS;

    switch (type) {
      case MeasurementType.DISTANCE:
        measurement.result = this.calculateDistance(points, unit);
        break;
      case MeasurementType.AREA:
        measurement.result = this.calculateArea(points, unit);
        break;
      case MeasurementType.PERIMETER:
        measurement.result = this.calculateDistance([...points, points[0]], unit);
        break;
      // Outros tipos requerem cálculos assíncronos (backend)
    }
  }

  /**
   * Determina tipo de geometria baseado no tipo de medição
   */
  private getGeometryType(type: MeasurementType): 'Point' | 'LineString' | 'Polygon' | 'MultiPoint' {
    switch (type) {
      case MeasurementType.DISTANCE:
      case MeasurementType.ELEVATION:
        return 'LineString';
      case MeasurementType.AREA:
      case MeasurementType.VOLUME:
        return 'Polygon';
      case MeasurementType.HEIGHT:
        return 'Point';
      default:
        return 'LineString';
    }
  }
}
