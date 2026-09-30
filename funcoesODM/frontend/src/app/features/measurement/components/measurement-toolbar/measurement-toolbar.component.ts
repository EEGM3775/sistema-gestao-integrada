/**
 * Measurement Toolbar Component
 * 
 * Barra de ferramentas com botões de medição
 * 
 * Features:
 * - Botões para cada tipo de medição
 * - Indicador de modo ativo
 * - Atalhos de teclado
 * - Tooltips descritivos
 * 
 * Responsabilidades:
 * - Emitir eventos de seleção de ferramenta
 * - Mostrar estado ativo
 * - Desabilitar ferramentas quando apropriado
 */

import { Component, Output, EventEmitter, Input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { MeasurementType, MeasurementMode } from '../../models/measurement.model';

export interface MeasurementTool {
  type: MeasurementType;
  icon: string;
  label: string;
  tooltip: string;
  shortcut?: string;
  disabled?: boolean;
}

@Component({
  selector: 'app-measurement-toolbar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './measurement-toolbar.component.html',
  styleUrls: ['./measurement-toolbar.component.scss']
})
export class MeasurementToolbarComponent {
  @Input() viewMode: MeasurementMode = MeasurementMode.ORTHOPHOTO;
  @Input() isDrawing = false;
  @Input() canComplete = false;
  
  @Output() toolSelected = new EventEmitter<MeasurementType>();
  @Output() complete = new EventEmitter<void>();
  @Output() cancel = new EventEmitter<void>();
  @Output() undo = new EventEmitter<void>();
  @Output() clear = new EventEmitter<void>();
  
  activeToolSignal = signal<MeasurementType | null>(null);

  /**
   * Ferramentas disponíveis
   */
  tools: MeasurementTool[] = [
    {
      type: MeasurementType.DISTANCE,
      icon: '📏',
      label: 'Distância',
      tooltip: 'Medir distância linear (2D/3D)',
      shortcut: 'D'
    },
    {
      type: MeasurementType.AREA,
      icon: '⬜',
      label: 'Área',
      tooltip: 'Medir área de polígono',
      shortcut: 'A'
    },
    {
      type: MeasurementType.VOLUME,
      icon: '📦',
      label: 'Volume',
      tooltip: 'Calcular volume entre superfícies',
      shortcut: 'V'
    },
    {
      type: MeasurementType.ELEVATION,
      icon: '📈',
      label: 'Perfil',
      tooltip: 'Perfil de elevação',
      shortcut: 'E'
    },
    {
      type: MeasurementType.PERIMETER,
      icon: '⭕',
      label: 'Perímetro',
      tooltip: 'Medir perímetro de polígono',
      shortcut: 'P'
    },
    {
      type: MeasurementType.SLOPE,
      icon: '⛰️',
      label: 'Inclinação',
      tooltip: 'Medir inclinação do terreno',
      shortcut: 'S'
    },
    {
      type: MeasurementType.ANGLE,
      icon: '∠',
      label: 'Ângulo',
      tooltip: 'Medir ângulo entre linhas',
      shortcut: 'G'
    },
    {
      type: MeasurementType.HEIGHT,
      icon: '📐',
      label: 'Altura',
      tooltip: 'Medir altura de objeto',
      shortcut: 'H'
    }
  ];

  /**
   * Seleciona ferramenta
   */
  selectTool(type: MeasurementType): void {
    if (this.isDrawing) return;
    
    this.activeToolSignal.set(type);
    this.toolSelected.emit(type);
  }

  /**
   * Verifica se ferramenta está ativa
   */
  isActive(type: MeasurementType): boolean {
    return this.activeToolSignal() === type;
  }

  /**
   * Verifica se ferramenta está disponível para o modo atual
   */
  isAvailable(type: MeasurementType): boolean {
    // Volume e elevação requerem DEM
    if ([MeasurementType.VOLUME, MeasurementType.ELEVATION].includes(type)) {
      return this.viewMode === MeasurementMode.DEM || this.viewMode === MeasurementMode.POINTCLOUD;
    }
    
    // Altura requer 3D
    if (type === MeasurementType.HEIGHT) {
      return this.viewMode === MeasurementMode.POINTCLOUD || this.viewMode === MeasurementMode.MESH;
    }
    
    return true;
  }

  /**
   * Finaliza medição
   */
  onComplete(): void {
    this.complete.emit();
    this.activeToolSignal.set(null);
  }

  /**
   * Cancela medição
   */
  onCancel(): void {
    this.cancel.emit();
    this.activeToolSignal.set(null);
  }

  /**
   * Desfaz último ponto
   */
  onUndo(): void {
    this.undo.emit();
  }

  /**
   * Limpa todas as medições
   */
  onClear(): void {
    this.clear.emit();
    this.activeToolSignal.set(null);
  }
}
