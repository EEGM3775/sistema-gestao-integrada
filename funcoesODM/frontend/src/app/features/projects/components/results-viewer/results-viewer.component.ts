import { Component, Input, OnInit, OnChanges, SimpleChanges, signal, computed, inject, ViewChild, ElementRef, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ResultsService, AssetInfo, TaskWarnings } from '../../services/results.service';
import { TaskOutputs, ProcessingTask } from '../../services/task.service';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { fromArrayBuffer } from 'geotiff';
import { firstValueFrom } from 'rxjs';

import { DownloadsTabComponent } from './components/downloads-tab/downloads-tab.component';
import { WarningsTabComponent } from './components/warnings-tab/warnings-tab.component';
import { MeasurementTabComponent } from '../measurement-tab/measurement-tab.component';
import { VegetationTabComponent } from './components/vegetation-tab/vegetation-tab.component';
import { TabType, SelectableAsset } from './models/results-viewer.model';

type ExtendedTabType = TabType | 'pointcloud' | 'model3d' | 'measurements' | 'vegetation';

/**
 * Componente coordenador para visualização de resultados
 * Gerencia as abas e delega visualização para sub-componentes
 * Interface estilo Metashape/DroneDeploy
 */
@Component({
  selector: 'app-results-viewer',
  standalone: true,
  imports: [
    CommonModule,
    DownloadsTabComponent,
    WarningsTabComponent,
    MeasurementTabComponent,
    VegetationTabComponent
  ],
  templateUrl: './results-viewer.component.html',
  styleUrls: ['./results-viewer.component.scss']
})
export class ResultsViewerComponent implements OnInit, OnChanges {
  @Input() projectId!: number;
  @Input() taskId!: number;
  @Input() nodeodmTaskId?: string;
  @Input() outputs: TaskOutputs | { [key: string]: string } = {};
  @Input() task?: ProcessingTask;

  @ViewChild('previewCanvas') previewCanvas?: ElementRef<HTMLCanvasElement>;

  // Task cacheada — evita criar novo objeto a cada ciclo de change detection
  cachedActiveTask: ProcessingTask | undefined;

  private resultsService = inject(ResultsService);
  private http = inject(HttpClient);
  private sanitizer = inject(DomSanitizer);
  private cdr = inject(ChangeDetectorRef);

  // State
  activeTab = signal<ExtendedTabType>('measurements');
  assets = signal<AssetInfo[]>([]);
  selectableAssets = signal<SelectableAsset[]>([]);
  taskWarnings = signal<TaskWarnings | null>(null);
  loadingWarnings = signal(false);

  // Preview modal state
  previewOpen = signal(false);
  previewTitle = signal('');
  previewType = signal<'tiff' | 'pdf' | 'message'>('message');
  previewMessage = signal('');
  previewError = signal<string | null>(null);
  previewLoading = signal(false);
  previewPdfUrl = signal<SafeResourceUrl | null>(null);
  previewDownloadUrl = signal<string | null>(null);
  private previewObjectUrl: string | null = null;

  // Computed - Detecta tipos de arquivos disponíveis
  hasOrthophoto = computed(() => 
    this.assets().some(a => a.name.includes('orthophoto'))
  );

  hasDSM = computed(() => 
    this.assets().some(a => a.name.includes('dsm') || a.name.includes('dtm'))
  );
  
  hasPointcloud = computed(() => 
    this.assets().some(a => 
      a.name.includes('georeferenced_model') || 
      a.name.includes('.laz') || 
      a.name.includes('.las') ||
      a.name.includes('pointcloud')
    )
  );
  
  hasModel3D = computed(() => 
    this.assets().some(a => 
      a.name.includes('textured_model') || 
      a.name.includes('.obj') || 
      a.name.includes('.glb') ||
      a.name.includes('model3d')
    )
  );
  
  hasAnyViewer = computed(() => 
    this.hasOrthophoto() || this.hasDSM() || this.hasPointcloud()
  );

  hasWarnings = computed(() => {
    const warnings = this.taskWarnings();
    return warnings !== null && warnings.warning_count > 0;
  });

  hasCriticalWarnings = computed(() => {
    const warnings = this.taskWarnings();
    return warnings?.has_critical_warnings ?? false;
  });

  warningCount = computed(() => {
    const warnings = this.taskWarnings();
    return warnings?.unique_warning_count ?? 0;
  });

