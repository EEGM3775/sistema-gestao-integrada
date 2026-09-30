/**
 * NodeODM Processing Options Constants
 * Extracted from project-workspace for better maintainability
 */

export interface AdvancedOption {
  key: string;
  label: string;
  type: 'number' | 'text' | 'boolean' | 'select' | 'file';
  help: string;
  accept?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
}

export interface OptionCategory {
  name: string;
  icon: string;
  expanded: boolean;
  options: AdvancedOption[];
}

export interface QualityLevel {
  value: string;
  name: string;
  description: string;
  time: string;
}

export const QUALITY_LEVELS: QualityLevel[] = [
  { value: 'fast', name: 'Rápido', description: 'Prévia', time: '5-15min' },
  { value: 'medium', name: 'Médio', description: 'Balanceado', time: '30-60min' },
  { value: 'high', name: 'Alto', description: 'Precisão', time: '2-4h' },
  { value: 'ultra', name: 'Ultra', description: 'Máximo', time: '6h+' }
];

export const ODM_DEFAULT_OPTIONS: Record<string, any> = {
  // === FEATURE EXTRACTION ===
  'min-num-features': 10000,
  'feature-type': 'sift',
  'feature-quality': 'high',
  
  // === MATCHING ===
  'matcher-type': 'flann',
  'matcher-neighbors': 0,
  'matcher-order': 0,
  
  // === CAMERA ===
  'use-fixed-camera-params': false,
  'camera-lens': 'auto',
  'cameras': '',
  
  // === RADIOMETRIC ===
  'radiometric-calibration': 'none',
  
  // === SFM ===
  'sfm-algorithm': 'incremental',
  'sfm-no-partial': false,
  'use-hybrid-bundle-adjustment': false,
  
  // === AI/MASKS ===
  'sky-removal': false,
  'bg-removal': false,
  
  // === 3D MODEL ===
  'use-3dmesh': false,
  'skip-3dmodel': false,
  'mesh-size': 200000,
  'mesh-octree-depth': 11,
  'texturing-data-term': 'gmi',
  'texturing-skip-global-seam-leveling': false,
  'texturing-skip-local-seam-leveling': false,
  'texturing-skip-hole-filling': false,
  'texturing-keep-unseen-faces': false,
  'texturing-single-material': false,
  'texturing-outlier-removal-type': 'gauss_clamping',
  'texturing-tone-mapping': 'none',
  'gltf': false,
  
  // === POINT CLOUD ===
  'pc-quality': 'medium',
  'pc-classify': false,
  'pc-csv': false,
  'pc-las': false,
  'pc-ept': false,
  'pc-copc': false,
  'pc-tile': false,
  'pc-filter': 5,
  'pc-sample': 0,
  'pc-skip-geometric': false,
  'pc-rectify': false,
  'pc-geometric': false,
  'depthmap-resolution': 640,
  
  // === DEM ===
  'dsm': true,
  'dtm': false,
  'dem-gapfill-steps': 3,
  'dem-resolution': 5,
  'dem-decimation': 1,
  'dem-euclidean-map': false,
  
  // === SMRF (DTM FILTER) ===
  'smrf-scalar': 1.25,
  'smrf-slope': 0.15,
  'smrf-threshold': 0.5,
  'smrf-window': 18,
  
  // === ORTHOPHOTO ===
  'orthophoto-resolution': 5,
  'orthophoto-no-tiled': false,
  'orthophoto-png': false,
  'orthophoto-kmz': false,
  'orthophoto-compression': 'DEFLATE',
  'orthophoto-bigtiff': 'IF_SAFER',
  'orthophoto-cutline': false,
  'skip-orthophoto': false,
  'fast-orthophoto': false,
  
  // === TILES ===
  'tiles': false,
  '3d-tiles': false,
  'cog': false,
  'build-overviews': false,
  
  // === GPS ===
  'gps-accuracy': 3,
  'gps-z-offset': 0,
  'use-exif': false,
  'force-gps': false,
  
  // === GCP ===
  'gcp': '',
  'geo': '',
  
  // === BOUNDARIES ===
  'crop': 3,
  'boundary': '',
  'auto-boundary': false,
  'auto-boundary-distance': 0,
  'ignore-gsd': false,
  
  // === ROLLING SHUTTER ===
  'rolling-shutter': false,
  'rolling-shutter-readout': 0,
  
  // === PROCESSING ===
  'max-concurrency': 0,
  'no-gpu': false,
  'optimize-disk-space': false,
  'resize-to': 0,
  'skip-report': false,
  
  // === DEBUG ===
  'verbose': false,
  'time': false,
  'debug': false,
  
  // === SPLIT/MERGE ===
  'split': 999999,
  'split-image-groups': '',
  'split-overlap': 150,
  'sm-no-align': false,
  'sm-cluster': '',
  'merge': 'all',
  'merge-skip-blending': false,
  
  // === VIDEO ===
  'video-limit': 500,
  'video-resolution': 4000,
  
  // === MULTISPECTRAL ===
  'primary-band': 'auto',
  'skip-band-alignment': false,
  
  // === WORKFLOW ===
  'rerun-from': '',
  'end-with': 'odm_postprocess',
  'copy-to': '',
  'align': ''
};

