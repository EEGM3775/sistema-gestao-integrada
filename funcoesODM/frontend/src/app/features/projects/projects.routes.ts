import { Routes } from '@angular/router';

export const PROJECTS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./project-list/project-list.component').then(m => m.ProjectListComponent)
  },
  {
    path: 'new',
    loadComponent: () => import('./project-workspace/project-workspace.component').then(m => m.ProjectWorkspaceComponent)
  },
  {
    path: ':id',
    loadComponent: () => import('./project-workspace/project-workspace.component').then(m => m.ProjectWorkspaceComponent)
  },
  {
    path: ':id/map',
    loadComponent: () => import('./project-map/project-map.component').then(m => m.ProjectMapComponent)
  },
  {
    path: ':id/3d',
    loadComponent: () => import('./project-3d/project-3d.component').then(m => m.Project3DComponent)
  }
];
