/**
 * Type declarations for georaster library
 * Professional GeoTIFF parsing for engineering applications
 */

declare module 'georaster' {
  interface GeoRaster {
    width: number;
    height: number;
    numberOfRasters: number;
    pixelWidth: number;
    pixelHeight: number;
    xmin: number;
    xmax: number;
    ymin: number;
    ymax: number;
    projection: number;
    values: number[][][];
    noDataValue: number | null;
    mins: number[];
    maxs: number[];
    ranges: number[];
    getValues(options?: { 
      left?: number; 
      right?: number; 
      top?: number; 
      bottom?: number;
      width?: number;
      height?: number;
    }): Promise<number[][][]>;
  }

  function parseGeoraster(
    input: ArrayBuffer | Uint8Array | string | File,
    metadata?: any
  ): Promise<GeoRaster>;

  export default parseGeoraster;
  export { GeoRaster };
}

declare module 'georaster-layer-for-leaflet' {
  import { Layer } from 'leaflet';
  import { GeoRaster } from 'georaster';

  interface GeoRasterLayerOptions {
    georaster: GeoRaster;
    opacity?: number;
    resolution?: number;
    debugLevel?: number;
    pixelValuesToColorFn?: (values: number[]) => string;
    bounds?: [[number, number], [number, number]];
  }

  class GeoRasterLayer extends Layer {
    constructor(options: GeoRasterLayerOptions);
    setOpacity(opacity: number): this;
  }

  export default GeoRasterLayer;
}
