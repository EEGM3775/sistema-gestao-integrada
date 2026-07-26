import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import { useAuth } from '@/hooks/useAuth'
import { apiDecimalToCents } from '@/utils/money'
import { isoLocal } from '@/utils/dates'
import type { AgingFaixa, ErpDashboardData } from '@/modules/erp/types'
import type { ScmDashboard } from '@/modules/scm/types'
import type { SilDashboard } from '@/modules/sil/types'
import type { CalendarFeedEvent } from '@/modules/calendar/types'

/**
 * Camada de dados do hub.
 *
 * **Não existe endpoint "dashboard da home"** — e inventar um número no
 * frontend para simular um seria exatamente o que a régua proíbe
 * (frontend.md §1.6.4). Então o hub **compõe** os agregados que os módulos já
 * calculam no backend, cada chamada condicionada ao entitlement do usuário:
 * quem não assina o SCM não dispara `scm/dashboard/` e simplesmente não vê
 * KPI de compras — não vê um zero, que mentiria.
 *
 * Consequência de desenho: o hub de dois usuários da mesma empresa é
 * legitimamente diferente, porque o acesso deles é diferente.
 */

// ─── Contratos vindos do backend ──────────────────────────────────────────────

export interface QuotaMedidor {
  recurso: string
  rotulo: string
  limite: number | null
  uso: number | null
  ilimitado: boolean
  restante: number | null
  excedido: boolean
  fonte: string
}

export interface PlanoResumo {
  plano: { slug: string; nome: string; preco_mensal: number; publico?: string }
  quotas: QuotaMedidor[]
  proximo_plano: { slug: string; nome: string; preco_mensal: number } | null
}

// ─── Modelos da tela ──────────────────────────────────────────────────────────

/** Um item da fila "requer sua decisão" — sempre com número, unidade e destino. */
export interface Decisao {
  id: string
  titulo: string
  /** O número já formatado **com unidade** (anti-padrão §11). */
  medida: string
  /** A base do número — o que ele conta. */
  detalhe: string
  urgencia: 'alta' | 'media'
  rota: string
  origem: string
}

export interface FatoRecente {
  id: string
  titulo: string
  meta: string
  quando: string
  origem: string
}

