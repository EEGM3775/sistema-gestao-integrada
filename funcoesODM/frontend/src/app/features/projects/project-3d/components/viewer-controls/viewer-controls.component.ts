import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ViewMode } from '../../models/project-3d.model';

/**
 * Componente Viewer Controls
 * 
 * Controles de navegação 3D:
 * - Modo de câmera (orbit/pan/zoom)
 * - Reset de câmera
 * - Screenshot
 * - Tela cheia
 * 
 * Responsabilidades:
 * - Renderizar botões de controle
 * - Emitir eventos de ações
 * - Indicar modo ativo
 */
@Component({
  selector: 'app-viewer-controls',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './viewer-controls.component.html',
  styleUrls: ['./viewer-controls.component.scss']
})
export class ViewerControlsComponent {
  @Input() viewMode: ViewMode = 'orbit';
  @Input() isFullscreen: boolean = false;

  @Output() viewModeChange = new EventEmitter<ViewMode>();
  @Output() resetCamera = new EventEmitter<void>();
  @Output() takeScreenshot = new EventEmitter<void>();
  @Output() toggleFullscreen = new EventEmitter<void>();

  setViewMode(mode: ViewMode): void {
    this.viewModeChange.emit(mode);
  }

  onResetCamera(): void {
    this.resetCamera.emit();
  }

  onTakeScreenshot(): void {
    this.takeScreenshot.emit();
  }

  onToggleFullscreen(): void {
    this.toggleFullscreen.emit();
  }
}
