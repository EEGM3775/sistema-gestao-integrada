import type { LucideIcon } from 'lucide-react'
import {
  BarChart3, Brain, Building, Building2, CalendarDays, Calculator, ClipboardList,
  FileText, HardHat, KeyRound, Landmark, LayoutGrid, LifeBuoy, LineChart, Map,
  Package, Plane, Ruler, ShieldCheck, TrendingUp, Truck, UserCog, Users, Warehouse,
  Wrench,
} from 'lucide-react'

/**
 * Catálogo do hub da Edição Construtora.
 *
 * O agrupamento é o **endereço no ciclo** (identidade §4/§9), não "base × pago":
 * cada módulo declara em que estágio do "do terreno à cidade" ele vive. Os
 * módulos futuros aparecem com o **horizonte** (H1/H2/H3) — o hub mostra a casa
 * inteira, incluindo os cômodos ainda não construídos, que é o que a régua
 * chama de "arquitetado para graduar" (frontend.md §1.6.5).
 *
 * **Farol por edição** (§3.2): esta é a lista da Construtora. Módulos exclusivos
 * de outras edições (Loja, Imobiliária) não entram aqui — cada edição tem o seu
 * hub. Nada é escondido por falta de entitlement: o inacessível aparece
 * travado, com o motivo.
 */

export type Estagio = 'originar' | 'construir' | 'negociar' | 'operar' | 'plataforma'

/** Situação de construção — o que existe hoje, sem otimismo. */
export type Situacao =
  | 'pronto' // frontend construído e roteado
  | 'backend' // backend pronto, frontend ainda não
  | 'planejado' // desenhado na expansão, sem backend

export interface ModuloDef {
  id: string
  label: string
  descricao: string
  icon: LucideIcon
  estagio: Estagio
  situacao: Situacao
  /** Código de entitlement. Ausente = módulo base (incluso em todo plano). */
  modulo?: string
  rota?: string
  adminOnly?: boolean
  /** Horizonte da expansão, quando o documento o fixa. */
  horizonte?: 'H1' | 'H2' | 'H3'
}

export const ESTAGIOS: Record<Estagio, { label: string; cor: string; sub: string }> = {
  originar: {
    label: 'Originar',
    cor: 'var(--st-orig)',
    sub: 'Onde o empreendimento nasce — terreno, viabilidade, licença',
  },
  construir: {
    label: 'Construir',
    cor: 'var(--st-const)',
    sub: 'O estágio desta edição — obra, orçamento, suprimentos, campo',
  },
  negociar: {
    label: 'Negociar',
    cor: 'var(--st-neg)',
    sub: 'Da intenção ao contrato — funil, carteira, unidades',
  },
  operar: {
    label: 'Operar',
    cor: 'var(--st-oper)',
    sub: 'Depois da chave — garantia, manutenção, relacionamento',
  },
  plataforma: {
    label: 'Plataforma',
    cor: 'var(--ink-3)',
    sub: 'Transversal: atravessa todos os estágios do ciclo',
  },
}

export const ORDEM_ESTAGIOS: Estagio[] = ['originar', 'construir', 'negociar', 'operar', 'plataforma']

