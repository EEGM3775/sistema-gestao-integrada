import { AssetInfo } from '../../../services/results.service';

/**
 * Asset com informação de seleção para downloads
 */
export interface SelectableAsset extends AssetInfo {
  selected: boolean;
  size?: string;
}

/**
 * Tipos de abas disponíveis no visualizador de resultados
 */
export type TabType = 'map' | 'dsm' | 'downloads' | 'warnings';
