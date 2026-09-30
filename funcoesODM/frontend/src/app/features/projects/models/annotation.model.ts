export interface Annotation {
  id: number;
  projectId: number;
  author: { id: number; username: string };
  type: 'MARKER' | 'POLYGON';
  coordinatesJson: string;
  text: string;
  visible: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateAnnotationRequest {
  type: string;
  coordinatesJson: string;
  text: string;
}
