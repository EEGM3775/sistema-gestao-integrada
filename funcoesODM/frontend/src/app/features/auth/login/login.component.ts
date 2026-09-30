import { Component, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '../../../core/services/auth.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { CardComponent } from '../../../shared/components/card/card.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, ButtonComponent, CardComponent],
  template: `
    <div class="auth-container">
      <app-card title="Projeto Phoenix" subtitle="Plataforma de Fotogrametria">
        <form [formGroup]="loginForm" (ngSubmit)="onSubmit()">
          <div class="form-group">
            <label for="username">Usuário</label>
            <input
              type="text"
              id="username"
              formControlName="username"
              placeholder="Digite seu usuário"
              [class.error]="isFieldInvalid('username')"
            />
            <span class="error-message" *ngIf="isFieldInvalid('username')">
              Usuário é obrigatório
            </span>
          </div>

          <div class="form-group">
            <label for="password">Senha</label>
            <input
              type="password"
              id="password"
              formControlName="password"
              placeholder="Digite sua senha"
              [class.error]="isFieldInvalid('password')"
            />
            <span class="error-message" *ngIf="isFieldInvalid('password')">
              Senha é obrigatória
            </span>
          </div>

          <div class="error-alert" *ngIf="errorMessage">
            {{ errorMessage }}
          </div>

          <app-button
            type="submit"
            [block]="true"
            [loading]="isLoading"
            [disabled]="loginForm.invalid"
          >
            Entrar
          </app-button>

          <p class="auth-link">
            Não tem uma conta? <a routerLink="/auth/register">Registre-se</a>
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
export class LoginComponent {
  private destroyRef = inject(DestroyRef);
  
  loginForm: FormGroup;
  isLoading = false;
  errorMessage = '';
  private returnUrl: string;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {
    this.loginForm = this.fb.group({
      username: ['', Validators.required],
      password: ['', Validators.required]
    });

    this.returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/dashboard';
  }

  isFieldInvalid(field: string): boolean {
    const control = this.loginForm.get(field);
    return !!(control && control.invalid && control.touched);
  }

  onSubmit(): void {
    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    this.authService.login(this.loginForm.value)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.router.navigateByUrl(this.returnUrl);
        },
        error: (err) => {
          this.isLoading = false;
          this.errorMessage = err.error?.message || 'Usuário ou senha inválidos';
        }
      });
  }
}
