import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';

/** Sem sessão da plataforma (cookie do BFF), a pessoa volta ao login dela. */
export const authGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  if (authService.isAuthenticated() || (await authService.carregar())) {
    return true;
  }
  authService.irParaLogin();
  return false;
};

/**
 * Guard to prevent authenticated users from accessing auth pages (login, register)
 */
export const guestGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!(authService.isAuthenticated() || (await authService.carregar()))) {
    return true;
  }

  router.navigate(['/dashboard']);
  return false;
};
