import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, firstValueFrom, from, map, switchMap, of } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface User {
  id: number;
  username: string;
  email: string;
  roles?: string[];
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

/** Cabeçalho que o gateway exige em toda escrita feita com o cookie da sessão. */
export const CABECALHO_ANTI_CSRF = { 'X-SGI-CSRF': '1' };

/**
 * Sessão do drone pelo BFF (remodelagem, fase 5 — docs/acesso-e-permissoes.md §10.5).
 *
 * O navegador não guarda token nenhum: a IAM grava o cookie HttpOnly da sessão no
 * login da plataforma, e o gateway troca esse cookie pelo access do drone em cada
 * chamada a /odm-api e /ws. Aqui só se pergunta ao drone quem é a pessoa desta
 * sessão (o espelho local, com o id que as anotações usam).
 */
@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = `${environment.apiUrl}/auth`;
  private iamUrl = '/auth';

  private currentUserSignal = signal<User | null>(null);
  private isAuthenticatedSignal = signal<boolean>(false);
  private carregando?: Promise<boolean>;
  private renovando?: Promise<boolean>;

  readonly currentUser = computed(() => this.currentUserSignal());
  readonly isAuthenticated = computed(() => this.isAuthenticatedSignal());

  constructor(private http: HttpClient) {}

  /** Quem é a pessoa desta sessão? `false` quando não há sessão válida. */
  carregar(): Promise<boolean> {
    if (!this.carregando) {
      this.carregando = firstValueFrom(this.http.get<User>(`${this.apiUrl}/me`))
        .then((user) => {
          this.currentUserSignal.set(user);
          this.isAuthenticatedSignal.set(true);
          return true;
        })
        .catch(() => {
          this.currentUserSignal.set(null);
          this.isAuthenticatedSignal.set(false);
          this.carregando = undefined;
          return false;
        });
    }
    return this.carregando;
  }

  /** Renova a sessão pelo cookie do refresh (uma chamada por vez). */
  renovar(): Promise<boolean> {
    if (!this.renovando) {
      this.renovando = firstValueFrom(
        this.http.post(`${this.iamUrl}/refresh/`, {}, { withCredentials: true, headers: CABECALHO_ANTI_CSRF })
      )
        .then(() => true)
        .catch(() => false)
        .finally(() => {
          this.renovando = undefined;
        });
    }
    return this.renovando;
  }

  /** O login é o da plataforma: sem sessão, a pessoa volta para lá. */
  irParaLogin(): void {
    window.location.href = environment.iamLoginUrl || '/login';
  }

  /**
   * Entrar pela tela do próprio drone: é o login da IAM, que grava o cookie da
   * sessão. Quem tem (ou é obrigado a ter) segundo fator termina na tela de
   * login da plataforma, que conduz a segunda etapa.
   */
  login(credentials: LoginRequest): Observable<boolean> {
    return this.http
      .post<{ segundo_fator?: string }>(`${this.iamUrl}/login/`, credentials, {
        withCredentials: true,
        headers: CABECALHO_ANTI_CSRF,
      })
      .pipe(
        switchMap((resposta) => {
          if (resposta?.segundo_fator) {
            this.irParaLogin();
            return of(false);
          }
          this.carregando = undefined;
          return from(this.carregar());
        })
      );
  }

  register(data: RegisterRequest): Observable<string> {
    return this.http.post(`${this.apiUrl}/register`, data, { responseType: 'text' });
  }

  logout(): void {
    this.http
      .post(`${this.iamUrl}/logout/`, {}, { withCredentials: true, headers: CABECALHO_ANTI_CSRF })
      .pipe(map(() => true))
      .subscribe({ complete: () => this.sair(), error: () => this.sair() });
  }

  private sair(): void {
    this.currentUserSignal.set(null);
    this.isAuthenticatedSignal.set(false);
    this.carregando = undefined;
    this.irParaLogin();
  }
}
