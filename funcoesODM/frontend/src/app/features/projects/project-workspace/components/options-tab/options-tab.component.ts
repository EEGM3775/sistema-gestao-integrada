import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Chunk } from '../../../models/project.model';

export interface ChunkOptions {
  crs: string;
  orthophoto: boolean;
  dsm: boolean;
  dtm: boolean;
  pointCloud: boolean;
  mesh: boolean;
  quality: string;
}

@Component({
  selector: 'app-options-tab',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="options-tab">
      <div class="options-section">
        <h4>Informações do Chunk</h4>
        <div class="form-group">
          <label>Nome</label>
          <input 
            type="text" 
            [value]="chunk.name"
            (input)="onNameChange($event)"
            (blur)="chunkNameSave.emit()"
          />
        </div>
        <div class="form-group">
          <label>Descrição</label>
          <textarea 
            rows="3"
            [value]="chunk.description || ''"
            (input)="onDescriptionChange($event)"
            (blur)="chunkDescriptionSave.emit()"
            placeholder="Descrição opcional..."
          ></textarea>
        </div>
      </div>

      <div class="options-section">
        <h4>Sistema de Coordenadas</h4>
        <div class="form-group">
          <label>CRS de Saída</label>
          <select [(ngModel)]="chunkOptions.crs">
            <option value="EPSG:4326">WGS 84 (EPSG:4326)</option>
            <option value="EPSG:32723">WGS 84 / UTM zone 23S</option>
            <option value="EPSG:32722">WGS 84 / UTM zone 22S</option>
            <option value="EPSG:31983">SIRGAS 2000 / UTM zone 23S</option>
          </select>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .options-tab {
      max-width: 600px;
    }

    .options-section {
      margin-bottom: 24px;
    }

    .options-section h4 {
      margin: 0 0 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid #30363d;
    }

    .form-group {
      margin-bottom: 16px;
    }

    .form-group label {
      display: block;
      margin-bottom: 6px;
      font-weight: 500;
      color: #8b949e;
    }

    .form-group input,
    .form-group textarea,
    .form-group select {
      width: 100%;
      background: #0d1117;
      border: 1px solid #30363d;
      color: #c9d1d9;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
    }

    .form-group input:focus,
    .form-group textarea:focus,
    .form-group select:focus {
      outline: none;
      border-color: #58a6ff;
    }
  `]
})
export class OptionsTabComponent {
  @Input() chunk!: Chunk;
  @Input() chunkOptions!: ChunkOptions;

  @Output() chunkNameChange = new EventEmitter<Event>();
  @Output() chunkNameSave = new EventEmitter<void>();
  @Output() chunkDescriptionChange = new EventEmitter<Event>();
  @Output() chunkDescriptionSave = new EventEmitter<void>();

  onNameChange(event: Event): void {
    this.chunkNameChange.emit(event);
  }

  onDescriptionChange(event: Event): void {
    this.chunkDescriptionChange.emit(event);
  }
}
