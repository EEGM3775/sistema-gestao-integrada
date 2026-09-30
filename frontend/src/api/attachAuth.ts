// Interceptors de autenticação compartilhados por todos os clients (api, iam-admin).
// Não há token no navegador (BFF, fase 5): o cookie da sessão vai sozinho, e toda
// chamada leva o cabeçalho anti-CSRF que o gateway exige na escrita. Em 401,
// ou a sessão precisa ser renovada (uma tentativa, pelo cookie do refresh), ou o
// ato é grave e pede confirmação de identidade (fase 6) — nos dois casos o pedido
// é refeito uma vez.
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { exigeConfirmacao, pedirConfirmacao } from './confirmacao'
import { CABECALHO_ANTI_CSRF, renovarSessao } from './session'

type ConfigComTentativas = InternalAxiosRequestConfig & { _renovou?: boolean; _confirmou?: boolean }

export function attachAuth(instance: AxiosInstance): void {
  instance.defaults.withCredentials = true

  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    config.headers.set(CABECALHO_ANTI_CSRF)
    // Não força JSON em FormData (uploads precisam do multipart do browser).
    if (!(config.data instanceof FormData)) {
      config.headers['Content-Type'] = 'application/json'
    }
    return config
  })

  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      const original = error.config as ConfigComTentativas | undefined
      if (!original || error.response?.status !== 401) return Promise.reject(error)

      if (exigeConfirmacao(error)) {
        if (!original._confirmou && (await pedirConfirmacao())) {
          original._confirmou = true
          return instance(original)
        }
        return Promise.reject(error)
      }

      if (!original._renovou) {
        original._renovou = true
        if (await renovarSessao()) return instance(original)
      }
      return Promise.reject(error)
    },
  )
}
