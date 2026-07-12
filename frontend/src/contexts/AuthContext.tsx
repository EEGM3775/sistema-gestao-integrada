import type { ReactNode } from 'react'
import React, { createContext, useState, useEffect } from 'react'
import axios from 'axios'
import { attachAuth } from '../api/attachAuth'
import { changePassword as changePasswordApi, loginSession, logoutSession, refreshAccess } from '../api/session'
import { getAccessToken, onAccessTokenChange } from '../api/tokenStore'
import type { User } from '../types'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'
// Cliente da IAM para /auth/me/ — com token em memória + refresh no 401.
const iamClient = axios.create({ baseURL: iamBaseURL })
attachAuth(iamClient)

interface AuthContextType {
  isAuthenticated: boolean
  user: User | null
  modules: string[]
  permissions: string[]
  isTenantAdmin: boolean
  loading: boolean
  login: (username: string, password: string, remember?: boolean) => Promise<void>
  changePassword: (senhaAtual: string, novaSenha: string) => Promise<void>
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

  const aplicarMe = (d: {
    id: string; username: string; email: string
    modules?: string[]; permissions?: string[]; is_tenant_admin?: boolean
  }) => {
    setUser({ id: d.id, username: d.username, email: d.email })
    setModules(Array.isArray(d.modules) ? d.modules : [])
    setPermissions(Array.isArray(d.permissions) ? d.permissions : [])
    setIsTenantAdmin(!!d.is_tenant_admin)
  }

  const limparEstado = () => {
    setUser(null)
    setModules([])
    setPermissions([])
    setIsTenantAdmin(false)
  }

  // Bootstrap: sem access em memória (reload), tenta renovar pelo cookie de
  // refresh. Se a sessão ainda vale, repopula tudo — o usuário NÃO reloga.
  useEffect(() => {
    let vivo = true
    refreshAccess()
      .then((token) => {
        if (!token) return
        return iamClient.get('me/').then((r) => {
          if (vivo) aplicarMe(r.data)
        })
      })
      .catch(() => {
        if (vivo) limparEstado()
      })
      .finally(() => {
        if (vivo) setLoading(false)
      })
    return () => {
      vivo = false
    }
  }, [])

  // Refresh PROATIVO: reagenda a cada troca de token para ~1 min antes de expirar,
  // de forma que nenhuma requisição chegue a falhar por token vencido.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const agendar = (token: string | null) => {
      if (timer) clearTimeout(timer)
      if (!token) return
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        const expMs = payload.exp * 1000
        const delay = Math.max(5000, expMs - Date.now() - 60_000)
        timer = setTimeout(() => { void refreshAccess() }, delay)
      } catch {
        /* token não decodificável — ignora */
      }
    }
    const desinscrever = onAccessTokenChange(agendar)
    agendar(getAccessToken())
    return () => {
      desinscrever()
      if (timer) clearTimeout(timer)
    }
  }, [])

  const login = async (username: string, password: string, remember = false) => {
    const data = await loginSession(username, password, remember)
    const u = data.user ?? ({} as NonNullable<typeof data.user>)
    setUser({ id: u.id, username: u.username, email: u.email })
    setModules(Array.isArray(data.modules) ? data.modules : [])
    setIsTenantAdmin(!!u.is_tenant_admin)
    // As permissões efetivas viajam no token; /auth/me/ as devolve.
    try {
      const me = await iamClient.get('me/')
      setPermissions(Array.isArray(me.data.permissions) ? me.data.permissions : [])
    } catch {
      setPermissions([])
    }
  }

  const changePassword = (senhaAtual: string, novaSenha: string) =>
    changePasswordApi(senhaAtual, novaSenha)

  const logout = () => {
    void logoutSession() // revoga a sessão no servidor (blacklist + limpa cookie)
    limparEstado()
  }

  const hasModule = (code: string) => modules.includes(code)
  const hasPermission = (code: string) => isTenantAdmin || permissions.includes(code)

  return (
    <AuthContext.Provider value={{
      isAuthenticated: !!user, user, modules, permissions, isTenantAdmin,
      loading, login, changePassword, logout, hasModule, hasPermission,
    }}>
      {children}
    </AuthContext.Provider>
  )
}
