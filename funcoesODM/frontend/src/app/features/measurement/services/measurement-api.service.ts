/**
 * ============================================================================
 * MEASUREMENT API SERVICE
 * ============================================================================
 *
 * Client HTTP para persistir medições no backend Java.
 *
 * Endpoints:
 *   GET    /api/v1/projects/{projectId}/chunks/{chunkId}/measurements
 *   POST   /api/v1/projects/{projectId}/chunks/{chunkId}/measurements
 *   DELETE /api/v1/projects/{projectId}/measurements/{measurementId}
 */

import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { MeasurementData } from '../../projects/components/measurement-tab/measurement-tab.component';

// ─── DTOs que espelham o backend ────────────────────────────────────────────

export interface MeasurementApiDto {
  id: number;
  projectId: number;
  chunkId: number | null;
  name: string;
  type: string;
  value: number;
  unit: string;
  dataSource: string;
  coordinates: number[][];
  visible: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface MeasurementCreateRequest {
  name: string;
  type: string;
  value: number;
  unit: string;
  dataSource: string;
  coordinates: number[][];
}

// ─── Conversão API ↔ Frontend ───────────────────────────────────────────────

function apiDtoToMeasurementData(dto: MeasurementApiDto): MeasurementData {
  return {
    id: String(dto.id),          // backend Long → frontend string
    name: dto.name,
    type: dto.type as MeasurementData['type'],
    value: dto.value,
    unit: dto.unit,
    dataSource: dto.dataSource,
    coordinates: dto.coordinates ?? [],
    visible: dto.visible !== false,
    createdAt: new Date(dto.createdAt)
  };
}

function measurementDataToCreateRequest(data: MeasurementData): MeasurementCreateRequest {
  return {
    name: data.name,
    type: data.type,
    value: data.value,
    unit: data.unit,
    dataSource: data.dataSource,
    coordinates: data.coordinates
  };
}

// ─── Service ────────────────────────────────────────────────────────────────

@Injectable({
  providedIn: 'root'
})
export class MeasurementApiService {

  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1/projects';

  /**
   * Busca medições de um chunk específico.
   */
  getMeasurements(projectId: number, chunkId: number): Observable<MeasurementData[]> {
    return new Observable(observer => {
      this.http
        .get<MeasurementApiDto[]>(`${this.baseUrl}/${projectId}/chunks/${chunkId}/measurements`)
        .subscribe({
          next: dtos => observer.next(dtos.map(apiDtoToMeasurementData)),
          error: err => observer.error(err),
          complete: () => observer.complete()
        });
    });
  }

  /**
   * Persiste uma nova medição.
   * Retorna o objeto salvo com o id gerado pelo backend.
   */
  saveMeasurement(projectId: number, chunkId: number, data: MeasurementData): Observable<MeasurementData> {
    const body = measurementDataToCreateRequest(data);
    return new Observable(observer => {
      this.http
        .post<MeasurementApiDto>(`${this.baseUrl}/${projectId}/chunks/${chunkId}/measurements`, body)
        .subscribe({
          next: dto => observer.next(apiDtoToMeasurementData(dto)),
          error: err => observer.error(err),
          complete: () => observer.complete()
        });
    });
  }

  /**
   * Remove uma medição pelo id numérico (backend Long).
   */
  deleteMeasurement(projectId: number, measurementId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/${projectId}/measurements/${measurementId}`);
  }

  /**
   * Atualiza a visibilidade de uma medição.
   */
  updateVisibility(projectId: number, measurementId: string, visible: boolean): Observable<MeasurementData> {
    return new Observable(observer => {
      this.http
        .patch<MeasurementApiDto>(
          `${this.baseUrl}/${projectId}/measurements/${measurementId}/visibility`,
          { visible }
        )
        .subscribe({
          next: dto => observer.next(apiDtoToMeasurementData(dto)),
          error: err => observer.error(err),
          complete: () => observer.complete()
        });
    });
  }

  /**
   * Renomeia uma medição.
   */
  renameMeasurement(projectId: number, measurementId: string, newName: string): Observable<MeasurementData> {
    return new Observable(observer => {
      this.http
        .patch<MeasurementApiDto>(
          `${this.baseUrl}/${projectId}/measurements/${measurementId}/name`,
          { name: newName }
        )
        .subscribe({
          next: dto => observer.next(apiDtoToMeasurementData(dto)),
          error: err => observer.error(err),
          complete: () => observer.complete()
        });
    });
  }
}
