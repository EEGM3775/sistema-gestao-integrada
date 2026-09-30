import { Component, Input, signal, computed, inject, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AnnotationService } from '../../services/annotation.service';
import { Annotation } from '../../models/annotation.model';
import { AuthService } from '../../../../core/services/auth.service';

@Component({
    selector: 'app-annotations-panel',
    imports: [CommonModule, FormsModule],
    changeDetection: ChangeDetectionStrategy.OnPush,
    templateUrl: './annotations-panel.component.html',
    styleUrls: ['./annotations-panel.component.scss']
})
export class AnnotationsPanelComponent {
  @Input() projectId!: number;
  @Input() showHeader = true;

  annotationService = inject(AnnotationService);
  private authService = inject(AuthService);

  filterType = signal<string>('ALL');
  deletingId = signal<number | null>(null);
  editingId = signal<number | null>(null);
  editText = signal<string>('');
  savingEditId = signal<number | null>(null);

  private currentUserId = computed(() => this.authService.currentUser()?.id ?? -1);

  filteredAnnotations = computed(() => {
    const list = this.annotationService.annotations();
    const filter = this.filterType();
    return filter === 'ALL' ? list : list.filter(a => a.type === filter);
  });

  setFilter(type: string): void {
    this.filterType.set(type);
  }

  startEdit(annotation: Annotation): void {
    this.editingId.set(annotation.id);
    this.editText.set(annotation.text ?? '');
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.editText.set('');
  }

  saveEdit(annotation: Annotation): void {
    const text = this.editText().trim();
    this.savingEditId.set(annotation.id);
    this.annotationService.updateAnnotation(this.projectId, annotation.id, text).subscribe({
      next: () => { this.editingId.set(null); this.editText.set(''); this.savingEditId.set(null); },
      error: () => this.savingEditId.set(null)
    });
  }

  toggleVisibility(id: number): void {
    this.annotationService.toggleVisibility(id);
  }

  deleteAnnotation(annotation: Annotation): void {
    if (!this.isOwn(annotation)) return;
    this.deletingId.set(annotation.id);
    this.annotationService.deleteAnnotation(this.projectId, annotation.id).subscribe({
      next: () => this.deletingId.set(null),
      error: () => this.deletingId.set(null)
    });
  }

  isOwn(annotation: Annotation): boolean {
    const uid = this.currentUserId();
    return uid !== -1 && annotation.author.id === uid;
  }

  typeLabel(type: string): string {
    const labels: Record<string, string> = {
      MARKER: 'Marcador',
      POLYGON: 'Poligono'
    };
    return labels[type] ?? type;
  }

  formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
  }
}
