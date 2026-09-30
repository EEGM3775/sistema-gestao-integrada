// Ciclo de sessão contra a IAM — BFF (docs/acesso-e-permissoes.md §10.5, fase 5).
// O navegador não guarda token: a IAM grava dois cookies HttpOnly (o refresh, que
// desliza a janela, e a sessão, que o gateway troca pelo access de cada serviço).
// Cliente "cru" (sem os interceptors de renovação) e com `withCredentials`.
import axios from 'axios'
import { atualizarRelogio, limparRelogio } from './sessionClock'
import type { DesafioSegundoFator } from './segundoFator'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'

export const CABECALHO_ANTI_CSRF = { 'X-SGI-CSRF': '1' } as const

const raw = axios.create({
  baseURL: iamBaseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json', ...CABECALHO_ANTI_CSRF },
})

export interface LoginData {
  user: { id: string; username: string; email: string; is_tenant_admin?: boolean; is_platform_admin?: boolean }
  tenant: { id: string; slug: string; nome: string } | null
  modules: string[]
  // Quando a sessão (refresh) cai e com quanta antecedência avisar. Vem da IAM
  // porque os cookies da sessão são HttpOnly e o front não consegue lê-los.
  session_expires_at?: number
  session_warn_seconds?: number
}

/** A senha certa de quem tem (ou é obrigado a ter) segundo fator não abre
 *  sessão: devolve o desafio da segunda etapa. */
export function pedeSegundoFator(data: LoginData | DesafioSegundoFator): data is DesafioSegundoFator {
  return 'segundo_fator' in data && 'desafio' in data
}

export async function loginSession(
  username: string,
  password: string,
  remember: boolean,
): Promise<LoginData | DesafioSegundoFator> {
  const r = await raw.post('login/', { username, password, remember })
  const data = r.data as LoginData | DesafioSegundoFator
  if (!pedeSegundoFator(data)) atualizarRelogio(data)
  return data
}

// Renovação silenciosa. Single-flight: várias 401 concorrentes compartilham um
// único POST /auth/refresh/ (senão a rotação dispararia detecção de reuso).
let inflight: Promise<boolean> | null = null

export function renovarSessao(): Promise<boolean> {
  if (!inflight) {
    inflight = raw
      .post('refresh/')
      .then((r) => {
        atualizarRelogio(r.data)
        return true
      })
      .catch(() => {
        limparRelogio()
        return false
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

export async function changePassword(senhaAtual: string, novaSenha: string): Promise<void> {
  // Encerra as OUTRAS sessões no servidor e abre uma nova para este aparelho
  // (novos cookies na própria resposta).
  const r = await raw.post('senha/', { senha_atual: senhaAtual, nova_senha: novaSenha })
  atualizarRelogio(r.data)
}

export async function logoutSession(): Promise<void> {
  try {
    await raw.post('logout/')
  } catch {
    /* mesmo se falhar no servidor, limpamos o estado local abaixo */
  }
  limparRelogio()
}
