import type { ReactNode } from 'react'
import React, { createContext, useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { attachAuth } from '../api/attachAuth'
import { changePassword as changePasswordApi, loginSession, logoutSession, refreshAccess } from '../api/session'
import { getAccessToken, onAccessTokenChange } from '../api/tokenStore'
import {
  getAvisoSegundos, getExpiraEm, getUltimaAtividade, marcarAtividade, onRelogioChange,
} from '../api/sessionClock'
import { SessionWarningDialog } from '../components/SessionWarningDialog'
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
  /** Supervisor da plataforma (`is_superuser` na IAM). Diferente de
   *  `isTenantAdmin`: aquele manda na empresa dele, este atravessa o
   *  catálogo. Governa o que é da PLATAFORMA — e o que depende dele **não
   *  aparece** para os demais, nem trancado. */
  isPlatformAdmin: boolean
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
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(false)
  const [loading, setLoading] = useState(true)

  const aplicarMe = (d: {
    id: string; username: string; email: string
    modules?: string[]; permissions?: string[]
    is_tenant_admin?: boolean; is_platform_admin?: boolean
  }) => {
    setUser({ id: d.id, username: d.username, email: d.email })
    setModules(Array.isArray(d.modules) ? d.modules : [])
    setPermissions(Array.isArray(d.permissions) ? d.permissions : [])
    setIsTenantAdmin(!!d.is_tenant_admin)
    setIsPlatformAdmin(!!d.is_platform_admin)
  }

  // `logout` é dependência dos efeitos de sessão abaixo → precisa ser estável e
  // estar declarado ANTES deles (a lista de deps é avaliada durante o render).
  const limparEstado = useCallback(() => {
    setUser(null)
    setModules([])
    setPermissions([])
    setIsTenantAdmin(false)
    setIsPlatformAdmin(false)
  }, [])

  const logout = useCallback(() => {
    void logoutSession() // revoga a sessão no servidor (blacklist + limpa cookie)
    limparEstado()
  }, [limparEstado])

  // Aviso de queda: `expiraEm` (época em s) da última resposta da IAM. Não é
  // limpo quando o relógio zera, só quando a sessão é renovada ou o usuário sai —
  // senão o modal sumiria justamente ao informar que o teto foi atingido.
  const [avisoExpiraEm, setAvisoExpiraEm] = useState<number | null>(null)

  /** "Continuar conectado": rotaciona o refresh. `false` = teto atingido. */
  const continuarSessao = useCallback(async () => {
    const token = await refreshAccess()
    return !!token
  }, [])

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

  // Registra INTERAÇÃO REAL. Não basta a aba estar aberta: é isso que diferencia
  // "trabalhando" de "notebook destravado e abandonado".
  useEffect(() => {
    const eventos = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'] as const
    const registrar = () => marcarAtividade()
    eventos.forEach((e) => window.addEventListener(e, registrar, { passive: true }))
    return () => eventos.forEach((e) => window.removeEventListener(e, registrar))
  }, [])

  // Refresh PROATIVO do access (~1 min antes de expirar), CONDICIONADO a interação
  // real desde a emissão do token. Renovar só por ter aba aberta anularia a janela
  // de inatividade da sessão (docs/acesso-e-permissoes.md §5.2): como a rotação do
  // refresh ESTENDE essa janela, uma aba esquecida seguraria a sessão até o teto.
  // Ocioso, deixamos o access expirar — quando o usuário voltar, o interceptor do
  // attachAuth renova sob demanda no primeiro 401 (a sessão em si ainda vale).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let emitidoEm = Date.now()
    const agendar = (token: string | null) => {
      if (timer) clearTimeout(timer)
      if (!token) return
      emitidoEm = Date.now()
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        const expMs = payload.exp * 1000
        const delay = Math.max(5000, expMs - Date.now() - 60_000)
        timer = setTimeout(() => {
          if (getUltimaAtividade() > emitidoEm) void refreshAccess()
        }, delay)
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

  // Aviso de queda + logout na expiração, a partir do `session_expires_at` da IAM.
  useEffect(() => {
    let tAviso: ReturnType<typeof setTimeout> | undefined
    let tQueda: ReturnType<typeof setTimeout> | undefined
    const agendar = (expiraEm: number | null) => {
      if (tAviso) clearTimeout(tAviso)
      if (tQueda) clearTimeout(tQueda)
      // Relógio zerado (refresh recusado ou logout): NÃO fecha um aviso já aberto —
      // é justamente nele que o usuário lê que o tempo máximo foi atingido.
      if (!expiraEm) return
      setAvisoExpiraEm(null) // sessão renovada com sucesso → fecha o aviso
      const faltaMs = expiraEm * 1000 - Date.now()
      tAviso = setTimeout(
        () => setAvisoExpiraEm(expiraEm),
        Math.max(0, faltaMs - getAvisoSegundos() * 1000),
      )
      tQueda = setTimeout(() => logout(), Math.max(0, faltaMs))
    }
    const desinscrever = onRelogioChange(agendar)
    agendar(getExpiraEm())
    return () => {
      desinscrever()
      if (tAviso) clearTimeout(tAviso)
      if (tQueda) clearTimeout(tQueda)
    }
  }, [logout])

  const login = async (username: string, password: string, remember = false) => {
    const data = await loginSession(username, password, remember)
    const u = data.user ?? ({} as NonNullable<typeof data.user>)
    setUser({ id: u.id, username: u.username, email: u.email })
    setModules(Array.isArray(data.modules) ? data.modules : [])
    setIsTenantAdmin(!!u.is_tenant_admin)
    setIsPlatformAdmin(!!u.is_platform_admin)
    // As permissões efetivas viajam no token; /auth/me/ as devolve.
    try {
      const me = await iamClient.get('me/')
      setPermissions(Array.isArray(me.data.permissions) ? me.data.permissions : [])
      // `me` é a fonte mais fresca dos dois flags — o payload do login pode ser
      // anterior a uma promoção feita enquanto a sessão já existia.
      if (typeof me.data.is_platform_admin === 'boolean') {
        setIsPlatformAdmin(me.data.is_platform_admin)
      }
    } catch {
      setPermissions([])
    }
  }

  const changePassword = (senhaAtual: string, novaSenha: string) =>
    changePasswordApi(senhaAtual, novaSenha)

  const hasModule = (code: string) => modules.includes(code)
  const hasPermission = (code: string) => isTenantAdmin || permissions.includes(code)

  return (
    <AuthContext.Provider value={{
      isAuthenticated: !!user, user, modules, permissions, isTenantAdmin, isPlatformAdmin,
      loading, login, changePassword, logout, hasModule, hasPermission,
    }}>
      {children}
      {/* Gated por `user`: no logout o modal some junto com a sessão. */}
      {user && avisoExpiraEm !== null && (
        <SessionWarningDialog
          expiraEm={avisoExpiraEm}
          onContinuar={continuarSessao}
          onSair={logout}
        />
      )}
    </AuthContext.Provider>
  )
}