export const ODM_OPTION_CATEGORIES: OptionCategory[] = [
  {
    name: 'Extração de Features',
    icon: '🔍',
    expanded: false,
    options: [
      { key: 'min-num-features', label: 'Mínimo de Features', type: 'number', min: 1000, max: 50000, help: 'Número mínimo de features a extrair por imagem' },
      { key: 'feature-type', label: 'Tipo de Feature', type: 'select', options: ['akaze', 'dspsift', 'hahog', 'orb', 'sift'], help: 'Algoritmo para extração de keypoints' },
      { key: 'feature-quality', label: 'Qualidade de Features', type: 'select', options: ['ultra', 'high', 'medium', 'low', 'lowest'], help: 'Qualidade da extração de features' }
    ]
  },
  {
    name: 'Matching de Imagens',
    icon: '🔗',
    expanded: false,
    options: [
      { key: 'matcher-type', label: 'Tipo de Matcher', type: 'select', options: ['bow', 'bruteforce', 'flann'], help: 'Algoritmo de matching' },
      { key: 'matcher-neighbors', label: 'Vizinhos por GPS', type: 'number', min: 0, max: 100, help: 'Match com N imagens mais próximas por GPS. 0=triangulação' },
      { key: 'matcher-order', label: 'Ordem Sequencial', type: 'number', min: 0, max: 100, help: 'Match com N imagens próximas por nome. Útil para vídeo. 0=desativado' }
    ]
  },
  {
    name: 'Câmera',
    icon: '📷',
    expanded: false,
    options: [
      { key: 'camera-lens', label: 'Tipo de Lente', type: 'select', options: ['auto', 'perspective', 'brown', 'fisheye', 'fisheye_opencv', 'spherical', 'equirectangular', 'dual'], help: 'Tipo de projeção da câmera' },
      { key: 'cameras', label: 'Arquivo de Câmeras', type: 'text', help: 'Caminho para arquivo cameras.json personalizado' },
      { key: 'use-fixed-camera-params', label: 'Parâmetros Fixos', type: 'boolean', help: 'Desativa otimização de parâmetros de câmera' },
      { key: 'rolling-shutter', label: 'Rolling Shutter', type: 'boolean', help: 'Ativa correção de rolling shutter' },
      { key: 'rolling-shutter-readout', label: 'Tempo de Readout (ms)', type: 'number', min: 0, max: 100, help: 'Override do tempo de readout em ms. 0=usar banco de dados' }
    ]
  },
  {
    name: 'SFM (Structure from Motion)',
    icon: '🏗️',
    expanded: false,
    options: [
      { key: 'sfm-algorithm', label: 'Algoritmo SFM', type: 'select', options: ['incremental', 'triangulation', 'planar'], help: 'Algoritmo de reconstrução. triangulation=melhor com GPS preciso' },
      { key: 'sfm-no-partial', label: 'Sem Reconstruções Parciais', type: 'boolean', help: 'Não tenta unir reconstruções parciais' },
      { key: 'use-hybrid-bundle-adjustment', label: 'Bundle Adjustment Híbrido', type: 'boolean', help: 'Acelera reconstrução em datasets muito grandes' }
    ]
  },
  {
    name: 'Nuvem de Pontos',
    icon: '✨',
    expanded: false,
    options: [
      { key: 'pc-quality', label: 'Qualidade', type: 'select', options: ['ultra', 'high', 'medium', 'low', 'lowest'], help: 'Qualidade da nuvem de pontos. Cada nível aumenta ~4x o tempo' },
      { key: 'pc-filter', label: 'Filtro de Outliers (σ)', type: 'number', min: 0, max: 10, step: 0.5, help: 'Remove pontos > N desvios padrão. 0=desativado' },
      { key: 'pc-sample', label: 'Amostragem (m)', type: 'number', min: 0, max: 10, step: 0.1, help: 'Mantém 1 ponto por raio N metros. 0=desativado' },
      { key: 'pc-classify', label: 'Classificar Pontos', type: 'boolean', help: 'Classifica a nuvem de pontos (solo, vegetação, etc.)' },
      { key: 'pc-rectify', label: 'Retificar Solo', type: 'boolean', help: 'Reclassifica e preenche lacunas no solo' },
      { key: 'pc-skip-geometric', label: 'Pular Geometric', type: 'boolean', help: 'Pula estimativas geométricas (mais rápido, menos preciso)' },
      { key: 'pc-geometric', label: '⚠️ Geometric DEPRECATED', type: 'boolean', help: 'DEPRECATED: Ativa estimativas geométricas. Opção descontinuada' },
      { key: 'depthmap-resolution', label: '⚠️ Depthmap Resolution DEPRECATED', type: 'number', min: 320, max: 2400, help: 'DEPRECATED: Resolução do depthmap. Opção descontinuada' }
    ]
  },
  {
    name: 'Exportação de Nuvem',
    icon: '💾',
    expanded: false,
    options: [
      { key: 'pc-las', label: 'Exportar LAS', type: 'boolean', help: 'Exporta nuvem em formato LAS' },
      { key: 'pc-ept', label: 'Exportar EPT', type: 'boolean', help: 'Exporta em Entwine Point Tile para visualização web' },
      { key: 'pc-copc', label: 'Exportar COPC', type: 'boolean', help: 'Exporta em Cloud Optimized Point Cloud' },
      { key: 'pc-tile', label: 'Gerar Tiles 3D', type: 'boolean', help: 'Gera tiles 3D da nuvem de pontos' },
      { key: 'pc-csv', label: 'Exportar CSV', type: 'boolean', help: 'Exporta nuvem em formato CSV' }
    ]
  },
  {
    name: 'Modelo 3D / Mesh',
    icon: '🎮',
    expanded: false,
    options: [
      { key: 'skip-3dmodel', label: 'Pular Modelo 3D', type: 'boolean', help: 'Pula geração do modelo 3D completo' },
      { key: 'use-3dmesh', label: 'Usar Mesh 3D', type: 'boolean', help: 'Usa mesh 3D completo ao invés de 2.5D para ortofoto' },
      { key: 'mesh-size', label: 'Tamanho do Mesh', type: 'number', min: 50000, max: 1000000, step: 50000, help: 'Número máximo de vértices' },
      { key: 'mesh-octree-depth', label: 'Profundidade Octree', type: 'number', min: 1, max: 14, help: 'Profundidade da octree. 8-12 recomendado' },
      { key: 'gltf', label: 'Exportar GLTF', type: 'boolean', help: 'Gera modelo texturizado em GLTF/GLB' }
    ]
  },
  {
    name: 'Texturização',
    icon: '🎨',
    expanded: false,
    options: [
      { key: 'texturing-data-term', label: '⚠️ Algoritmo de Dados DEPRECATED', type: 'select', options: ['gmi', 'area'], help: 'DEPRECATED: Termo de dados para otimização de textura' },
      { key: 'texturing-outlier-removal-type', label: '⚠️ Remoção de Outliers DEPRECATED', type: 'select', options: ['none', 'gauss_clamping', 'gauss_damping'], help: 'DEPRECATED: Tipo de remoção de outliers' },
      { key: 'texturing-tone-mapping', label: '⚠️ Tone Mapping DEPRECATED', type: 'select', options: ['none', 'gamma'], help: 'DEPRECATED: Mapeamento de tons para textura' },
      { key: 'texturing-skip-global-seam-leveling', label: 'Pular Normalização Global', type: 'boolean', help: 'Pula normalização global de cores' },
      { key: 'texturing-skip-local-seam-leveling', label: '⚠️ Pular Normalização Local DEPRECATED', type: 'boolean', help: 'DEPRECATED: Pula normalização local de cores nas costuras' },
      { key: 'texturing-skip-hole-filling', label: 'Pular Preenchimento de Buracos', type: 'boolean', help: 'Pula preenchimento automático de buracos na textura' },
      { key: 'texturing-keep-unseen-faces', label: 'Manter Faces Não Vistas', type: 'boolean', help: 'Mantém faces não vistas em nenhuma câmera' },
      { key: 'texturing-single-material', label: 'Material Único', type: 'boolean', help: 'Gera OBJ com material e textura únicos' }
    ]
  },
  {
    name: 'DEM (Modelos de Elevação)',
    icon: '🏔️',
    expanded: false,
    options: [
      { key: 'dsm', label: 'Gerar DSM', type: 'boolean', help: 'Gera Modelo Digital de Superfície' },
      { key: 'dtm', label: 'Gerar DTM', type: 'boolean', help: 'Gera Modelo Digital de Terreno (apenas solo)' },
      { key: 'dem-resolution', label: 'Resolução (cm/pixel)', type: 'number', min: 1, max: 100, help: 'Resolução do DEM em cm/pixel' },
      { key: 'dem-gapfill-steps', label: 'Passos de Preenchimento', type: 'number', min: 0, max: 10, help: 'Passos para preencher lacunas. 0=desativado' },
      { key: 'dem-decimation', label: 'Decimação', type: 'number', min: 1, max: 100, help: 'Decima pontos antes do DEM. 1=sem decimação, 100=~99%' },
      { key: 'dem-euclidean-map', label: 'Mapa Euclidiano', type: 'boolean', help: 'Gera mapa de distância até NODATA' }
    ]
  },
  {
    name: 'Filtro SMRF (DTM)',
    icon: '⛰️',
    expanded: false,
    options: [
      { key: 'smrf-scalar', label: 'Escalar', type: 'number', min: 0.1, max: 5, step: 0.05, help: 'Parâmetro escalar do filtro SMRF' },
      { key: 'smrf-slope', label: 'Inclinação', type: 'number', min: 0.01, max: 1, step: 0.01, help: 'Parâmetro de inclinação (rise/run)' },
      { key: 'smrf-threshold', label: 'Limiar (m)', type: 'number', min: 0.1, max: 5, step: 0.1, help: 'Limiar de elevação em metros' },
      { key: 'smrf-window', label: 'Janela (m)', type: 'number', min: 1, max: 100, help: 'Raio da janela em metros' }
    ]
  },
  {
    name: 'Ortofoto',
    icon: '🗺️',
    expanded: false,
    options: [
      { key: 'skip-orthophoto', label: 'Pular Ortofoto', type: 'boolean', help: 'Pula geração do ortofoto' },
      { key: 'fast-orthophoto', label: 'Ortofoto Rápido', type: 'boolean', help: 'Gera ortofoto direto da reconstrução esparsa' },
      { key: 'orthophoto-resolution', label: 'Resolução (cm/pixel)', type: 'number', min: 1, max: 100, help: 'Resolução em cm/pixel' },
      { key: 'orthophoto-compression', label: 'Compressão', type: 'select', options: ['JPEG', 'LZW', 'PACKBITS', 'DEFLATE', 'LZMA', 'NONE'], help: 'Tipo de compressão do GeoTIFF' },
      { key: 'orthophoto-bigtiff', label: 'BigTIFF', type: 'select', options: ['YES', 'NO', 'IF_NEEDED', 'IF_SAFER'], help: 'Forçar BigTIFF para arquivos grandes (>4GB)' },
      { key: 'orthophoto-png', label: 'Exportar PNG', type: 'boolean', help: 'Gera renderização PNG' },
      { key: 'orthophoto-kmz', label: 'Exportar KMZ', type: 'boolean', help: 'Gera arquivo para Google Earth' },
      { key: 'orthophoto-no-tiled', label: 'GeoTIFF Striped', type: 'boolean', help: 'Gera GeoTIFF striped ao invés de tiled' },
      { key: 'orthophoto-cutline', label: 'Gerar Cutline', type: 'boolean', help: 'Gera polígono de corte para mosaicos' }
    ]
  },
  {
    name: 'Tiles e Otimização',
    icon: '🧱',
    expanded: false,
    options: [
      { key: 'tiles', label: 'Gerar Tiles 2D', type: 'boolean', help: 'Gera tiles estáticos para Leaflet/OpenLayers' },
      { key: '3d-tiles', label: 'Gerar 3D Tiles', type: 'boolean', help: 'Gera OGC 3D Tiles' },
      { key: 'cog', label: 'Cloud Optimized GeoTIFF', type: 'boolean', help: 'Cria COG ao invés de GeoTIFF normal' },
      { key: 'build-overviews', label: 'Construir Overviews', type: 'boolean', help: 'Gera overviews para visualização rápida no QGIS' }
    ]
  },
  {
    name: 'GPS e Georreferenciamento',
    icon: '📍',
    expanded: false,
    options: [
      { key: 'gps-accuracy', label: 'Precisão GPS (m)', type: 'number', min: 0.01, max: 100, step: 0.1, help: 'DOP do GPS em metros. Menor = mais preciso' },
      { key: 'gps-z-offset', label: 'Offset Z (m)', type: 'number', min: -1000, max: 1000, help: 'Offset vertical para correção elipsoidal/ortométrica' },
      { key: 'use-exif', label: 'Usar EXIF', type: 'boolean', help: 'Usa EXIF ao invés de GCP para georreferenciamento' },
      { key: 'force-gps', label: 'Forçar GPS', type: 'boolean', help: 'Usa GPS mesmo com GCPs presentes' }
    ]
  },
  {
    name: 'Pontos de Controle (GCP)',
    icon: '🎯',
    expanded: false,
    options: [
      { key: 'gcp', label: 'Arquivo GCP', type: 'file', accept: '.txt', help: 'Arquivo .txt com Ground Control Points no formato ODM (EPSG:code + lat lng alt px py imagem)' },
      { key: 'geo', label: 'Arquivo de Projeção', type: 'text', help: 'Caminho para arquivo txt com definição da projeção (opcional)' }
    ]
  },
  {
    name: 'Limites e Recorte',
    icon: '✂️',
    expanded: false,
    options: [
      { key: 'crop', label: 'Margem de Recorte (m)', type: 'number', min: 0, max: 100, help: 'Buffer de recorte em metros. 0=desativado' },
      { key: 'boundary', label: 'Polígono Limite (GeoJSON)', type: 'text', help: 'GeoJSON ou caminho para arquivo com polígono de limite' },
      { key: 'auto-boundary', label: 'Limite Automático', type: 'boolean', help: 'Define limite automaticamente pelas posições das câmeras' },
      { key: 'auto-boundary-distance', label: 'Distância do Limite (m)', type: 'number', min: 0, max: 1000, help: 'Distância entre câmeras e borda. 0=automático' },
      { key: 'ignore-gsd', label: 'Ignorar GSD', type: 'boolean', help: 'Ignora estimativa de GSD. CUIDADO: usa muita memória!' }
    ]
  },
  {
    name: 'Calibração Radiométrica',
    icon: '☀️',
    expanded: false,
    options: [
      { key: 'radiometric-calibration', label: 'Calibração', type: 'select', options: ['none', 'camera', 'camera+sun'], help: 'Calibração para imagens multiespectrais/térmicas' }
    ]
  },
  {
    name: 'IA / Máscaras',
    icon: '🤖',
    expanded: false,
    options: [
      { key: 'sky-removal', label: 'Remover Céu (IA)', type: 'boolean', help: 'Remove céu automaticamente com IA. Experimental' },
      { key: 'bg-removal', label: 'Remover Fundo (IA)', type: 'boolean', help: 'Remove fundo automaticamente com IA. Experimental' }
    ]
  },
  {
    name: 'Split/Merge (Grandes Datasets)',
    icon: '🔀',
    expanded: false,
    options: [
      { key: 'split', label: 'Imagens por Submodelo', type: 'number', min: 50, max: 999999, help: 'Média de imagens por submodelo' },
      { key: 'split-overlap', label: 'Overlap (m)', type: 'number', min: 0, max: 500, help: 'Raio de overlap entre submodelos' },
      { key: 'split-image-groups', label: 'Arquivo de Grupos', type: 'text', help: 'Caminho para arquivo que define agrupamento manual de imagens' },
      { key: 'sm-cluster', label: 'Arquivo de Cluster', type: 'text', help: 'Caminho para arquivo JSON com definição de clusters' },
      { key: 'merge', label: 'O que Mesclar', type: 'select', options: ['all', 'pointcloud', 'orthophoto', 'dem'], help: 'Outputs a mesclar' },
      { key: 'sm-no-align', label: 'Pular Alinhamento', type: 'boolean', help: 'Pula alinhamento de submodelos (se GPS é bom)' },
      { key: 'merge-skip-blending', label: 'Pular Blending', type: 'boolean', help: 'Pula operação cara de blending na mesclagem' }
    ]
  },
  {
    name: 'Vídeo',
    icon: '🎬',
    expanded: false,
    options: [
      { key: 'video-limit', label: 'Limite de Frames', type: 'number', min: 0, max: 10000, help: 'Máximo de frames a extrair. 0=sem limite' },
      { key: 'video-resolution', label: 'Resolução (pixels)', type: 'number', min: 500, max: 8000, help: 'Resolução máxima dos frames extraídos' }
    ]
  },
  {
    name: 'Multiespectral',
    icon: '🌈',
    expanded: false,
    options: [
      { key: 'primary-band', label: 'Banda Primária', type: 'text', help: 'Nome da banda primária para reconstrução. auto=automático' },
      { key: 'skip-band-alignment', label: 'Pular Alinhamento', type: 'boolean', help: 'Pula alinhamento de bandas (se já alinhadas)' }
    ]
  },
  {
    name: 'Performance',
    icon: '⚡',
    expanded: false,
    options: [
      { key: 'max-concurrency', label: 'Threads (0=auto)', type: 'number', min: 0, max: 64, help: 'Número máximo de processos paralelos' },
      { key: 'resize-to', label: '⚠️ Redimensionar Imagens DEPRECATED', type: 'number', min: 0, max: 8000, help: 'DEPRECATED: Redimensiona imagens' },
      { key: 'no-gpu', label: 'Desativar GPU', type: 'boolean', help: 'Não usa aceleração GPU' },
      { key: 'optimize-disk-space', label: 'Otimizar Disco', type: 'boolean', help: 'Deleta arquivos intermediários. Impede reinício' }
    ]
  },
  {
    name: 'Debug & Monitoramento',
    icon: '🐛',
    expanded: false,
    options: [
      { key: 'verbose', label: '⚠️ Modo Verbose DEPRECATED', type: 'boolean', help: 'DEPRECATED: Saída detalhada de logs' },
      { key: 'time', label: '⚠️ Mostrar Tempos DEPRECATED', type: 'boolean', help: 'DEPRECATED: Exibe tempo de execução' },
      { key: 'debug', label: '⚠️ Modo Debug DEPRECATED', type: 'boolean', help: 'DEPRECATED: Salva arquivos intermediários' }
    ]
  },
  {
    name: 'Relatório',
    icon: '📄',
    expanded: false,
    options: [
      { key: 'skip-report', label: 'Pular Relatório', type: 'boolean', help: 'Pula geração do relatório PDF' }
    ]
  },
  {
    name: 'Workflow Avançado',
    icon: '🔄',
    expanded: false,
    options: [
      { key: 'rerun-from', label: 'Reiniciar de', type: 'select', options: ['', 'dataset', 'split', 'merge', 'opensfm', 'openmvs', 'odm_filterpoints', 'odm_meshing', 'mvs_texturing', 'odm_georeferencing', 'odm_dem', 'odm_orthophoto', 'odm_postprocess'], help: 'Estágio para reiniciar o processamento' },
      { key: 'end-with', label: 'Terminar em', type: 'select', options: ['odm_postprocess', 'dataset', 'split', 'merge', 'opensfm', 'openmvs', 'odm_filterpoints', 'odm_meshing', 'mvs_texturing', 'odm_georeferencing', 'odm_dem', 'odm_orthophoto'], help: 'Estágio onde terminar o processamento' },
      { key: 'copy-to', label: 'Copiar Resultados Para', type: 'text', help: 'Caminho de rede/nuvem para copiar resultados automaticamente' },
      { key: 'align', label: 'Alinhar a DEM/Nuvem', type: 'text', help: 'Caminho para GeoTIFF DEM ou nuvem LAS/LAZ para alinhamento automático' }
    ]
  }
];
