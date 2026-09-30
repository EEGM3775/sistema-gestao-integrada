import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { CardComponent } from '../../../shared/components/card/card.component';

@Component({
    selector: 'app-register',
    imports: [CommonModule, ReactiveFormsModule, RouterLink, ButtonComponent, CardComponent],
    template: `
    <div class="auth-container">
      <app-card title="Criar Conta" subtitle="Junte-se ao Projeto Phoenix">
        <form [formGroup]="registerForm" (ngSubmit)="onSubmit()">
          <div class="form-group">
            <label for="username">Usuário</label>
            <input
              type="text"
              id="username"
              formControlName="username"
              placeholder="Escolha um nome de usuário"
              [class.error]="isFieldInvalid('username')"
            />
            <span class="error-message" *ngIf="isFieldInvalid('username')">
              {{ getUsernameError() }}
            </span>
          </div>

          <div class="form-group">
            <label for="email">E-mail</label>
            <input
              type="email"
              id="email"
              formControlName="email"
              placeholder="Digite seu e-mail"
              [class.error]="isFieldInvalid('email')"
            />
            <span class="error-message" *ngIf="isFieldInvalid('email')">
              {{ getEmailError() }}
            </span>
          </div>

          <div class="form-group">
            <label for="password">Senha</label>
            <input
              type="password"
              id="password"
              formControlName="password"
              placeholder="Crie uma senha forte"
              [class.error]="isFieldInvalid('password')"
            />
            <span class="error-message" *ngIf="isFieldInvalid('password')">
              {{ getPasswordError() }}
            </span>
          </div>

          <div class="form-group">
            <label for="confirmPassword">Confirmar Senha</label>
            <input
              type="password"
              id="confirmPassword"
              formControlName="confirmPassword"
              placeholder="Repita a senha"
              [class.error]="isFieldInvalid('confirmPassword') || passwordMismatch"
            />
            <span class="error-message" *ngIf="passwordMismatch">
              As senhas não coincidem
            </span>
          </div>

          <div class="error-alert" *ngIf="errorMessage">
            {{ errorMessage }}
          </div>

          <div class="success-alert" *ngIf="successMessage">
            {{ successMessage }}
          </div>

          <app-button
            type="submit"
            [block]="true"
            [loading]="isLoading"
            [disabled]="isLoading"
          >
            Criar Conta
          </app-button>

          <p class="auth-link">
            Já tem uma conta? <a routerLink="/auth/login">Faça login</a>
          </p>
        </form>
      </app-card>
    </div>
  `,
    styles: [`
    .auth-container {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 1rem;
    }

    app-card {
      width: 100%;
      max-width: 400px;
    }

    .form-group {
      margin-bottom: 1.25rem;
    }

    label {
      display: block;
      margin-bottom: 0.5rem;
      font-weight: 500;
      color: #374151;
    }

    input {
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      font-size: 1rem;
      transition: border-color 0.2s, box-shadow 0.2s;
      box-sizing: border-box;
    }

    input:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
    }

    input.error {
      border-color: #dc2626;
    }

    .error-message {
      display: block;
      margin-top: 0.25rem;
      font-size: 0.875rem;
      color: #dc2626;
    }

    .error-alert {
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 6px;
      color: #dc2626;
      font-size: 0.875rem;
    }

    .success-alert {
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      border-radius: 6px;
      color: #166534;
      font-size: 0.875rem;
    }

    .auth-link {
      text-align: center;
      margin-top: 1.25rem;
      margin-bottom: 0;
      color: #6b7280;
    }

    .auth-link a {
      color: #2563eb;
      text-decoration: none;
      font-weight: 500;
    }

    .auth-link a:hover {
      text-decoration: underline;
    }
  `]
})
export class RegisterComponent {
  registerForm: FormGroup;
  isLoading = false;
  errorMessage = '';
  successMessage = '';

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router
  ) {
    this.registerForm = this.fb.group({
      username: ['', [Validators.required, Validators.minLength(3)]],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
      confirmPassword: ['', Validators.required]
    });
  }

  get passwordMismatch(): boolean {
    const password = this.registerForm.get('password')?.value;
    const confirmPassword = this.registerForm.get('confirmPassword')?.value;
    return confirmPassword && password !== confirmPassword;
  }

  isFieldInvalid(field: string): boolean {
    const control = this.registerForm.get(field);
    return !!(control && control.invalid && control.touched);
  }

  onSubmit(): void {
    if (this.registerForm.invalid || this.passwordMismatch) {
      this.registerForm.markAllAsTouched();
      this.errorMessage = this.passwordMismatch ? 'As senhas não coincidem' : 'Verifique os campos obrigatórios.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';
    this.successMessage = '';

    const { confirmPassword, ...registerData } = this.registerForm.value;

    this.authService.register(registerData).subscribe({
      next: () => {
        this.isLoading = false;
        this.successMessage = 'Conta criada com sucesso! Redirecionando...';
        setTimeout(() => {
          this.router.navigate(['/auth/login']);
        }, 2000);
      },
      error: (err) => {
        this.isLoading = false;
        this.errorMessage = this.formatRegisterError(err);
      }
    });
  }

  getUsernameError(): string {
    const control = this.registerForm.get('username');
    if (!control || !control.touched) return '';
    if (control.hasError('required')) return 'Usuário é obrigatório';
    if (control.hasError('minlength')) return 'Usuário deve ter pelo menos 3 caracteres';
    return 'Usuário inválido';
  }

  getEmailError(): string {
    const control = this.registerForm.get('email');
    if (!control || !control.touched) return '';
    if (control.hasError('required')) return 'E-mail é obrigatório';
    if (control.hasError('email')) return 'Informe um e-mail válido';
    return 'E-mail inválido';
  }

  getPasswordError(): string {
    const control = this.registerForm.get('password');
    if (!control || !control.touched) return '';
    if (control.hasError('required')) return 'Senha é obrigatória';
    if (control.hasError('minlength')) return 'Senha deve ter no mínimo 6 caracteres';
    return 'Senha inválida';
  }

  private formatRegisterError(err: any): string {
    if (!err) return 'Erro ao criar conta. Tente novamente.';
    if (err.error && typeof err.error === 'string') return err.error;

    const fieldErrors = err.error?.fieldErrors;
    if (fieldErrors && typeof fieldErrors === 'object') {
      const messages = Object.values(fieldErrors).filter(Boolean);
      if (messages.length) return messages.join(' • ');
    }

    if (err.status === 0) return 'Falha de conexão com o servidor.';
    return err.error?.message || 'Erro ao criar conta. Tente novamente.';
  }
}
