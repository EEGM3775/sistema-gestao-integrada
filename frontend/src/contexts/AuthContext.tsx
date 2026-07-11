import type { ReactNode } from 'react'
import React, { createContext, useState, useEffect } from 'react'
import axios from 'axios'
import apiClient from '../api/apiClient'
import type { User } from '../types'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'
const iamClient = axios.create({
  baseURL: iamBaseURL,
  headers: { 'Content-Type': 'application/json' },
})
iamClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

interface AuthContextType {
  isAuthenticated: boolean
  user: User | null
  modules: string[]
  permissions: string[]
  isTenantAdmin: boolean
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  hasModule: (code: string) => boolean
  hasPermission: (code: string) => boolean
}

export const AuthContext = createContext<AuthContextType>({} as AuthContextType)

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [modules, setModules] = useState<string[]>([])
  const [permissions, setPermissions] = useState<string[]>([])
  const [isTenantAdmin, setIsTenantAdmin] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setLoading(false); return }
    iamClient
      .get('me/')
      .then((response) => {
        const d = response.data
        setUser({ id: d.id, username: d.username, email: d.email })
        setModules(Array.isArray(d.modules) ? d.modules : [])
        setPermissions(Array.isArray(d.permissions) ? d.permissions : [])
        setIsTenantAdmin(!!d.is_tenant_admin)
      })
      .catch(() => {
        localStorage.removeItem('token')
        setUser(null)
        setModules([])
        setPermissions([])
        setIsTenantAdmin(false)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = async (username: string, password: string) => {
    const response = await iamClient.post('login/', { username, password })
    const token = response.data.access as string
    localStorage.setItem('token', token)
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`
    const u = response.data.user ?? {}
    setUser({ id: u.id, username: u.username, email: u.email })
    setModules(Array.isArray(response.data.modules) ? response.data.modules : [])
    setIsTenantAdmin(!!u.is_tenant_admin)
    // As permissões efetivas viajam no token; /auth/me/ as devolve na próxima carga.
    iamClient.get('me/').then((r) => {
      setPermissions(Array.isArray(r.data.permissions) ? r.data.permissions : [])
    }).catch(() => setPermissions([]))
  }

  const logout = () => {
    localStorage.removeItem('token')
    delete apiClient.defaults.headers.common['Authorization']
    setUser(null)
    setModules([])
    setPermissions([])
    setIsTenantAdmin(false)
  }

  const hasModule = (code: string) => modules.includes(code)
  const hasPermission = (code: string) => isTenantAdmin || permissions.includes(code)

  return (
    <AuthContext.Provider value={{
      isAuthenticated: !!user, user, modules, permissions, isTenantAdmin,
      loading, login, logout, hasModule, hasPermission,
    }}>
      {children}
    </AuthContext.Provider>
  )
}
