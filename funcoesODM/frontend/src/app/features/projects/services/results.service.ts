import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, map, catchError } from 'rxjs';

export interface TaskResult {
  taskId: number;
  projectId: number;
  status: string;
  availableAssets: string[];
  outputs: { [key: string]: string };
  completedAt?: string;
}

export interface AssetInfo {
  name: string;
  displayName: string;
  description: string;
  icon: string;
  extension: string;
  downloadUrl: string;
  previewUrl?: string;
  available: boolean;
}

export interface WarningSummary {
  type: string;
  icon: string;
  title: string;
  description: string;
  warnings: string[];
  severity: 'info' | 'warning' | 'error';
  tip: string;
}

export interface TaskWarnings {
  task_id: string;
  warnings: string[];
  warning_count: number;
  categories: {
    geometry: string[];
    driver: string[];
    processing: string[];
    skipped: string[];
    other: string[];
  };
  summary: WarningSummary[];
  has_critical_warnings: boolean;
  unique_warning_count: number;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ResultsService {
  private http = inject(HttpClient);
  private apiUrl = '/api/v1';

  /**
   * Get available assets for a completed task
   */
  getTaskAssets(projectId: number, taskId: number): Observable<AssetInfo[]> {
    return this.http.get<TaskResult>(`${this.apiUrl}/projects/${projectId}/tasks/${taskId}`)
      .pipe(
        map(task => this.mapOutputsToAssets(projectId, taskId, task.outputs || {})),
        catchError(() => of([]))
      );
  }

  /**
   * Map task outputs to asset info with metadata
   */
  private mapOutputsToAssets(projectId: number, taskId: number, outputs: { [key: string]: string }): AssetInfo[] {
    const assetDefinitions: { [key: string]: Omit<AssetInfo, 'downloadUrl' | 'available'> } = {
      'orthophoto': {
        name: 'orthophoto',
        displayName: 'Ortofoto',
        description: 'Mosaico ortorretificado em formato GeoTIFF',
        icon: '🗺️',
        extension: '.tif'
      },
      'orthophoto.tif': {
        name: 'orthophoto.tif',
        displayName: 'Ortofoto',
        description: 'Mosaico ortorretificado em formato GeoTIFF',
        icon: '🗺️',
        extension: '.tif'
      },
      'dsm': {
        name: 'dsm',
        displayName: 'DSM (Modelo Digital de Superfície)',
        description: 'Modelo de elevação incluindo objetos',
        icon: '🏔️',
        extension: '.tif'
      },
      'dsm.tif': {
        name: 'dsm.tif',
        displayName: 'DSM (Modelo Digital de Superfície)',
        description: 'Modelo de elevação incluindo objetos',
        icon: '🏔️',
        extension: '.tif'
      },
      'dtm': {
        name: 'dtm',
        displayName: 'DTM (Modelo Digital de Terreno)',
        description: 'Modelo de elevação do terreno',
        icon: '⛰️',
        extension: '.tif'
      },
      'dtm.tif': {
        name: 'dtm.tif',
        displayName: 'DTM (Modelo Digital de Terreno)',
        description: 'Modelo de elevação do terreno',
        icon: '⛰️',
        extension: '.tif'
      },
      'pointCloud': {
        name: 'pointCloud',
        displayName: 'Nuvem de Pontos',
        description: 'Nuvem de pontos georreferenciada (LAZ)',
        icon: '✨',
        extension: '.laz'
      },
      'georeferenced_model.laz': {
        name: 'georeferenced_model.laz',
        displayName: 'Nuvem de Pontos',
        description: 'Nuvem de pontos georreferenciada (LAZ)',
        icon: '✨',
        extension: '.laz'
      },
      'model3d': {
        name: 'model3d',
        displayName: 'Modelo 3D',
        description: 'Modelo 3D texturizado (OBJ)',
        icon: '🎮',
        extension: '.zip'
      },
      'textured_model.zip': {
        name: 'textured_model.zip',
        displayName: 'Modelo 3D',
        description: 'Modelo 3D texturizado (OBJ)',
        icon: '🎮',
        extension: '.zip'
      },
      'report': {
        name: 'report',
        displayName: 'Relatório',
        description: 'Relatório do processamento (PDF)',
        icon: '📄',
        extension: '.pdf'
      },
      'all.zip': {
        name: 'all.zip',
        displayName: 'Todos os Arquivos',
        description: 'Download de todos os resultados',
        icon: '📦',
        extension: '.zip'
      }
    };

    const assets: AssetInfo[] = [];

    for (const [key, url] of Object.entries(outputs)) {
      const definition = assetDefinitions[key];
      if (definition) {
        assets.push({
          ...definition,
          downloadUrl: this.buildDownloadUrl(projectId, taskId, key),
          previewUrl: this.buildPreviewUrl(projectId, taskId, key),
          available: true
        });
      }
    }

    // Add "all.zip" option if we have any assets
    if (assets.length > 0 && !assets.find(a => a.name === 'all.zip')) {
      assets.push({
        ...assetDefinitions['all.zip'],
        downloadUrl: this.buildDownloadUrl(projectId, taskId, 'all'),
        available: true
      });
    }

    return assets;
  }

  /**
   * Build download URL for an asset (legacy task-based endpoint)
   * @deprecated Use buildChunkDownloadUrl instead
   */
  private buildDownloadUrl(projectId: number, taskId: number, assetName: string): string {
    return `${this.apiUrl}/projects/${projectId}/tasks/${taskId}/download/${assetName}`;
  }

  /**
   * Build download URL for a chunk asset (preferred endpoint)
   */
  private buildChunkDownloadUrl(projectId: number, chunkId: number, assetName: string): string {
    // Map asset names to file names expected by the backend
    const assetFileMapping: { [key: string]: string } = {
      'orthophoto': 'orthophoto.tif',
      'dsm': 'dsm.tif',
      'dtm': 'dtm.tif',
      'pointCloud': 'georeferenced_model.laz',
      'model3d': 'textured_model.zip',
      'report': 'report.pdf',
      'all': 'all.zip'
    };
    const filename = assetFileMapping[assetName] || assetName;
    return `${this.apiUrl}/projects/${projectId}/chunks/${chunkId}/assets/${filename}`;
  }

  /**
   * Get asset download URL for a chunk (preferred method)
   */
  getChunkAssetDownloadUrl(projectId: number, chunkId: number, assetName: string): string {
    return this.buildChunkDownloadUrl(projectId, chunkId, assetName);
  }

  /**
   * @deprecated Use getChunkAssetDownloadUrl instead
   */
  getAssetDownloadUrl(projectId: number, taskId: number, assetName: string): string {
    return this.buildDownloadUrl(projectId, taskId, assetName);
  }

  /**
   * Build preview URL for an asset (for images)
   */
  private buildPreviewUrl(projectId: number, taskId: number, assetName: string): string | undefined {
    // Only orthophoto has preview capability for now
    if (assetName.includes('orthophoto')) {
      return `${this.apiUrl}/projects/${projectId}/tasks/${taskId}/preview/orthophoto`;
    }
    return undefined;
  }

  /**
   * Download an asset
   */
  downloadAsset(url: string, filename: string): void {
    this.http.get(url, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        link.click();
        window.URL.revokeObjectURL(downloadUrl);
      },
      error: (err) => {
        console.error('Download failed:', err);
        // Fallback to direct link
        window.open(url, '_blank');
      }
    });
  }

  /**
   * Get orthophoto tiles URL for Leaflet
    * Uses the NodeODM task UUID to access NodeODM directly (via proxy)
   */
  getOrthophotoTilesUrl(nodeodmTaskId: string): string {
    return `/nodeodm-api/task/${nodeodmTaskId}/download/orthophoto.tif`;
  }

  /**
   * Get orthophoto bounds for map centering
    * Placeholder: bounds are not computed without a dedicated service
   */
  getOrthophotoBounds(_projectId: number, _taskId: number, _nodeodmTaskId: string): Observable<{ north: number; south: number; east: number; west: number } | null> {
    return of(null);
  }

  /**
   * Get task location (center point) for map centering
  * @param nodeodmTaskId - UUID da task no NodeODM (preferido)
   * @param projectId - ID do projeto (fallback)
   * @param taskId - ID da task no banco (fallback)
   */
  getTaskLocation(_: number, __: number, ___?: string): Observable<{ lat: number; lng: number; zoom?: number; bounds?: any } | null> {
    return of(null);
  }

  /**
   * Get task processing warnings
    * @param nodeodmTaskId - UUID da task no NodeODM
   * Returns categorized warnings with user-friendly descriptions
   */
  getTaskWarnings(_: string): Observable<TaskWarnings | null> {
    return of(null);
  }
}
