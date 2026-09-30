import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ProjectService } from '../services/project.service';
import { CardComponent } from '../../../shared/components/card/card.component';
import { ButtonComponent } from '../../../shared/components/button/button.component';

@Component({
  selector: 'app-project-create',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, CardComponent, ButtonComponent],
  template: `
    <div class="create-project-page">
      <header class="page-header">
        <a routerLink="/projects" class="back-link">← Voltar para Projetos</a>
        <h1>Novo Projeto</h1>
        <p>Crie um novo projeto de fotogrametria</p>
      </header>

      <app-card class="form-card">
        <form [formGroup]="projectForm" (ngSubmit)="onSubmit()">
          <div class="form-section">
            <h3>Informações Básicas</h3>
            
            <div class="form-group">
              <label for="name">Nome do Projeto *</label>
              <input
                type="text"
                id="name"
                formControlName="name"
                placeholder="Ex: Obra Residencial XYZ"
                [class.error]="isFieldInvalid('name')"
              />
              <span class="error-message" *ngIf="isFieldInvalid('name')">
                Nome é obrigatório (mín. 3 caracteres)
              </span>
            </div>

            <div class="form-group">
              <label for="description">Descrição</label>
              <textarea
                id="description"
                formControlName="description"
                rows="4"
                placeholder="Descreva o objetivo do projeto..."
              ></textarea>
            </div>
          </div>

          <div class="form-section">
            <h3>Upload de Imagens</h3>
            <div class="upload-area" 
                 (dragover)="onDragOver($event)" 
                 (dragleave)="onDragLeave($event)"
                 (drop)="onDrop($event)"
                 [class.dragover]="isDragOver"
            >
              <div class="upload-content">
                <span class="upload-icon">📷</span>
                <p>Arraste imagens aqui ou</p>
                <input 
                  type="file" 
                  id="images" 
                  multiple 
                  accept="image/*"
                  (change)="onFilesSelected($event)"
                  hidden
                />
                <label for="images" class="upload-btn">Selecionar Arquivos</label>
              </div>
            </div>

            <div *ngIf="selectedFiles.length > 0" class="files-preview">
              <p>{{ selectedFiles.length }} arquivo(s) selecionado(s)</p>
              <div class="file-list">
                <div *ngFor="let file of selectedFiles; let i = index" class="file-item">
                  <span>{{ file.name }}</span>
                  <button type="button" (click)="removeFile(i)">×</button>
                </div>
              </div>
            </div>
          </div>

          <div class="form-section">
            <h3>Opções de Processamento</h3>
            
            <div class="options-grid">
              <label class="checkbox-option">
                <input type="checkbox" formControlName="generateOrthophoto" />
                <span>Gerar Ortofoto</span>
              </label>
              <label class="checkbox-option">
                <input type="checkbox" formControlName="generateDsm" />
                <span>Gerar DSM (Modelo Digital de Superfície)</span>
              </label>
              <label class="checkbox-option">
                <input type="checkbox" formControlName="generateDtm" />
                <span>Gerar DTM (Modelo Digital de Terreno)</span>
              </label>
              <label class="checkbox-option">
                <input type="checkbox" formControlName="generate3dModel" />
                <span>Gerar Modelo 3D</span>
              </label>
              <label class="checkbox-option">
                <input type="checkbox" formControlName="generatePointCloud" />
                <span>Gerar Nuvem de Pontos</span>
              </label>
            </div>
          </div>

          <div class="form-actions">
            <app-button type="button" variant="secondary" routerLink="/projects">
              Cancelar
            </app-button>
            <app-button 
              type="submit" 
              [loading]="isSubmitting" 
              [disabled]="projectForm.invalid"
            >
              Criar Projeto
            </app-button>
          </div>
        </form>
      </app-card>
    </div>
  `,
  styles: [`
    .create-project-page {
      padding: 1.5rem;
      max-width: 800px;
      margin: 0 auto;
    }

    .page-header {
      margin-bottom: 1.5rem;
    }

    .back-link {
      color: var(--color-text-muted);
      text-decoration: none;
      font-size: 0.9rem;
      display: inline-block;
      margin-bottom: 0.5rem;
    }

    .back-link:hover {
      color: var(--color-primary);
    }

    .page-header h1 {
      margin: 0;
      font-size: 1.75rem;
      color: var(--color-text);
    }

    .page-header p {
      margin: 0.25rem 0 0;
      color: var(--color-text-muted);
    }

    .form-card {
      max-width: 100%;
    }

    .form-section {
      margin-bottom: 2rem;
    }

    .form-section h3 {
      margin: 0 0 1rem;
      font-size: 1.1rem;
      color: var(--color-text);
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--color-border);
    }

    .form-group {
      margin-bottom: 1.25rem;
    }

    label {
      display: block;
      margin-bottom: 0.5rem;
      font-weight: 500;
      color: var(--color-text-secondary);
    }

    input[type="text"], textarea {
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid var(--color-border);
      border-radius: 6px;
      font-size: 1rem;
      font-family: inherit;
      transition: border-color 0.2s, box-shadow 0.2s;
      box-sizing: border-box;
      background: var(--color-bg-white);
      color: var(--color-text);
    }

    input:focus, textarea:focus {
      outline: none;
      border-color: var(--color-primary);
      box-shadow: 0 0 0 3px var(--color-primary-bg);
    }

    input.error {
      border-color: var(--color-danger);
    }

    .error-message {
      display: block;
      margin-top: 0.25rem;
      font-size: 0.875rem;
      color: var(--color-danger);
    }

    .upload-area {
      border: 2px dashed var(--color-border);
      border-radius: 8px;
      padding: 2rem;
      text-align: center;
      transition: all 0.2s;
      background: var(--color-bg);
    }

    .upload-area.dragover {
      border-color: var(--color-primary);
      background: var(--color-primary-bg);
    }

    .upload-icon {
      font-size: 3rem;
      display: block;
      margin-bottom: 0.5rem;
    }

    .upload-content p {
      margin: 0 0 0.75rem;
      color: var(--color-text-muted);
    }

    .upload-btn {
      display: inline-block;
      padding: 0.5rem 1.25rem;
      background: var(--color-primary);
      color: white;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 500;
      transition: background 0.2s;
    }

    .upload-btn:hover {
      background: var(--color-primary-dark);
    }

    .files-preview {
      margin-top: 1rem;
      padding: 1rem;
      background: var(--color-bg-white);
      border-radius: 6px;
      border: 1px solid var(--color-border);
    }

    .files-preview > p {
      margin: 0 0 0.75rem;
      font-weight: 500;
      color: var(--color-text);
    }

    .file-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .file-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.375rem 0.75rem;
      background: var(--color-bg);
      border-radius: 4px;
      font-size: 0.85rem;
      border: 1px solid var(--color-border);
    }

    .file-item button {
      background: none;
      border: none;
      cursor: pointer;
      font-size: 1.1rem;
      color: var(--color-text-muted);
      padding: 0;
      line-height: 1;
    }

    .file-item button:hover {
      color: var(--color-danger);
    }

    .options-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 0.75rem;
    }

    .checkbox-option {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.75rem;
      background: var(--color-bg);
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.2s;
      border: 1px solid var(--color-border);
    }

    .checkbox-option:hover {
      background: var(--color-bg-hover);
    }

    .checkbox-option input {
      width: 18px;
      height: 18px;
      cursor: pointer;
    }

    .checkbox-option span {
      font-weight: normal;
      color: var(--color-text-secondary);
    }

    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 1rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--color-border);
    }
  `]
})
export class ProjectCreateComponent {
  projectForm: FormGroup;
  isSubmitting = false;
  isDragOver = false;
  selectedFiles: File[] = [];

