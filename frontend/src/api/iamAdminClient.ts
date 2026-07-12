import axios from 'axios'
import { attachAuth } from './attachAuth'

// API de administração do tenant na IAM (papéis/personas, permissões, usuários).
// Passa pelo gateway em /iam/ (que remove o prefixo → /perfis/ na IAM).
// Guardada por IsTenantAdmin no backend.
const baseURL = (import.meta.env.VITE_IAM_ADMIN_BASE_URL as string | undefined) ?? '/iam'

const iamAdminClient = axios.create({ baseURL })
attachAuth(iamAdminClient) // access em memória + refresh silencioso no 401

export default iamAdminClient
