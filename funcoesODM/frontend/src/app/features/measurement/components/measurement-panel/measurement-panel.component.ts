/**
 * Measurement Panel Component
 * 
 * Painel de resultados e propriedades de medição
 * 
 * Features:
 * - Exibe resultado da medição ativa
 * - Lista de pontos
 * - Configurações (unidade, precisão)
 * - Exportação rápida
 * 
 * Responsabilidades:
 * - Mostrar resultado em tempo real
 * - Permitir edição de propriedades
 * - Botões de ação (salvar, exportar, deletar)
 */

import { Component, Input, Output, EventEmitter, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { 
  Measurement, 
  MeasurementUnit,
  MeasurementPoint
} from '../../models/measurement.model';

@Component({
  selector: 'app-measurement-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './measurement-panel.component.html',
  styleUrls: ['./measurement-panel.component.scss']
})
export class MeasurementPanelComponent {
  @Input() measurement: Measurement | null = null;
  @Input() isEditing = false;
  
  @Output() save = new EventEmitter<Measurement>();
  @Output() delete = new EventEmitter<string>();
  @Output() export = new EventEmitter<{measurement: Measurement, format: string}>();
  @Output() unitChange = new EventEmitter<MeasurementUnit>();
  
  showPoints = signal(false);
  showSettings = signal(false);
  
  // Available units based on measurement type
  availableUnits = computed(() => {
    if (!this.measurement) return [];
    
    const type = this.measurement.type;
    if (type === 'distance' || type === 'perimeter') {
      return [
        MeasurementUnit.METERS,
        MeasurementUnit.KILOMETERS,
        MeasurementUnit.FEET,
        MeasurementUnit.MILES
      ];
    } else if (type === 'area') {
      return [
        MeasurementUnit.SQUARE_METERS,
        MeasurementUnit.SQUARE_KILOMETERS,
        MeasurementUnit.HECTARES,
        MeasurementUnit.SQUARE_FEET,
        MeasurementUnit.ACRES
      ];
    } else if (type === 'volume') {
      return [
        MeasurementUnit.CUBIC_METERS,
        MeasurementUnit.CUBIC_FEET,
        MeasurementUnit.LITERS
      ];
    }
    return [];
  });

  onSave(): void {
    if (this.measurement) {
      this.save.emit(this.measurement);
    }
  }

  onDelete(): void {
    if (this.measurement && confirm('Deletar esta medição?')) {
      this.delete.emit(this.measurement.id);
    }
  }

  onExport(format: string): void {
    if (this.measurement) {
      this.export.emit({ measurement: this.measurement, format });
    }
  }

  onUnitChange(unit: MeasurementUnit): void {
    this.unitChange.emit(unit);
  }

  togglePoints(): void {
    this.showPoints.update(v => !v);
  }

  toggleSettings(): void {
    this.showSettings.update(v => !v);
  }

  formatCoordinate(value: number): string {
    return value.toFixed(6);
  }
}
