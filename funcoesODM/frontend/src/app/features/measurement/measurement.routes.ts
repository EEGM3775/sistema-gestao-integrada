/**
 * Measurement Module Routes
 * 
 * DEPRECATED: Medições agora são integradas como aba no project-detail
 * Estas rotas standalone estão mantidas para acesso direto se necessário
 */

import { Routes } from '@angular/router';

export const MEASUREMENT_ROUTES: Routes = [
  // Rotas standalone (opcional - medições estão integradas no project-detail)
  {
    path: 'orthophoto/:id',
    loadComponent: () => 
      import('../../shared/viewers/orthophoto-viewer/orthophoto-viewer.component')
        .then(m => m.OrthophotoViewerComponent),
    title: 'Ortofoto - Medições'
  },
  {
    path: 'dem/:id',
    loadComponent: () => 
      import('../../shared/viewers/dem-viewer/dem-viewer.component')
        .then(m => m.DemViewerComponent),
    title: 'DEM - Medições'
  },
  {
    path: 'pointcloud/:id',
    loadComponent: () => 
      import('../../shared/viewers/pointcloud-viewer/pointcloud-viewer.component')
        .then(m => m.PointcloudViewerComponent),
    title: 'Nuvem de Pontos - Medições'
  }
];
