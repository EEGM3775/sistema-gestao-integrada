// Ciclo de sessão contra a IAM (Fase 10.6 / F1). Cliente "cru" (sem os
// interceptors de refresh) e com `withCredentials` para enviar/receber o cookie
// HttpOnly do refresh. O access token volta no corpo e é guardado em memória.
import axios from 'axios'
import { getAccessToken, setAccessToken } from './tokenStore'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'

const raw = axios.create({
  baseURL: iamBaseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export interface LoginData {
  access: string
  user: { id: string; username: string; email: string; is_tenant_admin?: boolean; is_platform_admin?: boolean }
  tenant: { id: string; slug: string; nome: string } | null
  modules: string[]
}

export async function loginSession(
  username: string,
  password: string,
  remember: boolean,
): Promise<LoginData> {
  const r = await raw.post('login/', { username, password, remember })
  setAccessToken(r.data.access as string)
  return r.data as LoginData
}

// Renovação silenciosa. Single-flight: várias 401 concorrentes compartilham um
// único POST /auth/refresh/ (senão a rotação dispararia detecção de reuso).
let inflight: Promise<string | null> | null = null

export function refreshAccess(): Promise<string | null> {
  if (!inflight) {
    inflight = raw
      .post('refresh/')
      .then((r) => {
        const t = (r.data?.access as string) ?? null
        setAccessToken(t)
        return t
      })
      .catch(() => {
        setAccessToken(null)
        return null
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

export async function changePassword(senhaAtual: string, novaSenha: string): Promise<void> {
  // Troca a senha e encerra as OUTRAS sessões no servidor; devolve um access novo
  // para este dispositivo (que não é deslogado). O endpoint é autenticado por
  // Bearer (não pelo cookie), então anexamos o access token da memória.
  const token = getAccessToken()
  const r = await raw.post(
    'senha/',
    { senha_atual: senhaAtual, nova_senha: novaSenha },
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
  )
  if (r.data?.access) setAccessToken(r.data.access as string)
}

export async function logoutSession(): Promise<void> {
  try {
    await raw.post('logout/')
  } catch {
    /* mesmo se falhar no servidor, limpamos o estado local abaixo */
  }
  setAccessToken(null)
}
