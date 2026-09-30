export interface Project {
  id: number;
  name: string;
  description?: string;
  status: ProjectStatus;
  createdAt: string;
  updatedAt: string;
  taskCount: number;
  imageCount: number;
  owner?: string;
}

export type ProjectStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'ERROR';

export interface CreateProjectRequest {
  name: string;
  description?: string;
  // Vínculo com o ERP (Fase 3); normalmente preenchido pelo ProjectContextService.
  empreendimentoId?: number;
  obraId?: number;
}

/**
 * Resposta da API do backend Java
 */
export interface ProjectApiResponse {
  id: number;
  name: string;
  description?: string;
  imageCount?: number;
  status?: string;
  empreendimentoId?: number | null;
  obraId?: number | null;
  owner?: {
    id: number;
    username: string;
    email: string;
  };
  createdAt: string;
}

export interface ProjectTask {
  id: number;
  projectId: number;
  name: string;
  status: TaskStatus;
  progress: number;
  createdAt: string;
  completedAt?: string;
  options?: Record<string, any>;
  outputs?: TaskOutputs;
}

export type TaskStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELED';

export interface TaskOutputs {
  orthophoto?: string;
  dsm?: string;
  dtm?: string;
  pointCloud?: string;
  model3d?: string;
  report?: string;
}

// ============== Image Models ==============

export interface ProjectImage {
  id: number;
  filename: string;
  originalFilename: string;
  contentType: string;
  fileSize: number;
  uploadedAt: string;
  thumbnailUrl?: string;
}

export interface ImageUploadResponse {
  totalUploaded: number;
  totalFailed: number;
  images: ProjectImage[];
  errors: string[];
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface UploadLimits {
  maxFileSizeMb: number;
  maxRequestSizeMb: number;
  hardMaxFileSizeMb: number;
  hardMaxRequestSizeMb: number;
}

// ============== Chunk Models ==============

export type ChunkStatus = 'EMPTY' | 'READY' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELED';

export interface Chunk {
  id: number;
  projectId: number;
  name: string;
  description?: string;
  imageCount: number;
  status: ChunkStatus;
  nodeodmTaskId?: string;
  progress: number;
  outputs?: Record<string, any>;
  processingOptions?: Record<string, any>;
  errorMessage?: string;
  processingTime?: number;
  createdAt: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface ChunkCreateRequest {
  name: string;
  description?: string;
}

export interface ChunkUpdateRequest {
  name?: string;
  description?: string;
}

export interface ChunkAddImagesRequest {
  imageIds: number[];
}
