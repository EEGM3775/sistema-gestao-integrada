import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Chunk } from '../../../models/project.model';
import { OptionCategory, QualityLevel } from '../../constants/odm-options.const';

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
    selector: 'app-process-tab',
    imports: [CommonModule, FormsModule],
    changeDetection: ChangeDetectionStrategy.OnPush,
    template: `
    <div class="process-tab">
      <div class="process-section">
        <h4>Produtos de Saída</h4>
        <div class="output-options">
          <label class="output-option">
            <input type="checkbox" [(ngModel)]="chunkOptions.orthophoto" />
            <div class="option-content">
              <span class="option-icon">🗺️</span>
              <div>
                <span class="option-name">Ortofoto</span>
                <span class="option-desc">Imagem aérea georreferenciada</span>
              </div>
            </div>
          </label>
          <label class="output-option">
            <input type="checkbox" [(ngModel)]="chunkOptions.dsm" />
            <div class="option-content">
              <span class="option-icon">🏔️</span>
              <div>
                <span class="option-name">DSM</span>
                <span class="option-desc">Modelo Digital de Superfície</span>
              </div>
            </div>
          </label>
          <label class="output-option">
            <input type="checkbox" [(ngModel)]="chunkOptions.dtm" />
            <div class="option-content">
              <span class="option-icon">🌍</span>
              <div>
                <span class="option-name">DTM</span>
                <span class="option-desc">Modelo Digital de Terreno</span>
              </div>
            </div>
          </label>
          <label class="output-option">
            <input type="checkbox" [(ngModel)]="chunkOptions.pointCloud" />
            <div class="option-content">
              <span class="option-icon">✨</span>
              <div>
                <span class="option-name">Nuvem de Pontos</span>
                <span class="option-desc">Pontos 3D coloridos (LAZ)</span>
              </div>
            </div>
          </label>
          <label class="output-option">
            <input type="checkbox" [(ngModel)]="chunkOptions.mesh" />
            <div class="option-content">
              <span class="option-icon">🎮</span>
              <div>
                <span class="option-name">Modelo 3D</span>
                <span class="option-desc">Malha texturizada (OBJ/GLB)</span>
              </div>
            </div>
          </label>
        </div>
      </div>

      <div class="process-section">
        <h4>Qualidade</h4>
        <div class="quality-options">
          @for (q of qualityLevels; track q.value) {
            <label class="quality-option" [class.selected]="chunkOptions.quality === q.value">
              <input type="radio" name="quality" [value]="q.value" [(ngModel)]="chunkOptions.quality" />
              <div class="quality-content">
                <span class="quality-name">{{ q.name }}</span>
                <span class="quality-desc">{{ q.description }}</span>
                <span class="quality-time">~{{ q.time }}</span>
              </div>
            </label>
          }
        </div>
      </div>

      <!-- Advanced Options -->
      <div class="process-section">
        <button class="btn-toggle-advanced" (click)="toggleAdvancedOptions.emit(!showAdvancedOptions)">
          {{ showAdvancedOptions ? '▼' : '▶' }} Opções Avançadas do NodeODM
        </button>
        
        @if (showAdvancedOptions) {
          <div class="advanced-options">
            <p class="advanced-hint">⚡ Configurações avançadas do processamento. Altere apenas se souber o que está fazendo.</p>
            
            @for (category of advancedOptionCategories; track category.name) {
              <div class="option-category">
                <button class="category-header" (click)="category.expanded = !category.expanded">
                  <span class="category-icon">{{ category.icon }}</span>
                  <span class="category-name">{{ category.name }}</span>
                  <span class="category-toggle">{{ category.expanded ? '▼' : '▶' }}</span>
                </button>
                
                @if (category.expanded) {
                  <div class="category-options">
                    @for (opt of category.options; track opt.key) {
                      <div class="advanced-option">
                        <div class="option-header">
                          <label [for]="opt.key">{{ opt.label }}</label>
                          <span class="option-help" [title]="opt.help">❓</span>
                        </div>
                        
                        @if (opt.type === 'boolean') {
                          <label class="toggle-switch">
                            <input 
                              type="checkbox" 
                              [id]="opt.key"
                              [(ngModel)]="chunkAdvancedOptions[opt.key]"
                            />
                            <span class="toggle-slider"></span>
                          </label>
                        } @else if (opt.type === 'select') {
                          <select [id]="opt.key" [(ngModel)]="chunkAdvancedOptions[opt.key]">
                            @for (option of $any(opt).options; track option) {
                              <option [value]="option">{{ option }}</option>
                            }
                          </select>
                        } @else if (opt.type === 'number') {
                          <input 
                            type="number" 
                            [id]="opt.key"
                            [(ngModel)]="chunkAdvancedOptions[opt.key]"
                            [min]="$any(opt).min"
                            [max]="$any(opt).max"
                            [step]="$any(opt).step || 1"
                          />
                        } @else if (opt.type === 'file') {
                          <div class="file-input-wrapper">
                            @if (gcpFileFor(opt.key)) {
                              <div class="gcp-file-ready">
                                <span class="gcp-ok">[OK]</span>
                                <span class="gcp-name">{{ gcpFileFor(opt.key)!.name }}</span>
                                <button class="gcp-btn-change" (click)="openGcpEditor.emit()">Editar</button>
                                <button class="gcp-btn-clear" (click)="clearGcpFile(opt.key)">x</button>
                              </div>
                            } @else {
                              <button class="btn-open-gcp-editor" (click)="openGcpEditor.emit()">
                                [GCP] Abrir Editor de GCP
                              </button>
                              <details class="gcp-format-hint">
                                <summary>Ver formato do arquivo .txt</summary>
                                <p class="gcp-hint-label">GPS (WGS84):</p>
                                <pre class="gcp-example">EPSG:4326
-23.5506 -46.6334 760.5 0 0 foto001.jpg
-23.5512 -46.6341 761.0 0 0 foto002.jpg
-23.5498 -46.6320 759.8 0 0 foto003.jpg</pre>
                                <p class="gcp-hint-label">UTM (ex: SIRGAS 2000 zona 22S):</p>
                                <pre class="gcp-example">EPSG:31982
316500.123 7394200.456 760.5 0 0 foto001.jpg
316612.780 7394105.321 761.0 0 0 foto002.jpg
316388.045 7394350.890 759.8 0 0 foto003.jpg</pre>
                                <p class="gcp-hint-note">Colunas: X/lon  Y/lat  alt  px  py  imagem.jpg<br/>px/py podem ser 0 — o editor preenche ao marcar nas fotos.</p>
                              </details>
                              <div class="gcp-or">ou importe um arquivo ja pronto:</div>
                              <label class="file-input-label" [for]="'file-' + opt.key">
                                Selecionar .txt
                              </label>
                            }
                            <input
                              type="file"
                              [id]="'file-' + opt.key"
                              [accept]="$any(opt).accept || '.txt'"
                              class="file-input-hidden"
                              (change)="onFileChange($event, opt.key)"
                            />
                          </div>
                        } @else {
                          <input 
                            type="text" 
                            [id]="opt.key"
                            [(ngModel)]="chunkAdvancedOptions[opt.key]"
                            [placeholder]="opt.help"
                          />
                        }
                      </div>
                    }
                  </div>
                }
              </div>
            }
            
            <div class="advanced-actions">
              <button class="btn-reset-options" (click)="resetAdvancedOptions.emit()">
                🔄 Restaurar Padrões
              </button>
            </div>
          </div>
        }
      </div>

      <div class="process-actions">
        <div class="process-summary">
          {{ chunk.imageCount }} imagens • {{ getSelectedOutputsCount() }} produtos
        </div>
        <button 
          class="btn-start-process"
          [disabled]="!canProcess()"
          (click)="startProcess.emit()"
        >
          ▶ Iniciar Processamento
        </button>
      </div>
    </div>
  `,
    styles: [`
    .process-tab {
      max-width: 700px;
    }

    .process-section {
      margin-bottom: 24px;
    }

    .process-section h4 {
      margin: 0 0 12px;
    }

    .output-options {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .output-option {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      cursor: pointer;
    }

    .output-option:hover { border-color: #8b949e; }
    .output-option input { width: 18px; height: 18px; }

    .option-content {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .option-icon { font-size: 20px; }
    .option-name { font-weight: 500; display: block; }
    .option-desc { font-size: 11px; color: #8b949e; }

    .quality-options {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
    }

    .quality-option {
      cursor: pointer;
    }

    .quality-option input { display: none; }

    .quality-content {
      padding: 12px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      text-align: center;
    }

    .quality-option:hover .quality-content { border-color: #8b949e; }
    .quality-option.selected .quality-content,
    .quality-option input:checked + .quality-content {
      border-color: #58a6ff;
      background: #1f6feb11;
    }

    .quality-name { display: block; font-weight: 600; margin-bottom: 4px; }
    .quality-desc { display: block; font-size: 11px; color: #8b949e; }
    .quality-time { display: block; font-size: 10px; color: #6e7681; margin-top: 4px; }

    .process-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 16px;
      border-top: 1px solid #30363d;
    }

    .process-summary { color: #8b949e; }

    .btn-start-process {
      background: #238636;
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }

    .btn-start-process:hover:not(:disabled) { background: #2ea043; }
    .btn-start-process:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }

    /* Advanced Options */
    .btn-toggle-advanced {
      background: transparent;
      border: none;
      color: #8b949e;
      cursor: pointer;
      padding: 8px 0;
      font-size: 13px;
    }
    .btn-toggle-advanced:hover { color: #c9d1d9; }

    .advanced-options {
      margin-top: 12px;
      padding: 16px;
      background: #161b22;
      border-radius: 8px;
      border: 1px solid #30363d;
      max-height: 60vh;
      overflow-y: auto;
    }
    
    .advanced-hint {
      color: #8b949e;
      font-size: 12px;
      margin-bottom: 16px;
      padding: 8px 12px;
      background: #21262d;
      border-radius: 6px;
      border-left: 3px solid #f0883e;
    }
    
    .option-category {
      margin-bottom: 8px;
      border: 1px solid #30363d;
      border-radius: 6px;
      overflow: hidden;
    }
    
    .category-header {
      width: 100%;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      background: #21262d;
      border: none;
      color: #c9d1d9;
      cursor: pointer;
      text-align: left;
      font-size: 13px;
      transition: background 0.15s;
    }
    
    .category-header:hover { background: #30363d; }
    .category-icon { font-size: 16px; }
    .category-name { flex: 1; font-weight: 500; }
    .category-toggle { color: #8b949e; font-size: 10px; }
    
    .category-options {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 12px;
      padding: 12px;
      background: #0d1117;
    }
    
    .advanced-option {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    
    .option-header {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    
    .option-header label { font-size: 11px; color: #8b949e; }
    .option-help { font-size: 10px; cursor: help; opacity: 0.6; }
    .option-help:hover { opacity: 1; }
    
    .advanced-option input[type="number"],
    .advanced-option input[type="text"],
    .advanced-option select {
      padding: 6px 8px;
      font-size: 12px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 4px;
      color: #c9d1d9;
    }
    
    .advanced-option input:focus,
    .advanced-option select:focus {
      border-color: #58a6ff;
      outline: none;
    }
    
    /* Toggle Switch */
    .toggle-switch {
      position: relative;
      display: inline-block;
      width: 40px;
      height: 20px;
    }
    
    .toggle-switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }
    
    .toggle-slider {
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: #30363d;
      transition: 0.2s;
      border-radius: 20px;
    }
    
    .toggle-slider:before {
      position: absolute;
      content: "";
      height: 14px;
      width: 14px;
      left: 3px;
      bottom: 3px;
      background-color: #8b949e;
      transition: 0.2s;
      border-radius: 50%;
    }
    
    .toggle-switch input:checked + .toggle-slider {
      background-color: #238636;
    }
    
    .toggle-switch input:checked + .toggle-slider:before {
      transform: translateX(20px);
      background-color: white;
    }
    
    .advanced-actions {
      margin-top: 16px;
      padding-top: 12px;
      border-top: 1px solid #30363d;
      display: flex;
      justify-content: flex-end;
    }
    
    .file-input-wrapper {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .btn-open-gcp-editor {
      width: 100%;
      padding: 7px 12px;
      background: #1a3025;
      border: 1px solid #2ea043;
      border-radius: 6px;
      color: #3fb950;
      font-size: 12px;
      font-family: monospace;
      font-weight: 600;
      cursor: pointer;
      text-align: center;
    }

    .btn-open-gcp-editor:hover {
      background: #21392d;
      border-color: #3fb950;
    }

    .gcp-or {
      font-size: 10px;
      color: #8b949e;
      text-align: center;
    }

    .gcp-format-hint {
      font-size: 10px;
      color: #8b949e;
    }

    .gcp-format-hint summary {
      cursor: pointer;
      color: #58a6ff;
      font-size: 10px;
      padding: 2px 0;
      user-select: none;
    }

    .gcp-format-hint summary:hover {
      color: #79c0ff;
    }

    .gcp-example {
      margin: 4px 0 2px;
      padding: 6px 8px;
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 4px;
      font-size: 10px;
      font-family: monospace;
      color: #e6edf3;
      white-space: pre;
      overflow-x: auto;
      line-height: 1.5;
    }

    .gcp-hint-label {
      margin: 4px 0 1px;
      font-size: 9px;
      color: #8b949e;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    .gcp-hint-note {
      margin: 2px 0 0;
      font-size: 9px;
      color: #6e7681;
      line-height: 1.5;
    }

    .gcp-file-ready {
      display: flex;
      align-items: center;
      gap: 6px;
      background: #1a3025;
      border: 1px solid #2ea043;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 11px;
    }

    .gcp-ok {
      color: #3fb950;
      font-family: monospace;
      font-weight: 700;
      flex-shrink: 0;
    }

    .gcp-name {
      flex: 1;
      color: #c9d1d9;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .gcp-btn-change {
      background: none;
      border: 1px solid #30363d;
      color: #8b949e;
      padding: 2px 6px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 10px;
    }

    .gcp-btn-clear {
      background: none;
      border: none;
      color: #f85149;
      cursor: pointer;
      font-size: 11px;
      padding: 0 2px;
      font-family: monospace;
    }

    .file-input-hidden {
      position: absolute;
      width: 0;
      height: 0;
      opacity: 0;
      pointer-events: none;
    }

    .file-input-label {
      display: block;
      padding: 5px 10px;
      background: #21262d;
      border: 1px dashed #30363d;
      border-radius: 5px;
      color: #8b949e;
      font-size: 11px;
      cursor: pointer;
      text-align: center;
    }

    .file-input-label:hover {
      border-color: #58a6ff;
      color: #58a6ff;
    }

    .btn-reset-options {
      background: transparent;
      border: 1px solid #30363d;
      color: #8b949e;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      transition: all 0.15s;
    }
    
    .btn-reset-options:hover {
      background: #21262d;
      color: #c9d1d9;
      border-color: #8b949e;
    }
  `]
})
export class ProcessTabComponent {
  @Input() chunk!: Chunk;
  @Input() chunkOptions!: ChunkOptions;
  @Input() chunkAdvancedOptions!: Record<string, any>;
  @Input() qualityLevels: QualityLevel[] = [];
  @Input() advancedOptionCategories: OptionCategory[] = [];
  @Input() showAdvancedOptions = false;
  /** Arquivo GCP gerado pelo editor visual — refletido no display deste campo */
  @Input() gcpFileFromEditor: File | null = null;

