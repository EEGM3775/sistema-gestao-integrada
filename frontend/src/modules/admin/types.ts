// Tipos da área de Administração — papéis/personas e o catálogo de permissões.

export interface Permissao {
  id: number
  code: string
  nome: string
}

export interface CatalogoModulo {
  modulo: string
  atribuivel: boolean          // o tenant assina esse módulo? (base/plataforma sempre true)
  permissoes: Permissao[]
}

export interface CatalogoResposta {
  modulos: CatalogoModulo[]
  templates: string[]          // nomes das personas de fábrica
}

export interface Perfil {
  id: number
  tenant: string
  nome: string
  descricao: string | null
  permissoes: number[]         // ids de Permissao
}

export interface PerfilFormData {
  nome: string
  descricao: string
  permissoes: number[]
}

export interface UsuarioAdmin {
  id: string
  username: string
  email: string
  is_tenant_admin: boolean
  segundo_fator_ativo?: boolean
  perfis: number[]          // ids de Perfil atribuídos ao usuário
  modules: string[]         // entitlements efetivos (read-only)
}
