/**
 * Service de Histórico de Medições
 * 
 * Responsabilidades:
 * - Manter histórico de medições
 * - Filtrar e buscar medições
 * - Estatísticas
 * - Versionamento (undo/redo)
 */

import { Injectable, signal } from '@angular/core';
import { Observable, BehaviorSubject, map } from 'rxjs';

import {
  Measurement,
  MeasurementFilters,
  MeasurementStats,
  MeasurementType,
  MeasurementStatus
} from '../models/measurement.model';

export interface MeasurementHistoryEntry {
  measurement: Measurement;
  action: 'create' | 'update' | 'delete';
  timestamp: Date;
  userId?: string;
}

@Injectable({
  providedIn: 'root'
})
export class MeasurementHistoryService {
  private historySubject = new BehaviorSubject<MeasurementHistoryEntry[]>([]);
  history$ = this.historySubject.asObservable();
  
  // Undo/Redo stacks
  private undoStack: MeasurementHistoryEntry[] = [];
  private redoStack: MeasurementHistoryEntry[] = [];
  
  canUndo = signal(false);
  canRedo = signal(false);

  // ============================================================================
  // HISTORY MANAGEMENT
  // ============================================================================

  /**
   * Adiciona entrada ao histórico
   */
  addToHistory(
    measurement: Measurement,
    action: 'create' | 'update' | 'delete',
    userId?: string
  ): void {
    const entry: MeasurementHistoryEntry = {
      measurement: { ...measurement },
      action,
      timestamp: new Date(),
      userId
    };

    const current = this.historySubject.value;
    this.historySubject.next([entry, ...current]);
    
    // Adiciona ao undo stack
    this.undoStack.push(entry);
    this.redoStack = []; // Limpa redo ao fazer nova ação
    this.updateStackSignals();
  }

  /**
   * Obtém histórico completo
   */
  getHistory(): Observable<MeasurementHistoryEntry[]> {
    return this.history$;
  }

  /**
   * Obtém histórico de uma medição específica
   */
  getMeasurementHistory(measurementId: string): Observable<MeasurementHistoryEntry[]> {
    return this.history$.pipe(
      map(entries => entries.filter(e => e.measurement.id === measurementId))
    );
  }

  /**
   * Limpa histórico
   */
  clearHistory(): void {
    this.historySubject.next([]);
    this.undoStack = [];
    this.redoStack = [];
    this.updateStackSignals();
  }

  // ============================================================================
  // UNDO/REDO
  // ============================================================================

  /**
   * Desfaz última ação
   */
  undo(): MeasurementHistoryEntry | null {
    const entry = this.undoStack.pop();
    if (!entry) return null;

    this.redoStack.push(entry);
    this.updateStackSignals();
    
    return entry;
  }

  /**
   * Refaz última ação desfeita
   */
  redo(): MeasurementHistoryEntry | null {
    const entry = this.redoStack.pop();
    if (!entry) return null;

    this.undoStack.push(entry);
    this.updateStackSignals();
    
    return entry;
  }

  private updateStackSignals(): void {
    this.canUndo.set(this.undoStack.length > 0);
    this.canRedo.set(this.redoStack.length > 0);
  }

  // ============================================================================
  // FILTERING & SEARCH
  // ============================================================================

  /**
   * Filtra medições
   */
  filterMeasurements(
    measurements: Measurement[],
    filters: MeasurementFilters
  ): Measurement[] {
    return measurements.filter(m => {
      // Projeto
      if (filters.projectId && m.projectId !== filters.projectId) return false;
      
      // Tipo
      if (filters.type?.length && !filters.type.includes(m.type)) return false;
      
      // Modo
      if (filters.mode?.length && !filters.mode.includes(m.mode)) return false;
      
      // Status
      if (filters.status?.length && !filters.status.includes(m.status)) return false;
      
      // Data
      if (filters.dateFrom && m.createdAt < filters.dateFrom) return false;
      if (filters.dateTo && m.createdAt > filters.dateTo) return false;
      
      // Criador
      if (filters.createdBy && m.createdBy !== filters.createdBy) return false;
      
      // Busca textual
      if (filters.searchTerm) {
        const term = filters.searchTerm.toLowerCase();
        const matchName = m.name.toLowerCase().includes(term);
        const matchDesc = m.description?.toLowerCase().includes(term);
        if (!matchName && !matchDesc) return false;
      }
      
      return true;
    });
  }

