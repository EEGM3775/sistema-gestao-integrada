/**
 * Models compartilhados do Dashboard Home
 */

import { Project } from '../../../projects/models/project.model';

/**
 * Interface estendida de Project com dados de UI
 */
export interface ProjectUI extends Project {
  progress: number;
  area: string;
  thumbnail: string;
  location?: { lat: number; lng: number };
}

/**
 * Interface para as estatísticas do dashboard
 */
export interface DashboardStats {
  totalProjects: number;
  processing: number;
  completed: number;
  totalImages: number;
}

/**
 * Tipo de visualização do dashboard
 */
export type ViewMode = 'grid' | 'list';
