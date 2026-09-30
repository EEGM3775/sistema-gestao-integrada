import { Injectable } from '@angular/core';
import { ODM_DEFAULT_OPTIONS } from '../constants';

export interface ChunkOptions {
  crs: string;
  orthophoto: boolean;
  dsm: boolean;
  dtm: boolean;
  pointCloud: boolean;
  mesh: boolean;
  quality: string;
}

/**
 * Service responsible for building NodeODM processing options
 * Separates option building logic from the component
 */
@Injectable({
  providedIn: 'root'
})
export class OdmOptionsBuilderService {
  
  /**
   * Returns a fresh copy of default advanced options
   */
  getDefaultAdvancedOptions(): Record<string, any> {
    return { ...ODM_DEFAULT_OPTIONS };
  }

  /**
   * Builds the final processing options based on quality preset,
   * basic chunk options, and advanced options
   */
  buildProcessingOptions(
    chunkOptions: ChunkOptions,
    advancedOptions: Record<string, any>
  ): Record<string, any> {
    const opts: Record<string, any> = {};
    
    // Quality mapping to NodeODM options (overrides advanced options)
    this.applyQualityPreset(opts, chunkOptions.quality);
    
    // Basic output options from chunkOptions
    opts['dsm'] = chunkOptions.dsm;
    opts['dtm'] = chunkOptions.dtm;
    opts['pc-las'] = chunkOptions.pointCloud;
    opts['use-3dmesh'] = chunkOptions.mesh;
    
    // Merge all advanced options (excluding defaults and empty strings)
    this.mergeAdvancedOptions(opts, advancedOptions);
    
    return opts;
  }

  /**
   * Applies quality preset settings
   */
  private applyQualityPreset(opts: Record<string, any>, quality: string): void {
    switch (quality) {
      case 'fast':
        opts['pc-quality'] = 'lowest';
        opts['feature-quality'] = 'low';
        opts['min-num-features'] = 4000;
        opts['mesh-octree-depth'] = 8;
        break;
      case 'medium':
        opts['pc-quality'] = 'low';
        opts['feature-quality'] = 'medium';
        opts['min-num-features'] = 8000;
        opts['mesh-octree-depth'] = 10;
        break;
      case 'high':
        opts['pc-quality'] = 'medium';
        opts['feature-quality'] = 'high';
        opts['min-num-features'] = 12000;
        opts['mesh-octree-depth'] = 11;
        break;
      case 'ultra':
        opts['pc-quality'] = 'high';
        opts['feature-quality'] = 'ultra';
        opts['min-num-features'] = 20000;
        opts['mesh-octree-depth'] = 12;
        break;
    }
  }

  /**
   * Merges advanced options, filtering out defaults
   */
  private mergeAdvancedOptions(
    opts: Record<string, any>,
    advancedOptions: Record<string, any>
  ): void {
    // Options already set by quality preset
    const qualityPresetKeys = ['pc-quality', 'feature-quality', 'min-num-features', 'mesh-octree-depth'];
    
    // Numeric defaults that match NodeODM defaults
    const numericDefaults: Record<string, any> = {
      'matcher-neighbors': 0,
      'matcher-order': 0,
      'pc-filter': 5,
      'pc-sample': 0,
      'dem-gapfill-steps': 3,
      'dem-resolution': 5,
      'dem-decimation': 1,
      'smrf-scalar': 1.25,
      'smrf-slope': 0.15,
      'smrf-threshold': 0.5,
      'smrf-window': 18,
      'orthophoto-resolution': 5,
      'gps-accuracy': 3,
      'gps-z-offset': 0,
      'crop': 3,
      'auto-boundary-distance': 0,
      'rolling-shutter-readout': 0,
      'max-concurrency': 0,
      'split': 999999,
      'split-overlap': 150,
      'video-limit': 500,
      'video-resolution': 4000,
      'mesh-size': 200000
    };
    
    // String defaults
    const stringDefaults: Record<string, string> = {
      'feature-type': 'dspsift',
      'matcher-type': 'flann',
      'camera-lens': 'auto',
      'radiometric-calibration': 'none',
      'sfm-algorithm': 'incremental',
      'orthophoto-compression': 'DEFLATE',
      'merge': 'all',
      'primary-band': 'auto',
      'end-with': 'odm_postprocess'
    };

    for (const [key, value] of Object.entries(advancedOptions)) {
      // Skip empty strings
      if (value === '' || value === null || value === undefined) {
        continue;
      }
      
      // Skip options that are already set by quality preset
      if (qualityPresetKeys.includes(key)) {
        continue;
      }
      
      // Skip boolean false values (NodeODM uses defaults)
      if (typeof value === 'boolean' && !value) {
        continue;
      }
      
      // Skip numeric defaults
      if (key in numericDefaults && value === numericDefaults[key]) {
        continue;
      }
      
      // Skip string defaults
      if (key in stringDefaults && value === stringDefaults[key]) {
        continue;
      }
      
      opts[key] = value;
    }
  }

  /**
   * Counts selected output products
   */
  getSelectedOutputsCount(chunkOptions: ChunkOptions): number {
    let count = 0;
    if (chunkOptions.orthophoto) count++;
    if (chunkOptions.dsm) count++;
    if (chunkOptions.dtm) count++;
    if (chunkOptions.pointCloud) count++;
    if (chunkOptions.mesh) count++;
    return count;
  }
}