  /**
   * Busca medições por texto
   */
  searchMeasurements(
    measurements: Measurement[],
    searchTerm: string
  ): Measurement[] {
    const term = searchTerm.toLowerCase();
    return measurements.filter(m => 
      m.name.toLowerCase().includes(term) ||
      m.description?.toLowerCase().includes(term) ||
      m.type.toLowerCase().includes(term)
    );
  }

  /**
   * Ordena medições
   */
  sortMeasurements(
    measurements: Measurement[],
    sortBy: 'name' | 'date' | 'type' | 'value',
    order: 'asc' | 'desc' = 'desc'
  ): Measurement[] {
    const sorted = [...measurements].sort((a, b) => {
      let comparison = 0;
      
      switch (sortBy) {
        case 'name':
          comparison = a.name.localeCompare(b.name);
          break;
        case 'date':
          comparison = a.createdAt.getTime() - b.createdAt.getTime();
          break;
        case 'type':
          comparison = a.type.localeCompare(b.type);
          break;
        case 'value':
          comparison = a.result.value - b.result.value;
          break;
      }
      
      return order === 'asc' ? comparison : -comparison;
    });
    
    return sorted;
  }

  // ============================================================================
  // STATISTICS
  // ============================================================================

  /**
   * Calcula estatísticas de medições
   */
  calculateStats(measurements: Measurement[]): MeasurementStats {
    const stats: MeasurementStats = {
      total: measurements.length,
      byType: {} as Record<MeasurementType, number>,
      byStatus: {} as Record<MeasurementStatus, number>,
      totalDistance: 0,
      totalArea: 0,
      totalVolume: 0
    };

    // Inicializa contadores
    Object.values(MeasurementType).forEach(type => {
      stats.byType[type] = 0;
    });
    Object.values(MeasurementStatus).forEach(status => {
      stats.byStatus[status] = 0;
    });

    // Processa cada medição
    measurements.forEach(m => {
      // Contador por tipo
      stats.byType[m.type]++;
      
      // Contador por status
      stats.byStatus[m.status]++;
      
      // Totais
      switch (m.type) {
        case MeasurementType.DISTANCE:
          stats.totalDistance += m.result.value;
          break;
        case MeasurementType.AREA:
          stats.totalArea += m.result.value;
          break;
        case MeasurementType.VOLUME:
          stats.totalVolume += m.result.value;
          break;
      }
    });

    return stats;
  }

  /**
   * Obtém top N medições por valor
   */
  getTopMeasurements(
    measurements: Measurement[],
    type: MeasurementType,
    count: number = 10
  ): Measurement[] {
    return measurements
      .filter(m => m.type === type)
      .sort((a, b) => b.result.value - a.result.value)
      .slice(0, count);
  }

  /**
   * Agrupa medições por período
   */
  groupByPeriod(
    measurements: Measurement[],
    period: 'day' | 'week' | 'month'
  ): Map<string, Measurement[]> {
    const groups = new Map<string, Measurement[]>();

    measurements.forEach(m => {
      const date = new Date(m.createdAt);
      let key: string;

      switch (period) {
        case 'day':
          key = date.toISOString().split('T')[0];
          break;
        case 'week':
          const weekStart = new Date(date);
          weekStart.setDate(date.getDate() - date.getDay());
          key = weekStart.toISOString().split('T')[0];
          break;
        case 'month':
          key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
          break;
      }

      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(m);
    });

    return groups;
  }

  /**
   * Compara duas medições
   */
  compareMeasurements(m1: Measurement, m2: Measurement): {
    valueDiff: number;
    percentDiff: number;
    areaSame: boolean;
  } {
    const valueDiff = m2.result.value - m1.result.value;
    const percentDiff = m1.result.value !== 0 
      ? (valueDiff / m1.result.value) * 100 
      : 0;
    
    const areaSame = m1.type === m2.type && 
                     m1.result.unit === m2.result.unit;

    return {
      valueDiff,
      percentDiff,
      areaSame
    };
  }
}
