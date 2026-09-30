import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DisplayType, ColorMode } from '../../models/project-3d.model';

/**
 * Componente Viewer Options
 * 
 * Painel de configurações do visualizador:
 * - Tipo de display (pointcloud/mesh)
 * - Modo de cor (RGB/elevação/intensidade)
 * - Tamanho de pontos
 * - Grid e eixos
 * 
 * Responsabilidades:
 * - Renderizar opções de visualização
 * - Emitir mudanças de configuração
 * - Validar valores de entrada
 */
@Component({
    selector: 'app-viewer-options',
    imports: [CommonModule],
    templateUrl: './viewer-options.component.html',
    styleUrls: ['./viewer-options.component.scss']
})
export class ViewerOptionsComponent {
  @Input() displayType: DisplayType = 'pointcloud';
  @Input() colorMode: ColorMode = 'rgb';
  @Input() pointSize: number = 3;
  @Input() showGrid: boolean = true;
  @Input() showAxes: boolean = true;

  @Output() displayTypeChange = new EventEmitter<DisplayType>();
  @Output() colorModeChange = new EventEmitter<ColorMode>();
  @Output() pointSizeChange = new EventEmitter<number>();
  @Output() showGridChange = new EventEmitter<boolean>();
  @Output() showAxesChange = new EventEmitter<boolean>();

  setDisplayType(type: DisplayType): void {
    this.displayTypeChange.emit(type);
  }

  setColorMode(mode: ColorMode): void {
    this.colorModeChange.emit(mode);
  }

  onPointSizeChange(event: Event): void {
    const value = parseInt((event.target as HTMLInputElement).value);
    this.pointSizeChange.emit(value);
  }

  toggleGrid(): void {
    this.showGridChange.emit(!this.showGrid);
  }

  toggleAxes(): void {
    this.showAxesChange.emit(!this.showAxes);
  }
}
