/**
 * Data Source Detection
 *
 * Logica de deteccao e normalizacao de outputs de uma ProcessingTask:
 *  - Normaliza nomes de assets (orthophoto.tif -> orthophoto)
 *  - Monta URLs de download a partir de projectId e chunkId
 *  - Decide qual fonte de dados auto-selecionar
 *
 * Extraido do MeasurementTabComponent para manter o componente enxuto
 * e permitir reuso em outros contextos.
 */

import { TaskOutputs } from '../../services/task.service';

// ============================================================================
// Interfaces
// ============================================================================

export type DataSourceType = '' | 'orthophoto' | 'dsm' | 'pointcloud';

export interface DetectedAssets {
  orthophotoUrl: string | null;
  dsmUrl: string | null;
  dtmUrl: string | null;
  pointcloudUrl: string | null;
}

export interface DetectionResult {
  assets: DetectedAssets;
  autoSelected: DataSourceType;
}

// ============================================================================
// Funcoes
// ============================================================================

/**
 * Normaliza os outputs crus do backend para chaves conhecidas.
 * Backend retorna: {"orthophoto.tif": "url", "dsm.tif": "url", ...}
 * Esta funcao retorna: {orthophoto: "url", dsm: "url", ...}
 */
export function normalizeOutputs(rawOutputs: Record<string, any> | undefined | null): TaskOutputs {
  if (!rawOutputs || typeof rawOutputs !== 'object') return {};

  const normalized: TaskOutputs = {};

  Object.keys(rawOutputs).forEach(key => {
    const lk = key.toLowerCase();
    if (lk.includes('orthophoto') || lk.includes('ortho')) {
      normalized.orthophoto = rawOutputs[key];
    } else if (lk.includes('dsm') && !lk.includes('_size')) {
      normalized.dsm = rawOutputs[key];
    } else if (lk.includes('dtm') && !lk.includes('_size')) {
      normalized.dtm = rawOutputs[key];
    } else if (
      lk.includes('pointcloud') || lk.includes('point_cloud') ||
      lk.includes('point-cloud') || lk.includes('.ply') ||
      lk.includes('.laz') || lk.includes('.las')
    ) {
      normalized.pointCloud = rawOutputs[key];
    } else if (lk.includes('model') || lk.includes('.obj') || lk.includes('.glb')) {
      normalized.model3d = rawOutputs[key];
    } else if (lk.includes('report') || lk.includes('.pdf')) {
      normalized.report = rawOutputs[key];
    }
  });

  return normalized;
}

/**
 * Verifica se alguma chave nos rawOutputs contem a substring `key`
 */
export function hasAssetInOutputs(
  rawOutputs: Record<string, any> | undefined | null,
  key: string
): boolean {
  if (!rawOutputs) return false;
  return Object.keys(rawOutputs).some(k => k.toLowerCase().includes(key.toLowerCase()));
}

/**
 * Detecta URLs de assets disponiveis e a fonte de dados a ser auto-selecionada.
 *
 * @param projectId  ID do projeto
 * @param taskId     ID do chunk/task
 * @param rawOutputs outputs crus da task
 * @param isCompleted se a task esta completa
 */
export function detectAvailableAssets(
  projectId: number,
  taskId: number,
  rawOutputs: Record<string, any> | undefined | null,
  isCompleted: boolean
): DetectionResult {
  const norm = normalizeOutputs(rawOutputs);
  const base = `/api/v1/projects/${projectId}/tasks/${taskId}/download`;

  const assets: DetectedAssets = {
    orthophotoUrl: null,
    dsmUrl: null,
    dtmUrl: null,
    pointcloudUrl: null
  };

  // Prefer URLs stored in outputs (backend already has the correct path).
  // Fall back to legacy /tasks/{id}/download pattern only when missing.
  if (typeof norm.orthophoto === 'string' && norm.orthophoto.startsWith('/')) {
    assets.orthophotoUrl = norm.orthophoto;
  } else if (hasAssetInOutputs(rawOutputs, 'orthophoto') || isCompleted) {
    assets.orthophotoUrl = `${base}/orthophoto.tif`;
  }
  if (typeof norm.dsm === 'string' && norm.dsm.startsWith('/')) {
    assets.dsmUrl = norm.dsm;
  } else if (hasAssetInOutputs(rawOutputs, 'dsm')) {
    assets.dsmUrl = `${base}/dsm.tif`;
  }
  if (typeof norm.dtm === 'string' && norm.dtm.startsWith('/')) {
    assets.dtmUrl = norm.dtm;
  } else if (hasAssetInOutputs(rawOutputs, 'dtm')) {
    assets.dtmUrl = `${base}/dtm.tif`;
  }
  if (typeof norm.pointCloud === 'string' && norm.pointCloud.startsWith('/')) {
    assets.pointcloudUrl = norm.pointCloud;
  } else if (hasAssetInOutputs(rawOutputs, 'pointCloud')) {
    assets.pointcloudUrl = `${base}/georeferenced_model.laz`;
  }

  // Auto-selecao
  let autoSelected: DataSourceType = '';
  if (assets.orthophotoUrl) autoSelected = 'orthophoto';
  else if (assets.dsmUrl || assets.dtmUrl) autoSelected = 'dsm';
  else if (assets.pointcloudUrl) autoSelected = 'pointcloud';

  return { assets, autoSelected };
}