  ngOnInit(): void {
    console.log('🎯 ResultsViewer initialized with:', {
      projectId: this.projectId,
      taskId: this.taskId,
      nodeodmTaskId: this.nodeodmTaskId,
      outputs: this.outputs
    });
    console.log('🎯 Active Tab:', this.activeTab());
    this.buildCachedTask();
    this.loadAssets();
    this.loadWarnings();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['task'] || changes['taskId'] || changes['outputs'] || changes['nodeodmTaskId']) {
      this.buildCachedTask();
    }
  }

  setActiveTab(tab: ExtendedTabType): void {
    console.log('🎯 Tab changed to:', tab);
    this.activeTab.set(tab);
  }
  
  // Helper methods para obter assets específicos
  getPointcloudAsset(): SelectableAsset | undefined {
    return this.selectableAssets().find(a => 
      a.name.includes('georeferenced_model') || 
      a.name.includes('.laz') || 
      a.name.includes('.las')
    );
  }
  
  getModelAsset(): SelectableAsset | undefined {
    return this.selectableAssets().find(a => 
      a.name.includes('textured_model') || 
      a.name.includes('.obj') || 
      a.name.includes('.glb')
    );
  }
  
  hasMeasurements(): boolean {
    // TODO: Integrar com MeasurementService para verificar medições salvas
    return false;
  }
  
  openMeasurementViewer(type: 'orthophoto' | 'dsm' | 'pointcloud'): void {
    // TODO: Abrir modal de medição ou navegar para viewer específico
    console.log('Opening measurement viewer for:', type);
    // Por enquanto, muda para a aba correspondente
    if (type === 'orthophoto') this.setActiveTab('map');
    else if (type === 'dsm') this.setActiveTab('dsm');
    else if (type === 'pointcloud') this.setActiveTab('pointcloud');
  }
  
  /** Reconstrói a task cacheada — chamado apenas em ngOnInit/ngOnChanges */
  private buildCachedTask(): void {
    if (this.task) {
      this.cachedActiveTask = this.task;
      return;
    }
    if (this.taskId && this.outputs) {
      this.cachedActiveTask = {
        id: this.taskId,
        projectId: this.projectId,
        name: `Task ${this.taskId}`,
        status: 'COMPLETED',
        progress: 100,
        statusMessage: 'Completed',
        outputs: this.outputs as TaskOutputs,
        nodeodmTaskId: this.nodeodmTaskId,
        createdAt: new Date().toISOString()
      } as ProcessingTask;
      return;
    }
    this.cachedActiveTask = undefined;
  }

  /** @deprecated use cachedActiveTask — mantido para compatibilidade */
  getActiveTask(): ProcessingTask | undefined {
    return this.cachedActiveTask;
  }

  private loadAssets(): void {
    if (this.outputs && Object.keys(this.outputs).length > 0) {
      const outputsObj = this.outputs as Record<string, string | undefined>;
      const assets = this.mapOutputsToAssets(outputsObj);
      this.assets.set(assets);
      this.updateSelectableAssets(assets);
    } else if (this.projectId && this.taskId) {
      this.resultsService.getTaskAssets(this.projectId, this.taskId).subscribe({
        next: (assets) => {
          this.assets.set(assets);
          this.updateSelectableAssets(assets);
        },
        error: (err) => console.error('Failed to load assets:', err)
      });
    }
  }

  private loadWarnings(): void {
    if (!this.nodeodmTaskId) return;

    this.loadingWarnings.set(true);
    this.resultsService.getTaskWarnings(this.nodeodmTaskId).subscribe({
      next: (warnings) => {
        this.taskWarnings.set(warnings);
        this.loadingWarnings.set(false);
      },
      error: (err) => {
        console.error('Failed to load warnings:', err);
        this.loadingWarnings.set(false);
      }
    });
  }

  private updateSelectableAssets(assets: AssetInfo[]): void {
    const selectable: SelectableAsset[] = assets.map(asset => ({
      ...asset,
      selected: false,
      size: this.getEstimatedSize(asset.name)
    }));
    console.log('Selectable assets updated:', selectable);
    this.selectableAssets.set(selectable);
  }

  private getEstimatedSize(assetName: string): string {
    // Estima tamanho baseado na extensão e tipo de arquivo
    if (assetName.includes('orthophoto') || assetName.includes('.tif')) return '~5-50 MB';
    if (assetName.includes('dsm') || assetName.includes('dtm')) return '~2-20 MB';
    if (assetName.includes('georeferenced_model') || assetName.includes('.laz')) return '~10-100 MB';
    if (assetName.includes('textured_model') || assetName.includes('model')) return '~5-50 MB';
    if (assetName.includes('report') || assetName.includes('.pdf')) return '~1-5 MB';
    if (assetName.includes('all.zip')) return '~100-500 MB';
    return '';
  }

  private mapOutputsToAssets(outputs: Record<string, string | undefined>): AssetInfo[] {
    console.log('🔍 Mapping outputs to assets:', outputs);
    const assets: AssetInfo[] = [];
    
    // Mapeia os nomes de arquivo reais do NodeODM para metadados de exibição
    const fileMapping: { 
      pattern: RegExp; 
      icon: string; 
      displayName: string; 
      description: string;
      extension: string;
      previewable: boolean;
    }[] = [
      {
        pattern: /^orthophoto(.*\.tif)?$/i,
        icon: '🗺️',
        displayName: 'Ortofoto',
        description: 'Mapa ortorretificado georreferenciado',
        extension: '.tif',
        previewable: true
      },
      {
        pattern: /^dsm(\.tif)?$/i,
        icon: '🏔️',
        displayName: 'DSM (Modelo Digital de Superfície)',
        description: 'Modelo de elevação incluindo objetos',
        extension: '.tif',
        previewable: true
      },
      {
        pattern: /^dtm(\.tif)?$/i,
        icon: '🏞️',
        displayName: 'DTM (Modelo Digital de Terreno)',
        description: 'Modelo de elevação do terreno',
        extension: '.tif',
        previewable: true
      },
      {
        pattern: /^(pointCloud|georeferenced_model\.laz)$/i,
        icon: '☁️',
        displayName: 'Nuvem de Pontos',
        description: 'Nuvem de pontos georreferenciada (LAZ)',
        extension: '.laz',
        previewable: false
      },
      {
        pattern: /^(model3d|textured_model\.zip)$/i,
        icon: '🧊',
        displayName: 'Modelo 3D Texturizado',
        description: 'Modelo 3D com texturas (OBJ)',
        extension: '.zip',
        previewable: false
      },
      {
        pattern: /^(report|odm_report\.pdf)$/i,
        icon: '📄',
        displayName: 'Relatório ODM',
        description: 'Relatório de processamento detalhado',
        extension: '.pdf',
        previewable: true
      },
      {
        pattern: /^all\.zip$/i,
        icon: '📦',
        displayName: 'Pacote Completo',
        description: 'Todos os resultados em um único arquivo',
        extension: '.zip',
        previewable: false
      }
    ];

    for (const [fileName, url] of Object.entries(outputs)) {
      // Ignora metadados como 'all.zip_size'
      if (!url || fileName.includes('_size')) continue;

      console.log(`📄 Processing file: "${fileName}"`);

      // Encontra o mapeamento correspondente
      const mapping = fileMapping.find(m => {
        const matches = m.pattern.test(fileName);
        console.log(`  Pattern ${m.pattern} matches "${fileName}": ${matches}`);
        return matches;
      });
      
      if (mapping) {
        console.log(`✅ Matched with icon: ${mapping.icon}, displayName: ${mapping.displayName}`);
        // Extrai extensão real do nome do arquivo
        const actualExt = fileName.substring(fileName.lastIndexOf('.'));
        
        // NÃO usa URLs do backend - elas estão no formato antigo
        // Deixa undefined para forçar uso de getChunkAssetDownloadUrl
        assets.push({
          name: fileName,
          icon: mapping.icon,
          displayName: mapping.displayName,
          description: mapping.description,
          extension: actualExt,
          downloadUrl: '',  // Não usa URL do backend (formato antigo)
          previewUrl: undefined,
          available: true
        });
      } else {
        console.log(`❌ No mapping found for "${fileName}" - using default icon 📎`);
        // Asset desconhecido - adiciona com valores padrão
        const ext = fileName.substring(fileName.lastIndexOf('.')) || '';
        assets.push({
          name: fileName,
          icon: '📎',
          displayName: fileName,
          description: 'Arquivo de resultado',
          extension: ext,
          downloadUrl: '',  // Não usa URL do backend (formato antigo)
          previewUrl: undefined,
          available: true
        });
      }
    }

    console.log('Mapped assets from outputs:', assets);
    return assets;
  }

  private getExtension(assetName: string): string {
    // Extrai a extensão do nome do arquivo
    const lastDot = assetName.lastIndexOf('.');
    return lastDot > -1 ? assetName.substring(lastDot) : '';
  }

  // Download handlers
  downloadAsset(asset: SelectableAsset): void {
    // Sempre usa o método correto com projectId e chunkId
    if (this.projectId && this.taskId) {
      const url = this.resultsService.getChunkAssetDownloadUrl(this.projectId, this.taskId, asset.name);
      console.log('📥 Download URL:', url);
      this.resultsService.downloadAsset(url, asset.name);
    }
  }

  downloadSelected(selected: SelectableAsset[]): void {
    selected.forEach((asset, index) => {
      setTimeout(() => this.downloadAsset(asset), index * 500);
    });
  }

  downloadAllZip(): void {
    if (this.nodeodmTaskId) {
      const url = `/nodeodm-api/task/${this.nodeodmTaskId}/download/all.zip`;
      this.resultsService.downloadAsset(url, 'all.zip');
    }
  }

  // Preview handlers
  previewAsset(asset: SelectableAsset): void {
    // Sempre usa o método correto com projectId e chunkId
    if (!this.projectId || !this.taskId) {
      this.previewType.set('message');
      this.previewMessage.set('Informações de projeto/chunk não disponíveis.');
      this.previewLoading.set(false);
      return;
    }
    
    const url = this.resultsService.getChunkAssetDownloadUrl(this.projectId, this.taskId, asset.name);
    console.log('👁️ Preview URL:', url);

    this.previewOpen.set(true);
    this.previewTitle.set(asset.displayName);
    this.previewMessage.set('');
    this.previewError.set(null);
    this.previewPdfUrl.set(null);
    this.previewDownloadUrl.set(url || null);
    this.previewLoading.set(true);

    if (!url) {
      this.previewType.set('message');
      this.previewMessage.set('Arquivo indisponível para visualização.');
      this.previewLoading.set(false);
      return;
    }

    if (asset.extension.toLowerCase() === '.pdf') {
      this.previewType.set('pdf');
      void this.renderPdfPreview(url);
      return;
    }

    if (asset.extension.toLowerCase() === '.tif' || asset.extension.toLowerCase() === '.tiff') {
      this.previewType.set('tiff');
      void this.renderTiffPreview(url);
      return;
    }

    this.previewType.set('message');
    this.previewMessage.set('Pré-visualização não disponível para este tipo de arquivo.');
    this.previewLoading.set(false);
  }

  closePreview(): void {
    this.previewOpen.set(false);
    this.previewLoading.set(false);
    if (this.previewObjectUrl) {
      URL.revokeObjectURL(this.previewObjectUrl);
      this.previewObjectUrl = null;
    }
  }

  private async renderPdfPreview(url: string): Promise<void> {
    try {
      const blob = await firstValueFrom(this.http.get(url, { responseType: 'blob' }));
      if (this.previewObjectUrl) {
        URL.revokeObjectURL(this.previewObjectUrl);
      }
      this.previewObjectUrl = URL.createObjectURL(blob);
      this.previewPdfUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.previewObjectUrl));
      this.previewLoading.set(false);
    } catch (error) {
      this.previewError.set('Não foi possível gerar a visualização.');
      this.previewLoading.set(false);
    }
  }

  private async renderTiffPreview(url: string): Promise<void> {
    try {
      const buffer = await firstValueFrom(this.http.get(url, { responseType: 'arraybuffer' }));
      const tiff = await fromArrayBuffer(buffer);
      const image = await tiff.getImage();

      const maxWidth = 1024;
      const scale = Math.min(1, maxWidth / image.getWidth());
      const width = Math.max(1, Math.floor(image.getWidth() * scale));
      const height = Math.max(1, Math.floor(image.getHeight() * scale));

      const raster = await image.readRasters({ width, height });

      this.previewLoading.set(false);
      const canvas = await this.waitForCanvas();

      canvas.width = width;
      canvas.height = height;

      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Canvas context não disponível');

      const imageData = ctx.createImageData(width, height);
      const data = imageData.data;
      const bands = Array.isArray(raster) ? raster : [raster];

      if (bands.length >= 3) {
        const r = bands[0] as Uint8Array | Uint16Array | Float32Array;
        const g = bands[1] as Uint8Array | Uint16Array | Float32Array;
        const b = bands[2] as Uint8Array | Uint16Array | Float32Array;
        for (let i = 0, j = 0; i < r.length; i++, j += 4) {
          data[j] = this.normalizeSample(r[i]);
          data[j + 1] = this.normalizeSample(g[i]);
          data[j + 2] = this.normalizeSample(b[i]);
          data[j + 3] = 255;
        }
      } else {
        const gray = bands[0] as Uint8Array | Uint16Array | Float32Array;
        for (let i = 0, j = 0; i < gray.length; i++, j += 4) {
          const value = this.normalizeSample(gray[i]);
          data[j] = value;
          data[j + 1] = value;
          data[j + 2] = value;
          data[j + 3] = 255;
        }
      }

      ctx.putImageData(imageData, 0, 0);
    } catch (error) {
      this.previewError.set('Erro ao processar o arquivo TIFF.');
      this.previewLoading.set(false);
    }
  }

  private async waitForCanvas(maxAttempts: number = 50, delayMs: number = 20): Promise<HTMLCanvasElement> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      if (attempt === 0) this.cdr.detectChanges();
      
      const canvas = this.previewCanvas?.nativeElement;
      if (canvas) return canvas;
      
      await new Promise<void>((resolve) => setTimeout(resolve, delayMs));
    }
    throw new Error('Canvas não disponível');
  }

  private normalizeSample(value: number): number {
    if (value <= 255) return Math.round(value);
    if (value <= 65535) return Math.round((value / 65535) * 255);
    return Math.round(Math.max(0, Math.min(1, value)) * 255);
  }
}
