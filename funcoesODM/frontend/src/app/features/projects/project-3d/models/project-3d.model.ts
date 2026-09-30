/**
 * Models para Project 3D Viewer
 */

export interface ProjectInfo {
  id: number;
  taskId: number;
  name: string;
  description: string;
  status: string;
}

export type ViewMode = 'orbit' | 'pan' | 'zoom';
export type DisplayType = 'pointcloud' | 'mesh';
export type ColorMode = 'rgb' | 'elevation' | 'intensity';

export interface ViewerStats {
  points: number;
  fps: number;
  memory: number;
}

export interface ViewerSettings {
  viewMode: ViewMode;
  displayType: DisplayType;
  colorMode: ColorMode;
  pointSize: number;
  showGrid: boolean;
  showAxes: boolean;
  showMeasure: boolean;
  showClipping: boolean;
}
