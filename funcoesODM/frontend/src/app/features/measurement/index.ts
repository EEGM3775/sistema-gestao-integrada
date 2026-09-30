/**
 * Measurement Module Index
 * 
 * Exports públicos do módulo de medições
 */

// Components
export { MeasurementToolbarComponent } from './components/measurement-toolbar/measurement-toolbar.component';
export { MeasurementPanelComponent } from './components/measurement-panel/measurement-panel.component';

// Services
export { MeasurementService } from './services/measurement.service';
export { MapDrawingService } from './services/map-drawing.service';
export { MeasurementHistoryService } from './services/measurement-history.service';
export { MeasurementExportService } from './services/measurement-export.service';

// Models
export * from './models/measurement.model';

// Viewers movidos para shared/viewers
// export { OrthophotoViewerComponent } from '../../shared/viewers/orthophoto-viewer/orthophoto-viewer.component';

// Routes (deprecated - integrado no project-detail)
export { MEASUREMENT_ROUTES } from './measurement.routes';
