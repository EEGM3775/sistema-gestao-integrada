// Interceptors de autenticação compartilhados por todos os clients (api, iam-admin).
// Request: injeta o access token da memória. Response: em 401, tenta UMA renovação
// silenciosa (/auth/refresh/ via cookie) e refaz a requisição; se falhar, propaga.
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { getAccessToken } from './tokenStore'
import { refreshAccess } from './session'

export function attachAuth(instance: AxiosInstance): void {
  instance.defaults.withCredentials = true

  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getAccessToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    // Não força JSON em FormData (uploads precisam do multipart do browser).
    if (!(config.data instanceof FormData)) {
      config.headers['Content-Type'] = 'application/json'
    }
    return config
  })

  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
      if (error.response?.status === 401 && original && !original._retry) {
        original._retry = true
        const token = await refreshAccess()
        if (token) {
          original.headers = original.headers ?? {}
          original.headers.Authorization = `Bearer ${token}`
          return instance(original)
        }
      }
      return Promise.reject(error)
    },
  )
}
