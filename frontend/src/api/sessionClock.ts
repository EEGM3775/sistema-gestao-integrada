// Relógio da sessão — ver docs/acesso-e-permissoes.md §5.2.
//
// Duas responsabilidades que nascem do mesmo desenho:
//
// 1. O refresh vive num cookie HttpOnly, OPACO ao JS: o front não tem como ler
//    quando a sessão cai. A IAM devolve `session_expires_at` (época em segundos) e
//    `session_warn_seconds` no login / refresh / troca de senha — guardamos aqui
//    para agendar o aviso de queda.
// 2. A janela de inatividade só fecha se a renovação depender de INTERAÇÃO REAL.
//    O access é renovado sozinho enquanto a aba está aberta; se essa renovação
//    também rotacionasse o refresh, um notebook destravado com a aba aberta
//    seguraria a sessão até o teto absoluto. Por isso registramos a última
//    interação e o AuthContext condiciona a renovação a ela.

type Listener = (expiraEm: number | null) => void

let expiraEm: number | null = null // época em SEGUNDOS (como vem da IAM)
let avisoSegundos = 15 * 60 // sobrescrito pela resposta da IAM
let ultimaAtividade = Date.now() // ms (Date.now)
const listeners = new Set<Listener>()

export interface CamposSessao {
  session_expires_at?: number
  session_warn_seconds?: number
}

/** Absorve os campos de sessão de uma resposta da IAM (login/refresh/senha). */
export function atualizarRelogio(data: CamposSessao | undefined | null): void {
  if (!data || typeof data.session_expires_at !== 'number') return
  expiraEm = data.session_expires_at
  if (typeof data.session_warn_seconds === 'number') avisoSegundos = data.session_warn_seconds
  listeners.forEach((l) => l(expiraEm))
}

/** Logout ou sessão perdida: para de agendar aviso/expiração. */
export function limparRelogio(): void {
  expiraEm = null
  listeners.forEach((l) => l(null))
}

export function getExpiraEm(): number | null {
  return expiraEm
}

export function getAvisoSegundos(): number {
  return avisoSegundos
}

export function onRelogioChange(l: Listener): () => void {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}

export function marcarAtividade(): void {
  ultimaAtividade = Date.now()
}

export function getUltimaAtividade(): number {
  return ultimaAtividade
}