  @Output() toggleAdvancedOptions = new EventEmitter<boolean>();
  @Output() resetAdvancedOptions = new EventEmitter<void>();
  @Output() startProcess = new EventEmitter<void>();
  @Output() gcpFileSelected = new EventEmitter<{ key: string; file: File | null }>();
  @Output() openGcpEditor = new EventEmitter<void>();

  /** Map of option-key -> File selecionado para inputs do tipo 'file' */
  gcpFileMap: Record<string, File | null> = {};

  /** Retorna o arquivo GCP para um optKey: preferencia para upload local, fallback no editor */
  gcpFileFor(optKey: string): File | null {
    return this.gcpFileMap[optKey] ?? (optKey === 'gcp' ? this.gcpFileFromEditor : null);
  }

  onFileChange(event: Event, optKey: string): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.gcpFileMap = { ...this.gcpFileMap, [optKey]: file };
    this.gcpFileSelected.emit({ key: optKey, file });
  }

  clearGcpFile(optKey: string): void {
    this.gcpFileMap = { ...this.gcpFileMap, [optKey]: null };
    this.gcpFileSelected.emit({ key: optKey, file: null });
  }

  canProcess(): boolean {
    return this.chunk.imageCount >= 3 && 
           (this.chunk.status === 'READY' || this.chunk.status === 'FAILED');
  }

  getSelectedOutputsCount(): number {
    let count = 0;
    if (this.chunkOptions.orthophoto) count++;
    if (this.chunkOptions.dsm) count++;
    if (this.chunkOptions.dtm) count++;
    if (this.chunkOptions.pointCloud) count++;
    if (this.chunkOptions.mesh) count++;
    return count;
  }
}
