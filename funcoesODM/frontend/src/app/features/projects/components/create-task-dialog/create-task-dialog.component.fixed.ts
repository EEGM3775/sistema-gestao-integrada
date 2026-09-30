import { Component, inject, output, signal, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TaskService, CreateTaskRequest } from '../../services/task.service';

interface ODMOptions {
  orthophoto: boolean;
  dsm: boolean;
  dtm: boolean;
  pointCloud: boolean;
  model3d: boolean;
  report: boolean;

  featureQuality: 'ultra' | 'high' | 'medium' | 'low' | 'lowest';
  pcQuality: 'ultra' | 'high' | 'medium' | 'low' | 'lowest';
  meshSize: number;
  meshOctreeDepth: number;

  orthophotoResolution: number;
  demResolution: number;

  minNumFeatures: number;
  matcher: 'flann' | 'bruteforce';
  depthMapQuality: 'ultra' | 'high' | 'medium' | 'low' | 'lowest';

  useGcp: boolean;
  gcpAccuracy: number;

  fastOrthophoto: boolean;
  autoMask: boolean;
  radiometricCalibration: 'none' | 'camera' | 'camera+sun';

  skipModel: boolean;
  ignoreGsd: boolean;

  maxConcurrency: number;
  split: number;
  splitOverlap: number;
  merge: 'all' | 'orthophoto' | 'none';

  cameraLens: 'auto' | 'perspective' | 'brown' | 'fisheye' | 'spherical';
  rollingShutter: boolean;
  rollingShutterReadout: number;

  pcClassify: boolean;
  pcGeometric: boolean;
  pcFilter: number;
  pcRectify: boolean;
  pcSample: number;

  crop: number;
  forceGps: boolean;

  orthophotoPng: boolean;
  orthophotoKmz: boolean;
  tiles: boolean;
  cog: boolean;
  tiles3d: boolean;
  demEuclideanMap: boolean;

  texturingDataTerm: 'gmi' | 'area';
  texturingSkipGlobalSeam: boolean;
  texturingSkipLocalSeam: boolean;
  texturingKeepUnseenFaces: boolean;

  resizeTo: number;
  useFixedCameraParams: boolean;
  optimizeDiskSpace: boolean;

  verbose: boolean;
  time: boolean;
  debug: boolean;

  noGpu: boolean;

  // Additional NodeODM options
  align: boolean;
  autoBoundaryDistance: number;
  bgRemoval: boolean;
  boundary: string;
  buildOverviews: boolean;
  cameras: string;
  copyTo: string;
  dem: boolean;
  demDecimation: number;
  demGapfillSteps: number;
  endWith: string;
  featureType: string;
  geo: boolean;
  gltf: boolean;
  gpsAccuracy: number;
  gpsZOffset: number;
  help: boolean;
  matcherNeighbors: number;
  matcherOrder: string;
  mergeSkipBlending: boolean;
  orthophotoCompression: string;
  orthophotoCutline: boolean;
  orthophotoNoTiled: boolean;
  pcCopc: boolean;
  pcCsv: boolean;
  pcEpt: boolean;
  pcLas: boolean;
  pcSkipGeometric: boolean;
  primaryBand: string;
  projectPath: string;
  rerun: boolean;
  rerunAll: boolean;
  rerunFrom: string;
  sfmAlgorithm: string;
  sfmNoPartial: boolean;
  skipBandAlignment: boolean;
  skipOrthophoto: boolean;
  skyRemoval: boolean;
  smCluster: boolean;
  smNoAlign: boolean;
  smrf: boolean;
  smrfScalar: number;
  smrfSlope: number;
  smrfThreshold: number;
  smrfWindow: number;
  splitImageGroups: number;
  texturingOutlierRemovalType: string;
  texturingSingleMaterial: boolean;
  texturingToneMapping: string;
  useExif: boolean;
  useHybridBundleAdjustment: boolean;
  version: boolean;
  videoLimit: number;
  videoResolution: number;
}

