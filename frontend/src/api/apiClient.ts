import axios, { type InternalAxiosRequestConfig } from 'axios'

const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

const apiClient = axios.create({ baseURL })

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  // Só define JSON se o body não for FormData (uploads precisam do multipart gerado pelo browser)
  if (!(config.data instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json'
  }
  return config
})

export default apiClient
