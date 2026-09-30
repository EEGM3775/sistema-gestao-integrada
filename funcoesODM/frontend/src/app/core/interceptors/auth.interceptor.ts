import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';
import { AuthService, CABECALHO_ANTI_CSRF } from '../services/auth.service';

/**
 * BFF (fase 5): nenhum token sai daqui. O cookie da sessão vai sozinho (mesma
 * origem) e o gateway põe o access do drone no pedido; toda chamada leva o
 * cabeçalho anti-CSRF que ele exige na escrita. Num 401, a sessão é renovada uma
 * vez pelo cookie do refresh e o pedido é refeito; sem sessão, volta ao login da
 * plataforma. 403 é "não pode", e não "saia".
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const autenticado = req.clone({ withCredentials: true, setHeaders: CABECALHO_ANTI_CSRF });
  const daPropriaSessao = /\/auth\/(login|refresh|logout)\/?$/.test(req.url);

  return next(autenticado).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || daPropriaSessao) {
        return throwError(() => error);
      }
      return from(authService.renovar()).pipe(
        switchMap((ok) => {
          if (ok) {
            return next(autenticado);
          }
          authService.irParaLogin();
          return throwError(() => error);
        })
      );
    })
  );
};
