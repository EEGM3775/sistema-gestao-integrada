/**
 * Models para o componente Project List
 */

export type SortField = 'name' | 'createdAt' | 'updatedAt' | 'imageCount' | 'status';
export type SortDirection = 'asc' | 'desc';

export interface ProjectFilters {
  status: string;
  search: string;
  dateFrom: string;
  dateTo: string;
}

export interface SortConfig {
  field: SortField;
  direction: SortDirection;
}