@Component({
  selector: 'app-create-task-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="modal-overlay" (click)="onBackdropClick($event)">
      <div class="modal-content">
        <div class="modal-header">
          <h2>Nova Tarefa de Processamento</h2>
          <button class="close-btn" (click)="close()">✕</button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label for="taskName">Nome da Tarefa</label>
            <input type="text" id="taskName" [(ngModel)]="taskName" placeholder="Ex: Ortomosaico Área 1" />
          </div>

          <div class="form-group">
            <label for="preset">Preset de Configuração</label>
            <select id="preset" [(ngModel)]="selectedPreset" (change)="applyPreset()">
              <option value="fast">⚡ Rápido (Preview)</option>
              <option value="default">⚖️ Padrão (Balanceado)</option>
              <option value="highQuality">🎯 Alta Qualidade</option>
              <option value="3dModel">🎲 Modelo 3D Detalhado</option>
              <option value="agriculture">🌾 Agricultura (NDVI)</option>
              <option value="survey">📐 Topografia (Alta Precisão)</option>
              <option value="custom">⚙️ Personalizado</option>
            </select>
          </div>

          <div class="form-section">
            <h3>Produtos a Gerar</h3>
            <div class="checkbox-grid">
              <label class="checkbox-item"><input type="checkbox" [(ngModel)]="options.orthophoto" /><span>📷 Ortofoto <span class="help-icon" title="Gera ortofoto georreferenciada.">?</span></span></label>
              <label class="checkbox-item"><input type="checkbox" [(ngModel)]="options.dsm" /><span>🗻 DSM (Modelo Digital de Superfície) <span class="help-icon" title="Gera modelo digital de superfície.">?</span></span></label>
              <label class="checkbox-item"><input type="checkbox" [(ngModel)]="options.dtm" /><span>📊 DTM (Modelo Digital de Terreno) <span class="help-icon" title="Gera modelo digital do terreno (sem objetos).">?</span></span></label>
              <label class="checkbox-item"><input type="checkbox" [(ngModel)]="options.pointCloud" /><span>☁️ Nuvem de Pontos <span class="help-icon" title="Gera nuvem de pontos densa.">?</span></span></label>
              <label class="checkbox-item"><input type="checkbox" [(ngModel)]="options.model3d" /><span>🎲 Modelo 3D Texturizado <span class="help-icon" title="Gera malha 3D com textura.">?</span></span></label>
              <label class="checkbox-item" [class.warning]="options.report">
                <input type="checkbox" [(ngModel)]="options.report" />
                <span>📄 Relatório PDF <span class="help-icon" title="Gera relatório do processamento.">?</span></span>
                @if (options.report) {
                  <span class="warning-badge" title="ODM 3.5.6 tem um bug que pode causar falha na geração do relatório. Desmarque se o processamento falhar.">⚠️</span>
                }
              </label>
            </div>
          </div>

          <div class="form-section">
            <div class="advanced-actions">
              <button class="btn-advanced" type="button" (click)="showAdvancedModal = true">⚙️ Opções Avançadas</button>
              <small>Configurações avançadas do processamento NodeODM</small>
            </div>
          </div>

          @if (showAdvancedModal) {
            <div class="advanced-overlay" (click)="onAdvancedBackdropClick($event)">
              <div class="advanced-modal">
                <div class="advanced-header">
                  <h3>Opções Avançadas do Processamento</h3>
                  <button class="close-btn" (click)="showAdvancedModal = false">✕</button>
                </div>
                <div class="advanced-body">
                  <div class="advanced-options">
                    <div class="options-group">
                      <h4>⚡ Processamento Paralelo</h4>
                      <div class="form-row">
                        <div class="form-group">
                          <label for="maxConcurrency">Máx. Processos Paralelos <span class="help-icon" title="Define limite de processos simultâneos.">?</span></label>
                          <input type="number" id="maxConcurrency" [(ngModel)]="options.maxConcurrency" min="1" max="64" />
                          <small>0 = auto (núm. CPUs)</small>
                        </div>
                        <div class="form-group">
                          <label for="split">Dividir Dataset <span class="help-icon" title="Divide o dataset em grupos para processar em partes.">?</span></label>
                          <input type="number" id="split" [(ngModel)]="options.split" min="0" max="999999" />
                          <small>0 = não dividir, >0 = núm. grupos</small>
                        </div>
                      </div>
                      @if (options.split > 0) {
                        <div class="form-row">
                          <div class="form-group">
                            <label for="splitOverlap">Sobreposição Split (m) <span class="help-icon" title="Sobreposição entre splits em metros.">?</span></label>
                            <input type="number" id="splitOverlap" [(ngModel)]="options.splitOverlap" min="0" max="1000" step="5" />
                          </div>
                          <div class="form-group">
                            <label for="merge">Tipo de Merge <span class="help-icon" title="Define o que será mesclado após splits.">?</span></label>
                            <select id="merge" [(ngModel)]="options.merge">
                              <option value="all">Tudo</option>
                              <option value="orthophoto">Apenas Ortofoto</option>
                              <option value="none">Nenhum</option>
                            </select>
                          </div>
                        </div>
                      }
                    </div>

                    <div class="options-group">
                      <h4>☁️ Nuvem de Pontos Avançado</h4>
                      <div class="checkbox-grid-small">
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcClassify" /><span>Classificar automaticamente (chão, vegetação) <span class="help-icon" title="Classifica automaticamente pontos (ground/vegetação).">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcGeometric" /><span>Filtro geométrico <span class="help-icon" title="Aplica filtro geométrico na nuvem de pontos.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcRectify" /><span>Retificar nuvem de pontos <span class="help-icon" title="Corrige a nuvem de pontos com base no sistema de coordenadas.">?</span></span></label>
                      </div>
                      <div class="form-row">
                        <div class="form-group"><label for="pcFilter">Filtro de Ruído (0-100) <span class="help-icon" title="Remove ruído na nuvem de pontos.">?</span></label><input type="number" id="pcFilter" [(ngModel)]="options.pcFilter" min="0" max="100" step="5" /></div>
                        <div class="form-group"><label for="pcSample">Amostragem (0-1) <span class="help-icon" title="Reduz densidade por amostragem.">?</span></label><input type="number" id="pcSample" [(ngModel)]="options.pcSample" min="0" max="1" step="0.1" /><small>0 = sem amostragem</small></div>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>📷 Câmera & Calibração</h4>
                      <div class="form-group">
                        <label for="cameraLens">Tipo de Lente <span class="help-icon" title="Define o modelo de lente para calibração.">?</span></label>
                        <select id="cameraLens" [(ngModel)]="options.cameraLens">
                          <option value="auto">Auto (Detectar)</option>
                          <option value="perspective">Perspectiva</option>
                          <option value="brown">Brown (Distorção)</option>
                          <option value="fisheye">Fisheye/Olho de Peixe</option>
                          <option value="spherical">Esférica/360°</option>
                        </select>
                      </div>
                      <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.rollingShutter" /><span>Corrigir Rolling Shutter <span class="help-icon" title="Corrige distorções por shutter rolante.">?</span></span></label>
                      @if (options.rollingShutter) {
                        <div class="form-group" style="margin-top: 12px;">
                          <label for="rollingShutterReadout">Tempo de Readout (ms) <span class="help-icon" title="Tempo de leitura do sensor (ms).">?</span></label>
                          <input type="number" id="rollingShutterReadout" [(ngModel)]="options.rollingShutterReadout" min="0" max="100" step="0.1" />
                        </div>
                      }
                      <label class="checkbox-inline" style="margin-top: 12px;"><input type="checkbox" [(ngModel)]="options.useFixedCameraParams" /><span>Usar parâmetros fixos de câmera <span class="help-icon" title="Evita otimização de parâmetros de câmera.">?</span></span></label>
                    </div>

                    <div class="options-group">
                      <h4>✂️ Recorte & Limites</h4>
                      <div class="form-row">
                        <div class="form-group"><label for="crop">Crop (m) <span class="help-icon" title="Recorta a borda do modelo em metros.">?</span></label><input type="number" id="crop" [(ngModel)]="options.crop" min="0" max="100" step="1" /><small>0 = sem recorte</small></div>
                        <div class="form-group"><label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.forceGps" /><span>Forçar GPS <span class="help-icon" title="Força uso de posições GPS mesmo se inconsistentes.">?</span></span></label></div>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>📦 Formatos de Saída</h4>
                      <div class="checkbox-grid-small">
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.orthophotoPng" /><span>Ortofoto PNG <span class="help-icon" title="Exporta ortofoto em PNG.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.orthophotoKmz" /><span>Ortofoto KMZ <span class="help-icon" title="Exporta ortofoto em KMZ.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.tiles" /><span>Tiles 2D (Leaflet) <span class="help-icon" title="Gera tiles 2D para web.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.cog" /><span>COG (Cloud Optimized GeoTIFF) <span class="help-icon" title="Exporta como COG.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.tiles3d" /><span>3D Tiles (Cesium) <span class="help-icon" title="Exporta tiles 3D (Cesium).">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.demEuclideanMap" /><span>Mapa Euclidiano DEM <span class="help-icon" title="Gera mapa euclidiano a partir do DEM.">?</span></span></label>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>🎨 Texturização Avançada</h4>
                      <div class="form-group">
                        <label for="texturingDataTerm">Data Term <span class="help-icon" title="Método de seleção de dados para texturização.">?</span></label>
                        <select id="texturingDataTerm" [(ngModel)]="options.texturingDataTerm">
                          <option value="gmi">GMI (padrão)</option>
                          <option value="area">Área</option>
                        </select>
                      </div>
                      <div class="checkbox-grid-small">
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.texturingSkipGlobalSeam" /><span>Desativar nivelamento global <span class="help-icon" title="Desativa ajuste global de costuras.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.texturingSkipLocalSeam" /><span>Desativar nivelamento local <span class="help-icon" title="Desativa ajuste local de costuras.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.texturingKeepUnseenFaces" /><span>Manter faces não vistas <span class="help-icon" title="Mantém faces sem observação nas texturas.">?</span></span></label>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>🚀 GPU & Aceleração</h4>
                      <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.noGpu" /><span>Desabilitar GPU (usar apenas CPU) <span class="help-icon" title="Força processamento somente em CPU.">?</span></span></label>
                    </div>

                    <div class="options-group">
                      <h4>🐛 Debug & Monitoramento</h4>
                      <div class="checkbox-grid-small">
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.verbose" /><span>Saída verbosa (detalhada) <span class="help-icon" title="Aumenta o nível de logs.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.time" /><span>Mostrar tempos de execução <span class="help-icon" title="Exibe tempo por etapa.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.debug" /><span>Modo debug (salvar arquivos intermediários) <span class="help-icon" title="Gera arquivos intermediários para análise.">?</span></span></label>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>Qualidade</h4>
                      <div class="form-row">
                        <div class="form-group"><label for="featureQuality">Detecção de Features <span class="help-icon" title="Define qualidade da detecção de features.">?</span></label><select id="featureQuality" [(ngModel)]="options.featureQuality"><option value="ultra">Ultra (mais lento)</option><option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option><option value="lowest">Mínima (mais rápido)</option></select></div>
                        <div class="form-group"><label for="pcQuality">Qualidade da Nuvem de Pontos <span class="help-icon" title="Define densidade/qualidade da nuvem de pontos.">?</span></label><select id="pcQuality" [(ngModel)]="options.pcQuality"><option value="ultra">Ultra</option><option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option><option value="lowest">Mínima</option></select></div>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>🔍 Features & Depth Maps</h4>
                      <div class="form-row">
                        <div class="form-group"><label for="minNumFeatures">Min. de Features <span class="help-icon" title="Mínimo de features por imagem.">?</span></label><input type="number" id="minNumFeatures" [(ngModel)]="options.minNumFeatures" min="500" max="50000" step="500" /><small>0 = auto</small></div>
                        <div class="form-group"><label for="matcher">Matcher <span class="help-icon" title="Algoritmo de correspondência de features.">?</span></label><select id="matcher" [(ngModel)]="options.matcher"><option value="flann">FLANN (padrão)</option><option value="bruteforce">Brute Force</option></select></div>
                      </div>
                      <div class="form-group"><label for="depthMapQuality">Qualidade do Depth Map <span class="help-icon" title="Define a qualidade dos depth maps.">?</span></label><select id="depthMapQuality" [(ngModel)]="options.depthMapQuality"><option value="ultra">Ultra</option><option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option><option value="lowest">Mínima</option></select></div>
                    </div>

                    <div class="options-group">
                      <h4>Resolução</h4>
                      <div class="form-row">
                        <div class="form-group"><label for="orthophotoResolution">Ortofoto (cm/pixel) <span class="help-icon" title="Define resolução da ortofoto.">?</span></label><input type="number" id="orthophotoResolution" [(ngModel)]="options.orthophotoResolution" min="1" max="100" step="0.5" /><small>0 = máxima resolução</small></div>
                        <div class="form-group"><label for="demResolution">DEM (cm/pixel) <span class="help-icon" title="Define resolução do DEM.">?</span></label><input type="number" id="demResolution" [(ngModel)]="options.demResolution" min="1" max="100" step="0.5" /></div>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>Modelo 3D</h4>
                      <div class="form-row">
                        <div class="form-group"><label for="meshSize">Tamanho da Malha (faces) <span class="help-icon" title="Número de faces da malha.">?</span></label><input type="number" id="meshSize" [(ngModel)]="options.meshSize" min="50000" max="1000000" step="50000" /></div>
                        <div class="form-group"><label for="meshOctreeDepth">Profundidade Octree <span class="help-icon" title="Profundidade da octree para reconstrução.">?</span></label><input type="number" id="meshOctreeDepth" [(ngModel)]="options.meshOctreeDepth" min="6" max="14" /></div>
                      </div>
                      <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.skipModel" /><span>Pular geração de modelo 3D <span class="help-icon" title="Ignora criação da malha 3D.">?</span></span></label>
                    </div>

                    <div class="options-group">
                      <h4>Pontos de Controle (GCP)</h4>
                      <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.useGcp" /><span>Usar arquivo GCP <span class="help-icon" title="Habilita uso de pontos de controle.">?</span></span></label>
                      @if (options.useGcp) {
                        <div class="form-group" style="margin-top: 12px;"><label for="gcpAccuracy">Precisão GCP (metros) <span class="help-icon" title="Precisão estimada dos GCPs.">?</span></label><input type="number" id="gcpAccuracy" [(ngModel)]="options.gcpAccuracy" min="0.001" max="10" step="0.001" /></div>
                      }
                    </div>

                    <div class="options-group">
                      <h4>Otimização</h4>
                      <div class="checkbox-grid-small">
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.fastOrthophoto" /><span>Ortofoto Rápida (menor qualidade) <span class="help-icon" title="Acelera ortofoto com menor qualidade.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.autoMask" /><span>Auto-mascaramento de bordas <span class="help-icon" title="Remove bordas automaticamente.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.ignoreGsd" /><span>Ignorar GSD (processar todos os pixels) <span class="help-icon" title="Ignora GSD e processa resolução total.">?</span></span></label>
                      </div>
                      <div class="form-group" style="margin-top: 12px;"><label for="radiometricCalibration">Calibração Radiométrica <span class="help-icon" title="Aplica calibração radiométrica (multiespectral).">?</span></label><select id="radiometricCalibration" [(ngModel)]="options.radiometricCalibration"><option value="none">Nenhuma</option><option value="camera">Apenas Câmera</option><option value="camera+sun">Câmera + Sol</option></select></div>
                    </div>

                    <div class="options-group">
                      <h4>💾 Otimização & Memória</h4>
                      <div class="form-row">
                        <div class="form-group"><label for="resizeTo">Resize (px) <span class="help-icon" title="Redimensiona imagens antes do processamento.">?</span></label><input type="number" id="resizeTo" [(ngModel)]="options.resizeTo" min="0" max="10000" step="100" /><small>0 = tamanho original</small></div>
                        <div class="form-group"><label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.optimizeDiskSpace" /><span>Otimizar uso de disco <span class="help-icon" title="Reduz uso de disco com cache mínimo.">?</span></span></label></div>
                      </div>
                    </div>

                    <div class="options-group">
                      <h4>🔧 Opções adicionais NodeODM</h4>

                      <div class="form-row">
                        <div class="form-group"><label for="boundary">Boundary (arquivo/geojson) <span class="help-icon" title="Define um arquivo de limite para recortar a área de processamento.">?</span></label><input type="text" id="boundary" [(ngModel)]="options.boundary" placeholder="/caminho/limite.geojson" /></div>
                        <div class="form-group"><label for="autoBoundaryDistance">Auto Boundary Distance <span class="help-icon" title="Gera limite automático baseado na distância (metros).">?</span></label><input type="number" id="autoBoundaryDistance" [(ngModel)]="options.autoBoundaryDistance" min="0" step="1" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="cameras">Câmeras (arquivo) <span class="help-icon" title="Arquivo com parâmetros de câmera (prioriza calibração manual).">?</span></label><input type="text" id="cameras" [(ngModel)]="options.cameras" placeholder="/caminho/cameras.json" /></div>
                        <div class="form-group"><label for="copyTo">Copy To <span class="help-icon" title="Caminho para copiar resultados ao final do processamento.">?</span></label><input type="text" id="copyTo" [(ngModel)]="options.copyTo" placeholder="/caminho/saida" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="projectPath">Project Path <span class="help-icon" title="Define o diretório base do projeto no NodeODM.">?</span></label><input type="text" id="projectPath" [(ngModel)]="options.projectPath" placeholder="/caminho/projeto" /></div>
                        <div class="form-group"><label for="primaryBand">Primary Band <span class="help-icon" title="Define a banda principal em datasets multiespectrais.">?</span></label><input type="text" id="primaryBand" [(ngModel)]="options.primaryBand" placeholder="red/green/blue/nir..." /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="featureType">Feature Type <span class="help-icon" title="Algoritmo de detecção de features (ex: sift/akaze).">?</span></label><input type="text" id="featureType" [(ngModel)]="options.featureType" placeholder="sift/akaze..." /></div>
                        <div class="form-group"><label for="matcherNeighbors">Matcher Neighbors <span class="help-icon" title="Número de vizinhos no matching (melhora robustez, aumenta custo).">?</span></label><input type="number" id="matcherNeighbors" [(ngModel)]="options.matcherNeighbors" min="0" step="1" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="matcherOrder">Matcher Order <span class="help-icon" title="Ordem de pareamento entre imagens (impacta velocidade/robustez).">?</span></label><input type="text" id="matcherOrder" [(ngModel)]="options.matcherOrder" placeholder="order/nearest..." /></div>
                        <div class="form-group"><label for="sfmAlgorithm">SfM Algorithm <span class="help-icon" title="Algoritmo de Structure-from-Motion.">?</span></label><input type="text" id="sfmAlgorithm" [(ngModel)]="options.sfmAlgorithm" placeholder="incremental/triangulation..." /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="endWith">End With <span class="help-icon" title="Interrompe o processamento após a etapa indicada.">?</span></label><input type="text" id="endWith" [(ngModel)]="options.endWith" placeholder="dataset, odm_filterpoints..." /></div>
                        <div class="form-group"><label for="rerunFrom">Rerun From <span class="help-icon" title="Reprocessa a partir de uma etapa específica.">?</span></label><input type="text" id="rerunFrom" [(ngModel)]="options.rerunFrom" placeholder="dataset, odm_meshing..." /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="gpsAccuracy">GPS Accuracy (m) <span class="help-icon" title="Precisão estimada do GPS em metros.">?</span></label><input type="number" id="gpsAccuracy" [(ngModel)]="options.gpsAccuracy" min="0" step="0.1" /></div>
                        <div class="form-group"><label for="gpsZOffset">GPS Z Offset (m) <span class="help-icon" title="Offset vertical aplicado às altitudes GPS.">?</span></label><input type="number" id="gpsZOffset" [(ngModel)]="options.gpsZOffset" step="0.1" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="demDecimation">DEM Decimation <span class="help-icon" title="Reduz densidade do DEM para diminuir tamanho.">?</span></label><input type="number" id="demDecimation" [(ngModel)]="options.demDecimation" min="0" step="1" /></div>
                        <div class="form-group"><label for="demGapfillSteps">DEM Gapfill Steps <span class="help-icon" title="Número de iterações para preencher lacunas no DEM.">?</span></label><input type="number" id="demGapfillSteps" [(ngModel)]="options.demGapfillSteps" min="0" step="1" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="splitImageGroups">Split Image Groups <span class="help-icon" title="Divide grupos de imagens por sensor/câmera.">?</span></label><input type="number" id="splitImageGroups" [(ngModel)]="options.splitImageGroups" min="0" step="1" /></div>
                        <div class="form-group"><label for="videoLimit">Video Limit <span class="help-icon" title="Limita o número de frames extraídos de vídeo.">?</span></label><input type="number" id="videoLimit" [(ngModel)]="options.videoLimit" min="0" step="1" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="videoResolution">Video Resolution <span class="help-icon" title="Define resolução dos frames extraídos do vídeo.">?</span></label><input type="number" id="videoResolution" [(ngModel)]="options.videoResolution" min="0" step="1" /></div>
                        <div class="form-group"><label for="orthophotoCompression">Ortho Compression <span class="help-icon" title="Algoritmo de compressão da ortofoto.">?</span></label><input type="text" id="orthophotoCompression" [(ngModel)]="options.orthophotoCompression" placeholder="lzw/jpeg/deflate" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="texturingOutlierRemovalType">Texturing Outlier Removal <span class="help-icon" title="Método de remoção de outliers na texturização.">?</span></label><input type="text" id="texturingOutlierRemovalType" [(ngModel)]="options.texturingOutlierRemovalType" placeholder="none/gaussian..." /></div>
                        <div class="form-group"><label for="texturingToneMapping">Texturing Tone Mapping <span class="help-icon" title="Mapeamento de tons na textura final.">?</span></label><input type="text" id="texturingToneMapping" [(ngModel)]="options.texturingToneMapping" placeholder="none/gamma..." /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="smrfScalar">SMRF Scalar <span class="help-icon" title="Parâmetro do filtro SMRF para DTM.">?</span></label><input type="number" id="smrfScalar" [(ngModel)]="options.smrfScalar" min="0" step="0.1" /></div>
                        <div class="form-group"><label for="smrfSlope">SMRF Slope <span class="help-icon" title="Inclinação máxima para classificação SMRF.">?</span></label><input type="number" id="smrfSlope" [(ngModel)]="options.smrfSlope" min="0" step="0.1" /></div>
                      </div>

                      <div class="form-row">
                        <div class="form-group"><label for="smrfThreshold">SMRF Threshold <span class="help-icon" title="Limiar do filtro SMRF.">?</span></label><input type="number" id="smrfThreshold" [(ngModel)]="options.smrfThreshold" min="0" step="0.1" /></div>
                        <div class="form-group"><label for="smrfWindow">SMRF Window <span class="help-icon" title="Janela do filtro SMRF (tamanho da vizinhança).">?</span></label><input type="number" id="smrfWindow" [(ngModel)]="options.smrfWindow" min="0" step="1" /></div>
                      </div>

                      <div class="checkbox-grid-small">
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.align" /><span>Align <span class="help-icon" title="Executa apenas o alinhamento inicial.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.bgRemoval" /><span>BG Removal <span class="help-icon" title="Remove céu/fundo automaticamente.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.buildOverviews" /><span>Build Overviews <span class="help-icon" title="Gera overviews/pirâmides para rasters.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.dem" /><span>DEM <span class="help-icon" title="Gera DEM adicional.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.geo" /><span>GEO <span class="help-icon" title="Exporta arquivos georreferenciados adicionais.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.gltf" /><span>GLTF <span class="help-icon" title="Exporta modelo 3D em GLTF.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.orthophotoCutline" /><span>Ortho Cutline <span class="help-icon" title="Aplica recorte automático na ortofoto.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.orthophotoNoTiled" /><span>Ortho No Tiled <span class="help-icon" title="Gera ortofoto não dividida em tiles.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.mergeSkipBlending" /><span>Merge Skip Blending <span class="help-icon" title="Desativa blending ao mesclar splits.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcCopc" /><span>PC COPC <span class="help-icon" title="Exporta nuvem de pontos no formato COPC.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcCsv" /><span>PC CSV <span class="help-icon" title="Exporta nuvem de pontos em CSV.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcEpt" /><span>PC EPT <span class="help-icon" title="Exporta nuvem de pontos em EPT (Entwine).">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcLas" /><span>PC LAS <span class="help-icon" title="Exporta nuvem de pontos em LAS/LAZ.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.pcSkipGeometric" /><span>PC Skip Geometric <span class="help-icon" title="Ignora filtro geométrico na nuvem de pontos.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.rerun" /><span>Rerun <span class="help-icon" title="Força reprocessamento completo.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.rerunAll" /><span>Rerun All <span class="help-icon" title="Reprocessa todas as etapas.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.sfmNoPartial" /><span>SfM No Partial <span class="help-icon" title="Desativa reconstrução parcial do SfM.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.skipBandAlignment" /><span>Skip Band Alignment <span class="help-icon" title="Ignora alinhamento de bandas multiespectrais.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.skipOrthophoto" /><span>Skip Orthophoto <span class="help-icon" title="Pula geração da ortofoto.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.skyRemoval" /><span>Sky Removal <span class="help-icon" title="Remove pixels de céu automaticamente.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.smCluster" /><span>SM Cluster <span class="help-icon" title="Habilita execução em cluster (SM).">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.smNoAlign" /><span>SM No Align <span class="help-icon" title="Desativa alinhamento no módulo SM.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.smrf" /><span>SMRF <span class="help-icon" title="Aplica filtro SMRF para DTM.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.texturingSingleMaterial" /><span>Texturing Single Material <span class="help-icon" title="Usa material único na texturização.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.useExif" /><span>Use EXIF <span class="help-icon" title="Usa informações EXIF das imagens.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.useHybridBundleAdjustment" /><span>Use Hybrid Bundle Adjustment <span class="help-icon" title="Ativa bundle adjustment híbrido.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.help" /><span>Help <span class="help-icon" title="Mostra ajuda no processamento.">?</span></span></label>
                        <label class="checkbox-inline"><input type="checkbox" [(ngModel)]="options.version" /><span>Version <span class="help-icon" title="Mostra versão e sai.">?</span></span></label>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="advanced-footer"><button class="btn-cancel" (click)="showAdvancedModal = false">Fechar</button></div>
              </div>
            </div>
          }

          <div class="time-estimate">
            <span class="time-icon">⏱️</span>
            <span>Tempo estimado: <strong>{{ getEstimatedTime() }}</strong></span>
            <small>(baseado na qualidade e número de imagens)</small>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-cancel" (click)="close()">Cancelar</button>
          <button class="btn-submit" (click)="submit()" [disabled]="loading()">
            @if (loading()) {<span class="spinner-small"></span> Criando...} @else {▶️ Iniciar Processamento}
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
    .modal-content { background: #fff; border-radius: 12px; width: 90%; max-width: 700px; max-height: 90vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,.3); }
    .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 24px; border-bottom: 1px solid #e5e7eb; }
    .modal-header h2 { margin: 0; font-size: 18px; font-weight: 600; }
    .close-btn { background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: 4px; }
    .close-btn:hover { background: #f3f4f6; }
    .modal-body { padding: 24px; }
    .form-section { margin-top: 24px; padding-top: 20px; border-top: 1px solid #f3f4f6; }
    .form-section h3 { margin: 0 0 16px; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; }
    .form-group { margin-bottom: 16px; }
    .form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; }
    .form-group input[type="text"], .form-group input[type="number"], .form-group select { width: 100%; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; }
    .form-group small { display: block; margin-top: 4px; font-size: 11px; color: #6b7280; }
    .advanced-actions { display: flex; flex-direction: column; gap: 6px; }
    .btn-advanced { background: #3b82f6; color: #fff; border: none; padding: 10px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; width: fit-content; }
    .advanced-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 1100; padding: 20px; }
    .advanced-modal { background: #fff; border-radius: 12px; width: 95%; max-width: 920px; max-height: 90vh; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,.35); }
    .advanced-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #e5e7eb; }
    .advanced-body { padding: 20px; overflow-y: auto; max-height: calc(90vh - 110px); }
    .advanced-footer { padding: 12px 20px; border-top: 1px solid #e5e7eb; display: flex; justify-content: flex-end; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 600px) { .form-row { grid-template-columns: 1fr; } }
    .checkbox-grid { display: grid; gap: 12px; }
    .checkbox-item { display: flex; align-items: center; gap: 10px; padding: 12px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; cursor: pointer; }
    .checkbox-item.warning { border-color: #f59e0b; background: #fffbeb; }
    .warning-badge { margin-left: auto; cursor: help; font-size: 16px; }
    .help-icon { display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 16px; margin-left: 6px; border-radius: 999px; background: #e5e7eb; color: #374151; font-size: 11px; font-weight: 700; line-height: 1; cursor: help; }
    .help-icon:hover { background: #d1d5db; }
    .checkbox-inline { display: flex; align-items: center; gap: 8px; cursor: pointer; }
    .checkbox-grid-small { display: flex; flex-direction: column; gap: 8px; }
    .options-group { margin-bottom: 20px; padding: 16px; background: #f9fafb; border-radius: 8px; }
    .options-group h4 { margin: 0 0 12px; font-size: 13px; font-weight: 600; color: #374151; }
    .time-estimate { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%); border-radius: 8px; margin-top: 20px; font-size: 14px; color: #1e40af; }
    .modal-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 20px 24px; border-top: 1px solid #e5e7eb; background: #f9fafb; border-radius: 0 0 12px 12px; }
    .btn-cancel { padding: 10px 20px; background: #fff; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; cursor: pointer; }
    .btn-submit { padding: 10px 24px; background: #3b82f6; color: #fff; border: none; border-radius: 6px; font-size: 14px; cursor: pointer; display: flex; align-items: center; gap: 8px; }
    .btn-submit:disabled { opacity: .6; cursor: not-allowed; }
    .spinner-small { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin 1s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
  `]
})
export class CreateTaskDialogComponent {
  private readonly taskService = inject(TaskService);

  projectId = input.required<number>();
  closed = output<void>();
  created = output<void>();

  loading = signal(false);
  taskName = 'Processamento ODM';
  selectedPreset = 'default';
  showAdvancedModal = false;

  options: ODMOptions = {
    orthophoto: true,
    dsm: true,
    dtm: false,
    pointCloud: false,
    model3d: false,
    report: false,
    featureQuality: 'high',
    pcQuality: 'medium',
    meshSize: 200000,
    meshOctreeDepth: 11,
    orthophotoResolution: 5,
    demResolution: 5,
    minNumFeatures: 10000,
    matcher: 'flann',
    depthMapQuality: 'high',
    useGcp: false,
    gcpAccuracy: 0.01,
    fastOrthophoto: false,
    autoMask: true,
    radiometricCalibration: 'none',
    skipModel: false,
    ignoreGsd: false,
    maxConcurrency: 0,
    split: 0,
    splitOverlap: 150,
    merge: 'all',
    cameraLens: 'auto',
    rollingShutter: false,
    rollingShutterReadout: 0,
    pcClassify: false,
    pcGeometric: false,
    pcFilter: 0,
    pcRectify: false,
    pcSample: 0,
    crop: 0,
    forceGps: false,
    orthophotoPng: false,
    orthophotoKmz: false,
    tiles: false,
    cog: false,
    tiles3d: false,
    demEuclideanMap: false,
    texturingDataTerm: 'gmi',
    texturingSkipGlobalSeam: false,
    texturingSkipLocalSeam: false,
    texturingKeepUnseenFaces: false,
    resizeTo: 0,
    useFixedCameraParams: false,
    optimizeDiskSpace: false,
    verbose: false,
    time: false,
    debug: false,
    noGpu: false,
    align: false,
    autoBoundaryDistance: 0,
    bgRemoval: false,
    boundary: '',
    buildOverviews: false,
    cameras: '',
    copyTo: '',
    dem: false,
    demDecimation: 0,
    demGapfillSteps: 0,
    endWith: '',
    featureType: '',
    geo: false,
    gltf: false,
    gpsAccuracy: 0,
    gpsZOffset: 0,
    help: false,
    matcherNeighbors: 0,
    matcherOrder: '',
    mergeSkipBlending: false,
    orthophotoCompression: '',
    orthophotoCutline: false,
    orthophotoNoTiled: false,
    pcCopc: false,
    pcCsv: false,
    pcEpt: false,
    pcLas: false,
    pcSkipGeometric: false,
    primaryBand: '',
    projectPath: '',
    rerun: false,
    rerunAll: false,
    rerunFrom: '',
    sfmAlgorithm: '',
    sfmNoPartial: false,
    skipBandAlignment: false,
    skipOrthophoto: false,
    skyRemoval: false,
    smCluster: false,
    smNoAlign: false,
    smrf: false,
    smrfScalar: 0,
    smrfSlope: 0,
    smrfThreshold: 0,
    smrfWindow: 0,
    splitImageGroups: 0,
    texturingOutlierRemovalType: '',
    texturingSingleMaterial: false,
    texturingToneMapping: '',
    useExif: false,
    useHybridBundleAdjustment: false,
    version: false,
    videoLimit: 0,
    videoResolution: 0
  };

  private presets: Record<string, Partial<ODMOptions>> = {
    fast: { featureQuality: 'low', pcQuality: 'low', depthMapQuality: 'low', orthophotoResolution: 10, demResolution: 10, meshSize: 100000, fastOrthophoto: true, skipModel: true, maxConcurrency: 0, optimizeDiskSpace: true, noGpu: false },
    default: { featureQuality: 'high', pcQuality: 'medium', depthMapQuality: 'high', orthophotoResolution: 5, demResolution: 5, meshSize: 200000, noGpu: false },
    highQuality: { featureQuality: 'ultra', pcQuality: 'high', depthMapQuality: 'ultra', orthophotoResolution: 2, demResolution: 2, meshSize: 300000, minNumFeatures: 16000, cog: true, time: true, noGpu: false },
    '3dModel': { featureQuality: 'ultra', pcQuality: 'ultra', depthMapQuality: 'ultra', meshSize: 500000, meshOctreeDepth: 12, model3d: true, skipModel: false, tiles3d: true, pcClassify: true, noGpu: false },
    agriculture: { featureQuality: 'high', pcQuality: 'medium', orthophotoResolution: 3, demResolution: 3, radiometricCalibration: 'camera+sun', autoMask: true, tiles: true, orthophotoKmz: true, noGpu: false },
    survey: { featureQuality: 'ultra', pcQuality: 'high', depthMapQuality: 'ultra', orthophotoResolution: 1, demResolution: 1, minNumFeatures: 20000, useGcp: true, gcpAccuracy: 0.005, ignoreGsd: true, pcClassify: true, pcGeometric: true, demEuclideanMap: true, verbose: true, time: true, noGpu: false }
  };

  applyPreset(): void {
    if (this.selectedPreset !== 'custom') {
      const preset = this.presets[this.selectedPreset];
      if (preset) {
        this.options = { ...this.options, ...preset };
      }
    }
  }

  getEstimatedTime(): string {
    let baseMinutes = 10;
    const qualityMultipliers: Record<string, number> = { ultra: 4, high: 2, medium: 1, low: 0.5, lowest: 0.25 };
    const featureMult = qualityMultipliers[this.options.featureQuality] || 1;
    const pcMult = qualityMultipliers[this.options.pcQuality] || 1;
    const depthMult = qualityMultipliers[this.options.depthMapQuality] || 1;
    let totalMult = (featureMult + pcMult + depthMult) / 3;
    if (this.options.model3d && !this.options.skipModel) totalMult *= 1.5;
    if (this.options.pcClassify) totalMult *= 1.2;
    if (this.options.tiles || this.options.tiles3d) totalMult *= 1.3;
    if (this.options.dtm) totalMult *= 1.1;
    if (this.options.split > 0) totalMult *= 0.7;
    if (this.options.fastOrthophoto) totalMult *= 0.8;
    if (this.options.resizeTo > 0 && this.options.resizeTo < 2048) totalMult *= 0.6;
    if (this.options.debug) totalMult *= 1.5;
    const estimatedMinutes = Math.round(baseMinutes * totalMult);
    if (estimatedMinutes < 60) return `${estimatedMinutes} minutos`;
    const hours = Math.floor(estimatedMinutes / 60);
    const mins = estimatedMinutes % 60;
    return `${hours}h ${mins}min`;
  }

  onBackdropClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('modal-overlay')) {
      this.close();
    }
  }

  onAdvancedBackdropClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('advanced-overlay')) {
      this.showAdvancedModal = false;
    }
  }

  close(): void {
    this.closed.emit();
  }

  submit(): void {
    this.loading.set(true);
    const odmOptions = this.buildODMOptions();
    const request: CreateTaskRequest = { name: this.taskName, options: odmOptions };
    this.taskService.createTask(this.projectId(), request).subscribe({
      next: () => {
        this.loading.set(false);
        this.created.emit();
        this.close();
      },
      error: (error: any) => {
        this.loading.set(false);
        console.error('Failed to create task:', error);
        alert(error.error?.error || 'Erro ao criar tarefa');
      }
    });
  }

  private buildODMOptions(): Record<string, any> {
    const opts: Record<string, any> = {
      'feature-quality': this.options.featureQuality,
      'min-num-features': this.options.minNumFeatures,
      'matcher-type': this.options.matcher,
      'pc-quality': this.options.pcQuality,
      'mesh-size': this.options.meshSize,
      'mesh-octree-depth': this.options.meshOctreeDepth,
      'orthophoto-resolution': this.options.orthophotoResolution,
      'dem-resolution': this.options.demResolution,
      'depthmap-resolution': this.options.depthMapQuality,
      'gcp': this.options.useGcp || undefined,
      'dsm': this.options.dsm,
      'dtm': this.options.dtm,
      'fast-orthophoto': this.options.fastOrthophoto,
      'auto-boundary': this.options.autoMask,
      'ignore-gsd': this.options.ignoreGsd,
      'radiometric-calibration': this.options.radiometricCalibration,
      'skip-3dmodel': this.options.skipModel,
      'use-3dmesh': !this.options.skipModel && this.options.model3d,
      'skip-report': !this.options.report,
      'max-concurrency': this.options.maxConcurrency || undefined,
      'split': this.options.split || undefined,
      'split-overlap': this.options.split > 0 ? this.options.splitOverlap : undefined,
      'merge': this.options.split > 0 ? this.options.merge : undefined,
      'camera-lens': this.options.cameraLens !== 'auto' ? this.options.cameraLens : undefined,
      'rolling-shutter': this.options.rollingShutter || undefined,
      'rolling-shutter-readout': this.options.rollingShutter ? this.options.rollingShutterReadout : undefined,
      'use-fixed-camera-params': this.options.useFixedCameraParams || undefined,
      'pc-classify': this.options.pcClassify || undefined,
      'pc-geometric': this.options.pcGeometric || undefined,
      'pc-filter': this.options.pcFilter > 0 ? this.options.pcFilter : undefined,
      'pc-rectify': this.options.pcRectify || undefined,
      'pc-sample': this.options.pcSample > 0 ? this.options.pcSample : undefined,
      'crop': this.options.crop > 0 ? this.options.crop : undefined,
      'force-gps': this.options.forceGps || undefined,
      'orthophoto-png': this.options.orthophotoPng || undefined,
      'orthophoto-kmz': this.options.orthophotoKmz || undefined,
      'tiles': this.options.tiles || undefined,
      'cog': this.options.cog || undefined,
      '3d-tiles': this.options.tiles3d || undefined,
      'dem-euclidean-map': this.options.demEuclideanMap || undefined,
      'texturing-data-term': this.options.texturingDataTerm !== 'gmi' ? this.options.texturingDataTerm : undefined,
      'texturing-skip-global-seam-leveling': this.options.texturingSkipGlobalSeam || undefined,
      'texturing-skip-local-seam-leveling': this.options.texturingSkipLocalSeam || undefined,
      'texturing-keep-unseen-faces': this.options.texturingKeepUnseenFaces || undefined,
      'resize-to': this.options.resizeTo > 0 ? this.options.resizeTo : undefined,
      'optimize-disk-space': this.options.optimizeDiskSpace || undefined,
      'verbose': this.options.verbose || undefined,
      'time': this.options.time || undefined,
      'debug': this.options.debug || undefined,
      'no-gpu': this.options.noGpu || undefined,
      'align': this.options.align || undefined,
      'auto-boundary-distance': this.options.autoBoundaryDistance > 0 ? this.options.autoBoundaryDistance : undefined,
      'bg-removal': this.options.bgRemoval || undefined,
      'boundary': this.options.boundary || undefined,
      'build-overviews': this.options.buildOverviews || undefined,
      'cameras': this.options.cameras || undefined,
      'copy-to': this.options.copyTo || undefined,
      'dem': this.options.dem || undefined,
      'dem-decimation': this.options.demDecimation > 0 ? this.options.demDecimation : undefined,
      'dem-gapfill-steps': this.options.demGapfillSteps > 0 ? this.options.demGapfillSteps : undefined,
      'end-with': this.options.endWith || undefined,
      'feature-type': this.options.featureType || undefined,
      'geo': this.options.geo || undefined,
      'gltf': this.options.gltf || undefined,
      'gps-accuracy': this.options.gpsAccuracy > 0 ? this.options.gpsAccuracy : undefined,
      'gps-z-offset': this.options.gpsZOffset !== 0 ? this.options.gpsZOffset : undefined,
      'help': this.options.help || undefined,
      'matcher-neighbors': this.options.matcherNeighbors > 0 ? this.options.matcherNeighbors : undefined,
      'matcher-order': this.options.matcherOrder || undefined,
      'merge-skip-blending': this.options.mergeSkipBlending || undefined,
      'orthophoto-compression': this.options.orthophotoCompression || undefined,
      'orthophoto-cutline': this.options.orthophotoCutline || undefined,
      'orthophoto-no-tiled': this.options.orthophotoNoTiled || undefined,
      'pc-copc': this.options.pcCopc || undefined,
      'pc-csv': this.options.pcCsv || undefined,
      'pc-ept': this.options.pcEpt || undefined,
      'pc-las': this.options.pcLas || undefined,
      'pc-skip-geometric': this.options.pcSkipGeometric || undefined,
      'primary-band': this.options.primaryBand || undefined,
      'project-path': this.options.projectPath || undefined,
      'rerun': this.options.rerun || undefined,
      'rerun-all': this.options.rerunAll || undefined,
      'rerun-from': this.options.rerunFrom || undefined,
      'sfm-algorithm': this.options.sfmAlgorithm || undefined,
      'sfm-no-partial': this.options.sfmNoPartial || undefined,
      'skip-band-alignment': this.options.skipBandAlignment || undefined,
      'skip-orthophoto': this.options.skipOrthophoto || undefined,
      'sky-removal': this.options.skyRemoval || undefined,
      'sm-cluster': this.options.smCluster || undefined,
      'sm-no-align': this.options.smNoAlign || undefined,
      'smrf': this.options.smrf || undefined,
      'smrf-scalar': this.options.smrfScalar > 0 ? this.options.smrfScalar : undefined,
      'smrf-slope': this.options.smrfSlope > 0 ? this.options.smrfSlope : undefined,
      'smrf-threshold': this.options.smrfThreshold > 0 ? this.options.smrfThreshold : undefined,
      'smrf-window': this.options.smrfWindow > 0 ? this.options.smrfWindow : undefined,
      'split-image-groups': this.options.splitImageGroups > 0 ? this.options.splitImageGroups : undefined,
      'texturing-outlier-removal-type': this.options.texturingOutlierRemovalType || undefined,
      'texturing-single-material': this.options.texturingSingleMaterial || undefined,
      'texturing-tone-mapping': this.options.texturingToneMapping || undefined,
      'use-exif': this.options.useExif || undefined,
      'use-hybrid-bundle-adjustment': this.options.useHybridBundleAdjustment || undefined,
      'version': this.options.version || undefined,
      'video-limit': this.options.videoLimit > 0 ? this.options.videoLimit : undefined,
      'video-resolution': this.options.videoResolution > 0 ? this.options.videoResolution : undefined
    };

    Object.keys(opts).forEach(key => {
      if (opts[key] === undefined) {
        delete opts[key];
      }
    });

    return opts;
  }
}
