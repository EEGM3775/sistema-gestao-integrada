// Access token EM MEMÓRIA (nunca em localStorage — imune a XSS de leitura; Fase 10.6).
// O refresh vive num cookie HttpOnly no servidor. Perder este valor num reload é
// esperado: o bootstrap chama /auth/refresh/ (cookie) e repopula.
let accessToken: string | null = null

type Listener = (token: string | null) => void
const listeners = new Set<Listener>()

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
  listeners.forEach((l) => l(token))
}

/** Observa mudanças do token (usado para agendar o refresh proativo). */
export function onAccessTokenChange(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
