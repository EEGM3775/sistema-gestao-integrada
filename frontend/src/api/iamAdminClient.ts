import axios, { type InternalAxiosRequestConfig } from 'axios'

// API de administração do tenant na IAM (papéis/personas, permissões, usuários).
// Passa pelo gateway em /iam/ (que remove o prefixo → /perfis/ na IAM).
// Guardada por IsTenantAdmin no backend.
const baseURL = (import.meta.env.VITE_IAM_ADMIN_BASE_URL as string | undefined) ?? '/iam'

const iamAdminClient = axios.create({ baseURL })

iamAdminClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['Content-Type'] = 'application/json'
  return config
})

export default iamAdminClient