export const CATALOGO: ModuloDef[] = [
  // ── Originar ───────────────────────────────────────────────────────────────
  {
    id: 'empreendimentos',
    label: 'Empreendimentos',
    descricao: 'O empreendimento e sua SPE: cadastro, contas bancárias, custos e as obras que o compõem.',
    icon: Building2,
    estagio: 'originar',
    situacao: 'pronto',
    rota: '/app/empreendimentos',
  },
  {
    // Georreferenciar cadastro é FUNDAÇÃO (sem `modulo`): a página abre para
    // todo tenant e trava só a aba Território, que é o que o entitlement paga.
    // Declarar `modulo: 'maps'` aqui poria cadeado no que está incluso.
    id: 'maps',
    label: 'Mapas & Território',
    descricao: 'Onde cada obra, fornecedor e almoxarifado fica — com precisão declarada. Acervo de voos, plano de voo e rotas com o módulo Maps.',
    icon: Map,
    estagio: 'originar',
    situacao: 'pronto',
    rota: '/app/maps',
  },
  {
    id: 'terrenos',
    label: 'Banco de terrenos',
    descricao: 'Prospecção, dono, zoneamento e status de negociação. Gradua para o marketplace de terrenos.',
    icon: Landmark,
    estagio: 'originar',
    situacao: 'planejado',
  },
  {
    id: 'viabilidade',
    label: 'Estudo de viabilidade',
    descricao: 'VGV, custo estimado, TIR e exposição de caixa por cenário, a partir do banco de terrenos.',
    icon: LineChart,
    estagio: 'originar',
    situacao: 'planejado',
  },

  // ── Construir ──────────────────────────────────────────────────────────────
  {
    id: 'obras',
    label: 'Obras',
    descricao: 'Etapas, cronograma, documentos, equipe e avanço — o centro de gravidade do ciclo.',
    icon: HardHat,
    estagio: 'construir',
    situacao: 'pronto',
    rota: '/app/obras',
  },
  {
    id: 'orcamento',
    label: 'Orçamento de obra',
    descricao: 'Planilha versionada, composições SINAPI/ORSE, BDI do TCU, curva ABC/S e orçado × aplicado.',
    icon: Calculator,
    estagio: 'construir',
    situacao: 'pronto',
    modulo: 'orcamento',
    rota: '/app/orcamento',
  },
  {
    id: 'scm',
    label: 'Suprimentos (SCM)',
    descricao: 'Demanda → cotação → mapa comparativo → pedido → recebimento → avaliação do fornecedor.',
    icon: Package,
    estagio: 'construir',
    situacao: 'pronto',
    modulo: 'scm',
    rota: '/app/scm',
  },
  {
    id: 'sil',
    label: 'Estoque & Logística (SIL)',
    descricao: 'Saldo valorado, requisição da obra, EPI e ferramentaria. Recebimento vira entrada; falta vira demanda.',
    icon: Warehouse,
    estagio: 'construir',
    situacao: 'pronto',
    modulo: 'sil',
    rota: '/app/sil',
  },
  {
    id: 'diario',
    label: 'Diário de Obra + IA',
    descricao: 'Registro diário pelo WhatsApp, com análise automática das fotos do canteiro.',
    icon: Brain,
    estagio: 'construir',
    situacao: 'pronto',
    rota: '/app/diario',
  },
  {
    id: 'fornecedores',
    label: 'Fornecedores',
    descricao: 'Cadastro, produtos e serviços, e o histórico que alimenta a avaliação do SCM.',
    icon: Truck,
    estagio: 'construir',
    situacao: 'pronto',
    rota: '/app/fornecedores',
  },
  {
    id: 'drone',
    label: 'Drone & Mapeamento',
    descricao: 'Levantamento aéreo, ortofoto e modelo 3D por obra, com NodeODM e Potree.',
    icon: Plane,
    estagio: 'construir',
    situacao: 'backend',
    modulo: 'drone',
  },
  {
    id: 'aps',
    label: 'Planejamento (APS)',
    descricao: 'Cronograma físico, linha de balanço e avanço × previsto, com previsão de atraso por IA.',
    icon: Wrench,
    estagio: 'construir',
    situacao: 'planejado',
    modulo: 'aps',
  },
  {
    id: 'pdca',
    label: 'Qualidade / PDCA',
    descricao: 'Checklists de serviço (FVS), não-conformidades, planos de ação e auditoria ISO/PBQP-H.',
    icon: ClipboardList,
    estagio: 'construir',
    situacao: 'planejado',
    modulo: 'pdca',
  },
  {
    id: 'medicoes',
    label: 'Medições & empreiteiros',
    descricao: 'Contratos de empreitada, boletins, retenções e liberação — espelhado com a Edição Empreiteiro.',
    icon: Ruler,
    estagio: 'construir',
    situacao: 'planejado',
    horizonte: 'H2',
  },

  // ── Negociar ───────────────────────────────────────────────────────────────
  {
    id: 'crm',
    label: 'CRM de Vendas',
    descricao: 'Funil de leads, oportunidades e contas — do primeiro contato ao contrato assinado.',
    icon: TrendingUp,
    estagio: 'negociar',
    situacao: 'pronto',
    modulo: 'crm',
    rota: '/app/crm',
  },
  {
    id: 'clientes',
    label: 'Clientes',
    descricao: 'Carteira de compradores, contratos, aquisições e cobranças vinculadas.',
    icon: Users,
    estagio: 'negociar',
    situacao: 'pronto',
    rota: '/app/clientes',
  },
  {
    id: 'espelho',
    label: 'Espelho de vendas',
    descricao: 'Unidades disponível/reservado/vendido, tabela de preços, reserva com prazo e comissões.',
    icon: LayoutGrid,
    estagio: 'negociar',
    situacao: 'planejado',
    horizonte: 'H2',
  },

  // ── Operar ─────────────────────────────────────────────────────────────────
  {
    id: 'assistencia',
    label: 'Assistência técnica',
    descricao: 'Chamados de garantia por unidade e sistema construtivo, SLA e técnico em campo.',
    icon: LifeBuoy,
    estagio: 'operar',
    situacao: 'planejado',
    horizonte: 'H1',
  },
  {
    id: 'portal-cliente',
    label: 'Portal do cliente',
    descricao: 'O comprador acompanha a obra, tira 2ª via e abre chamado — sem passar pelo atendimento.',
    icon: KeyRound,
    estagio: 'operar',
    situacao: 'planejado',
    horizonte: 'H1',
  },
  {
    id: 'condominio',
    label: 'Administração de condomínio',
    descricao: 'Unidades, moradores, taxas (reusa as cobranças), reservas e assembleias.',
    icon: Building,
    estagio: 'operar',
    situacao: 'planejado',
    horizonte: 'H3',
  },

  // ── Plataforma (transversal) ───────────────────────────────────────────────
  {
    id: 'erp',
    label: 'ERP Financeiro',
    descricao: 'Contas a pagar e receber, fluxo de caixa, boletos e NF-e/NFS-e integrados.',
    icon: BarChart3,
    estagio: 'plataforma',
    situacao: 'pronto',
    modulo: 'erp_financeiro',
    rota: '/app/erp',
  },
  {
    id: 'rh',
    label: 'Recursos Humanos',
    descricao: 'Funcionários, cargos, folha e documentos trabalhistas, com PII protegida por permissão.',
    icon: UserCog,
    estagio: 'plataforma',
    situacao: 'pronto',
    modulo: 'rh',
    rota: '/app/rh',
  },
  {
    id: 'calendario',
    label: 'Calendário',
    descricao: 'Agenda única: eventos próprios, diário de obra, feriados e compromissos do CRM.',
    icon: CalendarDays,
    estagio: 'plataforma',
    situacao: 'pronto',
    rota: '/app/calendario',
  },
  {
    id: 'dms',
    label: 'Gestão de Documentos',
    descricao: 'Repositório central com versões e validade — absorve os documentos de obra e de pessoal.',
    icon: FileText,
    estagio: 'plataforma',
    situacao: 'planejado',
    modulo: 'dms',
  },
  {
    id: 'admin-papeis',
    label: 'Papéis e Acessos',
    descricao: 'Personas do tenant e o que cada uma enxerga, por módulo e por ação.',
    icon: ShieldCheck,
    estagio: 'plataforma',
    situacao: 'pronto',
    rota: '/app/admin/papeis',
    adminOnly: true,
  },
  {
    id: 'admin-usuarios',
    label: 'Usuários',
    descricao: 'Quem tem conta na empresa e quais papéis carrega.',
    icon: Users,
    estagio: 'plataforma',
    situacao: 'pronto',
    rota: '/app/admin/usuarios',
    adminOnly: true,
  },
]

/** Por que um módulo não é acessível — o texto vai para o `title` e para o card. */
export type Acesso =
  | { pode: true }
  | { pode: false; motivo: string; contratar?: boolean }

export function acessoDoModulo(
  m: ModuloDef,
  hasModule: (c: string) => boolean,
  isTenantAdmin: boolean,
): Acesso {
  if (m.modulo && !hasModule(m.modulo)) {
    // Não contratado vem antes de "em construção": é a informação acionável
    // (o usuário pode contratar; não pode acelerar o roadmap).
    return { pode: false, motivo: 'Módulo não contratado', contratar: true }
  }
  if (m.adminOnly && !isTenantAdmin) return { pode: false, motivo: 'Somente administradores' }
  if (m.situacao === 'backend') return { pode: false, motivo: 'Backend pronto — tela em construção' }
  if (m.situacao === 'planejado') return { pode: false, motivo: 'Planejado — ver roadmap' }
  if (!m.rota) return { pode: false, motivo: 'Em construção' }
  return { pode: true }
}
