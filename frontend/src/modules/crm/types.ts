// Tipos do CRM — espelham os models/serializers do backend (`modulocrm`).
//
// O CRM usa **UUID** como PK (BaseModel.id = UUIDField). Os IDs chegam como
// string no JSON. Filtros seguem o padrão DRF (filterset_fields por viewset).

/** Espelha `Lead.StatusChoices` (backend). */
export type StatusLead = 'NOVO' | 'CONTATADO' | 'QUALIFICADO' | 'CONVERTIDO' | 'PERDIDO'

/** Espelha `Opportunity.StageChoices` (backend). */
export type StageOportunidade = 'QUALIFICACAO' | 'PROPOSTA' | 'NEGOCIACAO' | 'GANHO' | 'PERDIDO'

/** Espelha `Interaction.TypeChoices` (backend). */
export type TipoInteracao = 'LIGACAO' | 'EMAIL' | 'REUNIAO' | 'TAREFA' | 'OUTRO'

/** Resumo do usuário (UsuarioSerializer — vem aninhado em assigned_to). */
export interface UsuarioResumo {
  id: number
  username: string
  email: string
  first_name?: string
  last_name?: string
}

// ─── Lead ────────────────────────────────────────────────────────────────────

export interface Lead {
  id: string
  first_name: string
  last_name: string
  email: string
  phone: string
  company: string
  status: StatusLead
  source: string
  assigned_to: UsuarioResumo | null
  assigned_to_id?: number | null
  score: number
  campaign: string | null
  interactions: Interaction[]
  created_at: string
  updated_at: string
  tenant: number
}

export interface LeadPayload {
  first_name: string
  last_name: string
  email: string
  phone?: string
  company?: string
  status?: StatusLead
  source?: string
  assigned_to_id?: number | null
  campaign?: string | null
}

export interface LeadFiltros {
  status?: StatusLead
  source?: string
  campaign?: string
  search?: string
  page?: number
  page_size?: number
}

// ─── Account (Conta/Empresa) ─────────────────────────────────────────────────

export interface Account {
  id: string
  name: string
  email: string
  phone: string
  website: string
  industry: string
  assigned_to: UsuarioResumo | null
  assigned_to_id?: number | null
  cliente_associado: number | null
  contacts: Contact[]
  opportunities: Opportunity[]
  created_at: string
  updated_at: string
  tenant: number
}

export interface AccountPayload {
  name: string
  email?: string
  phone?: string
  website?: string
  industry?: string
  assigned_to_id?: number | null
  cliente_associado?: number | null
}

// ─── Contact (Contato) ───────────────────────────────────────────────────────

export interface Contact {
  id: string
  account: string
  account_id?: string
  first_name: string
  last_name: string
  email: string
  phone: string
  title: string
  cliente_associado: number | null
  opportunities: Opportunity[]
  interactions: Interaction[]
  created_at: string
  updated_at: string
  tenant: number
}

export interface ContactPayload {
  account_id?: string
  first_name: string
  last_name: string
  email: string
  phone?: string
  title?: string
  cliente_associado?: number | null
}

// ─── Opportunity (Oportunidade) ──────────────────────────────────────────────

export interface OpportunityProduct {
  id: string
  opportunity: string
  product: {
    id: number
    nome_produto_servico: string
    unidade_medida: string
    preco_unitario: string
  }
  product_id?: number
  quantity: string
  unit_price: string
  created_at: string
  updated_at: string
  tenant: number
}

export interface OpportunityProductPayload {
  opportunity: string
  product_id: number
  quantity: string
  unit_price: string
}

export interface Opportunity {
  id: string
  name: string
  account: string
  account_id?: string
  contact: string | null
  contact_id?: string | null
  stage: StageOportunidade
  probability: number
  close_date: string
  assigned_to: UsuarioResumo | null
  assigned_to_id?: number | null
  empreendimento: number | null
  interactions: Interaction[]
  products: OpportunityProduct[]
  amount: string
  created_at: string
  updated_at: string
  tenant: number
}

export interface OpportunityPayload {
  name: string
  account_id?: string
  contact_id?: string | null
  stage?: StageOportunidade
  probability?: number
  close_date: string
  assigned_to_id?: number | null
  empreendimento?: number | null
}

export interface OpportunityFiltros {
  search?: string
  page?: number
  page_size?: number
}

// ─── Interaction (Interação/Tarefa) ──────────────────────────────────────────

export interface Interaction {
  id: string
  opportunity: string | null
  contact: string | null
  lead: string | null
  type: TipoInteracao
  subject: string
  notes: string
  due_date: string | null
  completed: boolean
  assigned_to: { type: string; id: number; [k: string]: unknown } | null
  created_at: string
  updated_at: string
  tenant: number
}

export interface InteractionPayload {
  opportunity?: string | null
  contact?: string | null
  lead?: string | null
  type: TipoInteracao
  subject: string
  notes?: string
  due_date?: string | null
  completed?: boolean
}

export interface InteractionFiltros {
  type?: TipoInteracao
  completed?: boolean
  due_date__gte?: string
  due_date__lte?: string
  lead?: string
  opportunity?: string
  contact?: string
  page?: number
  page_size?: number
}

// ─── Resposta paginada ───────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}