  constructor(
    private fb: FormBuilder,
    private projectService: ProjectService,
    private router: Router
  ) {
    this.projectForm = this.fb.group({
      name: ['', [Validators.required, Validators.minLength(3)]],
      description: [''],
      generateOrthophoto: [true],
      generateDsm: [true],
      generateDtm: [false],
      generate3dModel: [false],
      generatePointCloud: [true]
    });
  }

  isFieldInvalid(field: string): boolean {
    const control = this.projectForm.get(field);
    return !!(control && control.invalid && control.touched);
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = true;
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = false;
    
    const files = event.dataTransfer?.files;
    if (files) {
      this.addFiles(Array.from(files));
    }
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      this.addFiles(Array.from(input.files));
    }
  }

  addFiles(files: File[]): void {
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    this.selectedFiles = [...this.selectedFiles, ...imageFiles];
  }

  removeFile(index: number): void {
    this.selectedFiles.splice(index, 1);
  }

  onSubmit(): void {
    if (this.projectForm.invalid) {
      this.projectForm.markAllAsTouched();
      return;
    }

    this.isSubmitting = true;

    this.projectService.createProject({
      name: this.projectForm.value.name,
      description: this.projectForm.value.description
    }).subscribe({
      next: (project) => {
        // TODO: Upload files to project
        this.router.navigate(['/projects', project.id]);
      },
      error: () => {
        this.isSubmitting = false;
      }
    });
  }
}