export interface Kpi {
  id: string
  label: string
  valor: string
  base?: string
  origem?: string
  rota?: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const somaCentavos = (faixas: AgingFaixa[] | undefined) =>
  (faixas ?? []).reduce((acc, f) => acc + apiDecimalToCents(f.total), 0)

/** Faixas já vencidas — o backend deriva "Atrasado" do vencimento, não o persiste. */
const VENCIDAS = new Set(['1-30 dias Vencido', '31-60 dias', '61-90 dias', '> 90 dias'])

const somaVencido = (faixas: AgingFaixa[] | undefined) =>
  (faixas ?? []).filter((f) => VENCIDAS.has(f.categoria)).reduce((a, f) => a + apiDecimalToCents(f.total), 0)

const somaHoje = (faixas: AgingFaixa[] | undefined) =>
  (faixas ?? []).filter((f) => f.categoria === 'Vence Hoje').reduce((a, f) => a + apiDecimalToCents(f.total), 0)

const brl = (cents: number) =>
  (cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

const plural = (n: number, s: string, p: string) => `${n} ${n === 1 ? s : p}`

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useHomeResumo() {
  const { hasModule, hasPermission } = useAuth()

  // O dashboard do ERP exige `erp.relatorio.view` além do módulo (é relatório
  // financeiro do tenant inteiro). Sem a permissão não chamamos — o 403 velado
  // seria ruído, e o KPI simplesmente não existe para este usuário.
  const podeErp = hasModule('erp_financeiro') && hasPermission('erp.relatorio.view')
  const podeScm = hasModule('scm')
  const podeSil = hasModule('sil')

  const plano = useQuery<PlanoResumo>({
    queryKey: ['home', 'plano'],
    queryFn: async () => (await apiClient.get<PlanoResumo>('plano/')).data,
    staleTime: 5 * 60_000,
  })

  const erp = useQuery<ErpDashboardData>({
    queryKey: ['home', 'erp'],
    queryFn: async () => (await apiClient.get<ErpDashboardData>('erp/dashboard/')).data,
    enabled: podeErp,
    staleTime: 60_000,
  })

  const scm = useQuery<ScmDashboard>({
    queryKey: ['home', 'scm'],
    queryFn: async () => (await apiClient.get<ScmDashboard>('scm/dashboard/')).data,
    enabled: podeScm,
    staleTime: 60_000,
  })

  const sil = useQuery<SilDashboard>({
    queryKey: ['home', 'sil'],
    queryFn: async () => (await apiClient.get<SilDashboard>('sil/dashboard/')).data,
    enabled: podeSil,
    staleTime: 60_000,
  })

  // Agenda: o feed do calendário já é agregado no backend (eventos próprios +
  // diário + feriados + CRM), então a home não precisa juntar nada.
  const janela = useMemo(() => {
    const hoje = new Date()
    const fim = new Date(hoje)
    fim.setDate(fim.getDate() + 7)
    return { inicio: isoLocal(hoje), fim: isoLocal(fim) }
  }, [])

  const agenda = useQuery<CalendarFeedEvent[]>({
    queryKey: ['home', 'agenda', janela.inicio, janela.fim],
    queryFn: async () =>
      (
        await apiClient.get<CalendarFeedEvent[]>('calendar/events/', {
          params: { start: janela.inicio, end: janela.fim },
        })
      ).data,
    staleTime: 5 * 60_000,
  })

  // ── Medidores de plano (uso real, vindo de `/api/plano/`) ───────────────────
  // Memoizado: sem isso o `?? []` devolveria um array novo a cada render e
  // faria os `useMemo` que dependem dele recalcular sempre.
  const quotas = useMemo<QuotaMedidor[]>(() => plano.data?.quotas ?? [], [plano.data])

  // ── KPIs — só o que tem fonte ───────────────────────────────────────────────
  const kpis = useMemo<Kpi[]>(() => {
    const out: Kpi[] = []
    const nomePlano = plano.data?.plano.nome

    const doQuota = (recurso: string, label: string, rota: string) => {
      const q = quotas.find((x) => x.recurso === recurso)
      if (!q || q.uso == null) return
      out.push({
        id: `quota-${recurso}`,
        label,
        valor: String(q.uso),
        base: q.ilimitado ? 'sem limite no plano' : `de ${q.limite} no plano ${nomePlano ?? ''}`.trim(),
        rota,
      })
    }
    doQuota('obras', 'Obras ativas', '/app/obras')
    doQuota('empreendimentos', 'Empreendimentos', '/app/empreendimentos')
    doQuota('clientes', 'Clientes', '/app/clientes')

    if (erp.data) {
      const receber = somaCentavos(erp.data.agingContasAReceber)
      const pagar = somaCentavos(erp.data.agingContasAPagar)
      out.push(
        { id: 'erp-receber', label: 'A receber', valor: brl(receber), base: 'saldo em aberto', origem: 'ERP', rota: '/app/erp/contas-a-receber' },
        { id: 'erp-pagar', label: 'A pagar', valor: brl(pagar), base: 'saldo em aberto', origem: 'ERP', rota: '/app/erp/contas-a-pagar' },
        { id: 'erp-saldo', label: 'Saldo projetado', valor: brl(receber - pagar), base: 'a receber − a pagar', origem: 'ERP', rota: '/app/erp' },
      )
    }

    if (scm.data) {
      out.push({
        id: 'scm-mes',
        label: 'Comprado no mês',
        valor: brl(apiDecimalToCents(scm.data.valorCompradoMes)),
        base: `pedidos de ${scm.data.mesReferencia}`,
        origem: 'SCM',
        rota: '/app/scm',
      })
      if (scm.data.pedidosTransitoCount > 0) {
        out.push({
          id: 'scm-transito',
          label: 'Em trânsito',
          valor: brl(apiDecimalToCents(scm.data.pedidosTransitoValor)),
          base: plural(scm.data.pedidosTransitoCount, 'pedido a caminho', 'pedidos a caminho'),
          origem: 'SCM',
          rota: '/app/scm',
        })
      }
    }

    if (sil.data) {
      out.push({
        id: 'sil-estoque',
        label: 'Valor em estoque',
        valor: brl(apiDecimalToCents(sil.data.valorEstoque)),
        base: `${plural(sil.data.itensEmEstoque, 'item', 'itens')} · custo médio`,
        origem: 'SIL',
        rota: '/app/sil',
      })
    }

    return out
  }, [plano.data, quotas, erp.data, scm.data, sil.data])

  // ── Fila "requer sua decisão" ──────────────────────────────────────────────
  const decisoes = useMemo<Decisao[]>(() => {
    const out: Decisao[] = []
    const add = (d: Decisao) => out.push(d)

    if (erp.data) {
      const recVenc = somaVencido(erp.data.agingContasAReceber)
      const pagVenc = somaVencido(erp.data.agingContasAPagar)
      const recHoje = somaHoje(erp.data.agingContasAReceber)
      const pagHoje = somaHoje(erp.data.agingContasAPagar)
      if (recVenc > 0)
        add({ id: 'erp-rec-venc', titulo: 'Recebimentos vencidos', medida: brl(recVenc), detalhe: 'saldo em aberto após o vencimento — cobrar', urgencia: 'alta', rota: '/app/erp/contas-a-receber', origem: 'ERP' })
      if (pagVenc > 0)
        add({ id: 'erp-pag-venc', titulo: 'Pagamentos vencidos', medida: brl(pagVenc), detalhe: 'contas em atraso — regularizar', urgencia: 'alta', rota: '/app/erp/contas-a-pagar', origem: 'ERP' })
      if (pagHoje > 0)
        add({ id: 'erp-pag-hoje', titulo: 'Vence hoje (a pagar)', medida: brl(pagHoje), detalhe: 'dar baixa ou reprogramar', urgencia: 'alta', rota: '/app/erp/contas-a-pagar', origem: 'ERP' })
      if (recHoje > 0)
        add({ id: 'erp-rec-hoje', titulo: 'Vence hoje (a receber)', medida: brl(recHoje), detalhe: 'conferir a entrada do dia', urgencia: 'media', rota: '/app/erp/contas-a-receber', origem: 'ERP' })
    }

    if (scm.data) {
      const d = scm.data
      if (d.cotacoesVencemHoje > 0)
        add({ id: 'scm-cot-hoje', titulo: 'Cotações no prazo final', medida: plural(d.cotacoesVencemHoje, 'cotação', 'cotações'), detalhe: 'adjudicar antes de perder a proposta', urgencia: 'alta', rota: '/app/scm', origem: 'SCM' })
      if (d.demandasAbertas > 0)
        add({ id: 'scm-demandas', titulo: 'Demandas a cotar', medida: plural(d.demandasAbertas, 'demanda aberta', 'demandas abertas'), detalhe: 'abrir cotação ou comprar direto', urgencia: 'media', rota: '/app/scm', origem: 'SCM' })
      if (d.pedidosRecebidosParcial > 0)
        add({ id: 'scm-parcial', titulo: 'Recebimento parcial pendente', medida: plural(d.pedidosRecebidosParcial, 'pedido', 'pedidos'), detalhe: 'conferir o saldo que falta chegar', urgencia: 'media', rota: '/app/scm', origem: 'SCM' })
    }

    if (sil.data) {
      const d = sil.data
      if (d.requisicoesPendentes > 0)
        add({ id: 'sil-req', titulo: 'Requisições a aprovar', medida: plural(d.requisicoesPendentes, 'requisição', 'requisições'), detalhe: 'a obra está esperando material', urgencia: 'alta', rota: '/app/sil', origem: 'SIL' })
      if (d.abaixoMinimo > 0)
        add({ id: 'sil-minimo', titulo: 'Itens abaixo do mínimo', medida: plural(d.abaixoMinimo, 'item', 'itens'), detalhe: 'repor ou gerar demanda no SCM', urgencia: 'alta', rota: '/app/sil', origem: 'SIL' })
      if (d.epiVencendo > 0)
        add({ id: 'sil-epi', titulo: 'EPI vencendo', medida: plural(d.epiVencendo, 'entrega', 'entregas'), detalhe: 'CA ou troca em até 30 dias — exigência da NR-6', urgencia: 'alta', rota: '/app/sil', origem: 'SIL' })
      if (d.ferramentasAtrasadas > 0)
        add({ id: 'sil-ferr', titulo: 'Ferramentas em atraso', medida: plural(d.ferramentasAtrasadas, 'ferramenta', 'ferramentas'), detalhe: 'devolução vencida — cobrar do responsável', urgencia: 'media', rota: '/app/sil', origem: 'SIL' })
      if (d.recebimentosAConferir > 0)
        add({ id: 'sil-receb', titulo: 'Recebimentos a conferir', medida: plural(d.recebimentosAConferir, 'pedido', 'pedidos'), detalhe: 'dar entrada no estoque', urgencia: 'media', rota: '/app/sil', origem: 'SIL' })
      if (d.lotesVencendo > 0)
        add({ id: 'sil-lotes', titulo: 'Lotes vencendo', medida: plural(d.lotesVencendo, 'lote', 'lotes'), detalhe: 'validade em até 30 dias', urgencia: 'media', rota: '/app/sil', origem: 'SIL' })
      if (d.inventariosAbertos > 0)
        add({ id: 'sil-inv', titulo: 'Inventários abertos', medida: plural(d.inventariosAbertos, 'inventário', 'inventários'), detalhe: 'fechar para destravar o saldo', urgencia: 'media', rota: '/app/sil', origem: 'SIL' })
    }

    // Quota estourada é decisão de verdade: trava cadastro novo (402 no backend).
    for (const q of quotas) {
      if (q.excedido) {
        add({ id: `quota-${q.recurso}`, titulo: `Limite de ${q.rotulo} atingido`, medida: `${q.uso} de ${q.limite}`, detalhe: 'novos cadastros bloqueados até liberar espaço ou subir de plano', urgencia: 'alta', rota: '/app/dashboard', origem: 'Plano' })
      }
    }

    const peso = { alta: 0, media: 1 }
    return out.sort((a, b) => peso[a.urgencia] - peso[b.urgencia])
  }, [erp.data, scm.data, sil.data, quotas])

  // ── Feed de fatos (reais, vindos dos módulos) ──────────────────────────────
  const atividade = useMemo<FatoRecente[]>(() => {
    const out: FatoRecente[] = []
    scm.data?.atividade?.forEach((a, i) =>
      out.push({ id: `scm-${i}`, titulo: a.titulo, meta: a.meta, quando: a.quando, origem: 'SCM' }),
    )
    sil.data?.atividade?.forEach((a, i) =>
      out.push({ id: `sil-${i}`, titulo: a.titulo, meta: a.meta, quando: a.quando, origem: 'SIL' }),
    )
    return out.sort((a, b) => (a.quando < b.quando ? 1 : -1)).slice(0, 12)
  }, [scm.data, sil.data])

  return {
    plano,
    erp,
    scm,
    sil,
    agenda,
    quotas,
    kpis,
    decisoes,
    atividade,
    /** Módulos que de fato alimentam este hub — usado para explicar a procedência. */
    fontes: { erp: podeErp, scm: podeScm, sil: podeSil },
    carregando: plano.isLoading || erp.isLoading || scm.isLoading || sil.isLoading,
  }
}
