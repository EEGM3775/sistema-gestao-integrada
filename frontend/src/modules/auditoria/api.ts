import apiClient from '@/api/apiClient'
import iamAdminClient from '@/api/iamAdminClient'

/** Recorte comum das duas trilhas (D17): período ISO (data) e login de quem. */
export interface FiltroTrilha {
  desde?: string
  ate?: string
  pessoa?: string
}

export interface Pagina<T> {
  count: number
  next: string | null
  results: T[]
}

/** Linha da trilha do backend (`nucleo.AuditLog`). */
export interface LinhaSistema {
  id: number
  usuario: number | null
  usuario_nome: string
  acao: string
  modelo: string
  objeto_id: string
  detalhes: Record<string, unknown> | null
  timestamp: string
}

/** Linha da trilha de identidade (`identity.EventoSeguranca`, na IAM). */
export interface LinhaIdentidade {
  id: number
  tipo: string
  tipo_rotulo: string
  alvo_username: string
  autor_username: string
  ip: string | null
  user_agent: string
  detalhes: Record<string, unknown>
  criado_em: string
}

function params(f: FiltroTrilha, page: number) {
  return {
    page,
    ...(f.desde ? { desde: f.desde } : {}),
    ...(f.ate ? { ate: f.ate } : {}),
    ...(f.pessoa ? { pessoa: f.pessoa } : {}),
  }
}

export async function trilhaDoSistema(f: FiltroTrilha, page: number): Promise<Pagina<LinhaSistema>> {
  const { data } = await apiClient.get<Pagina<LinhaSistema>>('/auditoria/', { params: params(f, page) })
  return data
}

export async function trilhaDeIdentidade(f: FiltroTrilha, page: number): Promise<Pagina<LinhaIdentidade>> {
  const { data } = await iamAdminClient.get<Pagina<LinhaIdentidade>>('/eventos-seguranca/', { params: params(f, page) })
  return data
}
