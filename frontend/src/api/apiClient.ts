import axios from 'axios'
import { attachAuth } from './attachAuth'

const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

const apiClient = axios.create({ baseURL })
attachAuth(apiClient) // access em memória + refresh silencioso no 401

export default apiClient
