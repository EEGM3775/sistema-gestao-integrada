import React, { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Pencil, Trash2, ChevronRight, Building2, Loader2, HardHat, Landmark, LayoutGrid, Receipt, Plus, Crown } from 'lucide-react'
import {
  useEmpreendimento,
  updateEmpreendimento,
  deleteEmpreendimento,
  createContaBancaria,
  updateContaBancaria,
  deleteContaBancaria,
  createCusto,
  updateCusto,
  deleteCusto,
} from '../hooks/useEmpreendimento'
import EmpreendimentoStatusBadge from '../components/EmpreendimentoStatusBadge'
import EmpreendimentoForm from '../components/EmpreendimentoForm'
import ContaBancariaForm from '../components/ContaBancariaForm'
import CustoEmpreendimentoForm from '../components/CustoEmpreendimentoForm'
import UnidadesTab from '../components/UnidadesTab'
import DonoECotas from '@/modules/entidades/components/DonoECotas'
import { useAuth } from '@/hooks/useAuth'
import { useObras } from '@/modules/obras/hooks/useObras'
import ObraStatusBadge from '@/modules/obras/components/ObraStatusBadge'
import type {
  EmpreendimentoFormData,
  ContaBancariaEmpreendimento,
  ContaBancariaEmpreendimentoFormData,
  CustoEmpreendimento,
  CustoEmpreendimentoFormData,
} from '@/types'
import { formatCNPJ } from '@/utils/masks'

type Tab = 'visao' | 'dono' | 'obras' | 'contas' | 'custos' | 'unidades'
const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: 'visao',    label: 'Visão Geral',      icon: <Building2 size={15} /> },
  { key: 'dono',     label: 'Dono e cotas',      icon: <Crown size={15} /> },
  { key: 'obras',    label: 'Obras',             icon: <HardHat size={15} /> },
  { key: 'contas',   label: 'Contas Bancárias',  icon: <Landmark size={15} /> },
  { key: 'custos',   label: 'Custos',            icon: <Receipt size={15} /> },
  { key: 'unidades', label: 'Unidades',          icon: <LayoutGrid size={15} /> },
]

function formatCurrency(value: string | null) {
  if (!value) return '—'
  const n = parseFloat(value)
  if (isNaN(n)) return '—'
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function formatDate(value: string | null) {
  if (!value) return '—'
  const [y, m, d] = value.split('-')
  return `${d}/${m}/${y}`
}

const TIPO_CUSTO_LABEL: Record<string, string> = {
  automovel: 'Automóvel', equipamentos: 'Equipamentos', extra: 'Extra',
  fixo: 'Fixo', funcionarios: 'Funcionários', imovel: 'Imóvel',
  impostos: 'Impostos', imprevisto: 'Imprevisto', manutencao: 'Manutenção',
  materiais: 'Materiais', mobiliario: 'Mobiliário', publicidade: 'Publicidade',
  seguros: 'Seguros', servicos: 'Serviços', servicos_terceiros: 'Serv. Terceiros',
  taxas: 'Taxas', transporte: 'Transporte', variavel: 'Variável', outros: 'Outros',
}

const EmpreendimentoDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const numId = id ? parseInt(id, 10) : null

  const { data, contas, custos, loading, error, refetch } = useEmpreendimento(numId)
  const { hasPermission } = useAuth()
  const { data: obras, loading: obrasLoading } = useObras({ empreendimentoId: numId })

  const [activeTab, setActiveTab]         = useState<Tab>('visao')
  const [editOpen, setEditOpen]           = useState(false)
  const [deleteModalOpen, setDeleteModal] = useState(false)
  const [deleting, setDeleting]           = useState(false)

  // Conta bancária states
  const [contaFormOpen, setContaFormOpen]   = useState(false)
  const [editingConta, setEditingConta]     = useState<ContaBancariaEmpreendimento | null>(null)
  const [deletingContaId, setDeletingContaId] = useState<number | null>(null)

  // Custo states
  const [custoFormOpen, setCustoFormOpen]   = useState(false)
  const [editingCusto, setEditingCusto]     = useState<CustoEmpreendimento | null>(null)
  const [deletingCustoId, setDeletingCustoId] = useState<number | null>(null)

  const handleUpdate = async (formData: EmpreendimentoFormData) => {
    if (!numId) return
    await updateEmpreendimento(numId, formData)
    refetch()
  }

  const handleDelete = async () => {
    if (!numId || !data) return
    setDeleting(true)
    try {
      await deleteEmpreendimento(numId)
      navigate('/app/empreendimentos', { replace: true })
    } catch {
      setDeleting(false)
      setDeleteModal(false)
    }
  }

  // Conta bancária handlers
  const handleSaveConta = async (formData: ContaBancariaEmpreendimentoFormData) => {
    if (editingConta) {
      await updateContaBancaria(editingConta.id, formData)
    } else {
      await createContaBancaria(formData)
    }
    refetch()
  }

  const handleDeleteConta = async (contaId: number) => {
    setDeletingContaId(contaId)
    try {
      await deleteContaBancaria(contaId)
      refetch()
    } finally {
      setDeletingContaId(null)
    }
  }

  // Custo handlers
  const handleSaveCusto = async (formData: CustoEmpreendimentoFormData) => {
    if (editingCusto) {
      await updateCusto(editingCusto.custo_id, formData)
    } else {
      await createCusto(formData)
    }
    refetch()
  }

  const handleDeleteCusto = async (custoId: number) => {
    setDeletingCustoId(custoId)
    try {
      await deleteCusto(custoId)
      refetch()
    } finally {
      setDeletingCustoId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
             style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="px-6 py-8">
        <div className="text-sm px-4 py-3 rounded-lg"
             style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
          {error ?? 'Empreendimento não encontrado.'}
        </div>
      </div>
    )
  }

  const totalCustos = custos.reduce((acc, c) => acc + parseFloat(c.valor_total || '0'), 0)

  return (
    <div className="px-6 py-8 max-w-5xl">

      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-xs mb-6"
           style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
        <Link to="/app/empreendimentos" className="hover:underline" style={{ color: 'var(--color-brand)' }}>
          Empreendimentos
        </Link>
        <ChevronRight size={12} />
        <span>{data.empreendimento}</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
               style={{ background: '#dbeafe', color: 'var(--color-brand)' }}>
            <Building2 size={24} />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold"
                  style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                {data.empreendimento}
              </h1>
              <EmpreendimentoStatusBadge status={data.status_empreendimento} />
            </div>
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {data.razao_social} · {formatCNPJ(data.cnpj)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setEditOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold transition-colors duration-150"
            style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', color: 'var(--color-brand)', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
            <Pencil size={14} /> Editar
          </button>
          <button
            onClick={() => setDeleteModal(true)} disabled={deleting}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid #fed7d7', background: '#fff5f5', color: '#c53030', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: 'Orçamento Total', value: formatCurrency(data.orcamento_total) },
          { label: 'Total em Custos', value: formatCurrency(String(totalCustos)) },
          { label: 'Início Previsto', value: formatDate(data.data_inicio_prevista) },
          { label: 'Fim Previsto',    value: formatDate(data.data_fim_prevista) },
        ].map(kpi => (
          <div key={kpi.label} className="rounded-xl p-4"
               style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}>
            <p className="text-xs font-semibold uppercase tracking-wide mb-1"
               style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {kpi.label}
            </p>
            <p className="text-lg font-bold"
               style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {kpi.value}
            </p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-xl w-fit" style={{ background: '#f1f5f9' }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-150"
            style={{
              fontFamily: 'var(--font-body)', border: 'none', cursor: 'pointer',
              background: activeTab === t.key ? '#FFFFFF' : 'transparent',
              color: activeTab === t.key ? 'var(--color-brand)' : 'var(--color-text-muted)',
              boxShadow: activeTab === t.key ? 'var(--shadow-sm)' : 'none',
            }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}>

        {/* ── Visão Geral ── */}
        {activeTab === 'visao' && (
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
            {[
              // O estoque num relance. `null` = a resposta não trouxe a
              // contagem; nunca mostrar "0 unidades" para o que não foi contado.
              {
                label: 'Unidades',
                value: data.unidades_total == null
                  ? '—'
                  : `${data.unidades_total} cadastrada${data.unidades_total === 1 ? '' : 's'}`
                    + ` · ${data.unidades_disponiveis ?? 0} à venda`
                    + ` · ${data.unidades_vendidas ?? 0} vendida${data.unidades_vendidas === 1 ? '' : 's'}`,
              },
              { label: 'Telefone',    value: data.telefone || '—' },
              { label: 'Endereço',    value: data.endereco || '—' },
              { label: 'Início real', value: formatDate(data.data_inicio_real) },
              { label: 'Fim real',    value: formatDate(data.data_fim_real) },
              { label: 'Cadastro',    value: new Date(data.data_criacao).toLocaleDateString('pt-BR') },
              { label: 'Atualização', value: new Date(data.data_atualizacao).toLocaleDateString('pt-BR') },
            ].map(item => (
              <div key={item.label}>
                <dt className="text-xs font-semibold uppercase tracking-wide mb-0.5"
                    style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  {item.label}
                </dt>
                <dd className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  {item.value}
                </dd>
              </div>
            ))}
            {data.descricao && (
              <div className="md:col-span-2">
                <dt className="text-xs font-semibold uppercase tracking-wide mb-0.5"
                    style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  Descrição
                </dt>
                <dd className="text-sm leading-relaxed"
                    style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  {data.descricao}
                </dd>
              </div>
            )}
          </dl>
        )}

        {/* ── Dono e cotas (docs/modulos/entidades.md) ── */}
        {activeTab === 'dono' && (
          <DonoECotas empreendimentoId={numId!} entidadePropria={data.entidade_propria ?? null}
            podeEditar={hasPermission('obra.empreendimento.edit')} onMudou={refetch} />
        )}

        {/* ── Unidades ── */}
        {activeTab === 'unidades' && (
          <UnidadesTab empreendimentoId={numId!} onMudou={refetch} />
        )}

        {/* ── Obras ── */}
        {activeTab === 'obras' && (
          obrasLoading ? (
            <div className="flex items-center justify-center py-10">
              <div className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin"
                   style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
            </div>
          ) : obras.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <HardHat size={36} style={{ color: '#cbd5e1' }} />
              <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                Nenhuma obra vinculada a este empreendimento.
              </p>
              <Link to="/app/obras" className="text-sm font-semibold"
                    style={{ color: 'var(--color-brand)', textDecoration: 'none', fontFamily: 'var(--font-body)' }}>
                + Gerenciar obras
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                    {['Nome', 'Status', 'Início', 'Fim'].map(h => (
                      <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-4 py-3"
                          style={{ color: 'var(--color-text-muted)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {obras.map((obra, i) => (
                    <tr key={obra.obra_id}
                        onClick={() => navigate(`/app/obras/${obra.obra_id}`)}
                        className="cursor-pointer transition-colors duration-100"
                        style={{ borderBottom: i < obras.length - 1 ? '1px solid #f1f5f9' : 'none' }}
                        onMouseEnter={el => (el.currentTarget.style.background = '#f8fafc')}
                        onMouseLeave={el => (el.currentTarget.style.background = 'transparent')}>
                      <td className="px-4 py-3 text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                        {obra.nome_obra}
                      </td>
                      <td className="px-4 py-3"><ObraStatusBadge status={obra.status_obra} /></td>
                      <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {formatDate(obra.data_inicio_prevista)}
                      </td>
                      <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {formatDate(obra.data_fim_prevista)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {/* ── Contas Bancárias ── */}
        {activeTab === 'contas' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm font-semibold" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {contas.length} conta{contas.length !== 1 ? 's' : ''} cadastrada{contas.length !== 1 ? 's' : ''}
              </p>
              <button
                onClick={() => { setEditingConta(null); setContaFormOpen(true) }}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                <Plus size={14} /> Nova Conta
              </button>
            </div>

            {contas.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <Landmark size={36} style={{ color: '#cbd5e1' }} />
                <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  Nenhuma conta bancária cadastrada.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {contas.map(c => (
                  <div key={c.id} className="rounded-lg p-4"
                       style={{ border: '1px solid #e2e8f0', background: '#f8fafc' }}>
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div className="flex flex-wrap gap-4 flex-1">
                        <div>
                          <p className="text-xs uppercase tracking-wide"
                             style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>Banco</p>
                          <p className="text-sm font-semibold"
                             style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                            {c.codigo_banco}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wide"
                             style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>Agência</p>
                          <p className="text-sm font-semibold"
                             style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                            {c.agencia}{c.agencia_dv ? `-${c.agencia_dv}` : ''}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wide"
                             style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>Conta</p>
                          <p className="text-sm font-semibold"
                             style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                            {c.conta}{c.conta_dv ? `-${c.conta_dv}` : ''}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wide"
                             style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>Tipo</p>
                          <p className="text-sm font-semibold capitalize"
                             style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                            {c.tipo_conta}
                          </p>
                        </div>
                        {c.codigo_pix && (
                          <div>
                            <p className="text-xs uppercase tracking-wide"
                               style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>PIX</p>
                            <p className="text-sm font-semibold"
                               style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                              {c.codigo_pix}
                            </p>
                          </div>
                        )}
                        {c.is_principal === 1 && (
                          <span className="self-center text-xs font-semibold px-2 py-0.5 rounded-full"
                                style={{ background: '#dcfce7', color: '#166534', fontFamily: 'var(--font-body)' }}>
                            Principal
                          </span>
                        )}
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <button
                          onClick={() => { setEditingConta(c); setContaFormOpen(true) }}
                          className="p-1.5 rounded-lg transition-colors"
                          style={{ border: '1px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer', color: 'var(--color-brand)' }}
                          title="Editar">
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDeleteConta(c.id)}
                          disabled={deletingContaId === c.id}
                          className="p-1.5 rounded-lg transition-colors"
                          style={{ border: '1px solid #fed7d7', background: '#fff5f5', cursor: 'pointer', color: '#c53030' }}
                          title="Excluir">
                          {deletingContaId === c.id
                            ? <Loader2 size={13} className="animate-spin" />
                            : <Trash2 size={13} />}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Custos ── */}
        {activeTab === 'custos' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm font-semibold" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {custos.length} custo{custos.length !== 1 ? 's' : ''} registrado{custos.length !== 1 ? 's' : ''}
              </p>
              <button
                onClick={() => { setEditingCusto(null); setCustoFormOpen(true) }}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                <Plus size={14} /> Registrar Custo
              </button>
            </div>

            {custos.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <Receipt size={36} style={{ color: '#cbd5e1' }} />
                <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  Nenhum custo registrado para este empreendimento.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                      {['Data', 'Tipo', 'Descrição', 'Qtd', 'Valor Unit.', 'Total', ''].map(h => (
                        <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-4 py-3"
                            style={{ color: 'var(--color-text-muted)' }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {custos.map((c, i) => (
                      <tr key={c.custo_id}
                          style={{ borderBottom: i < custos.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                          {formatDate(c.data_custo)}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                                style={{ background: '#f1f5f9', color: 'var(--color-text)' }}>
                            {TIPO_CUSTO_LABEL[c.tipo_custo] ?? c.tipo_custo}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text)' }}>
                          {c.descricao ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text)' }}>
                          {parseFloat(c.quantidade).toLocaleString('pt-BR')}
                        </td>
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text)' }}>
                          {formatCurrency(c.valor)}
                        </td>
                        <td className="px-4 py-3 text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                          {formatCurrency(c.valor_total)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            <button
                              onClick={() => { setEditingCusto(c); setCustoFormOpen(true) }}
                              className="p-1.5 rounded-lg transition-colors"
                              style={{ border: '1px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer', color: 'var(--color-brand)' }}
                              title="Editar">
                              <Pencil size={13} />
                            </button>
                            <button
                              onClick={() => handleDeleteCusto(c.custo_id)}
                              disabled={deletingCustoId === c.custo_id}
                              className="p-1.5 rounded-lg transition-colors"
                              style={{ border: '1px solid #fed7d7', background: '#fff5f5', cursor: 'pointer', color: '#c53030' }}
                              title="Excluir">
                              {deletingCustoId === c.custo_id
                                ? <Loader2 size={13} className="animate-spin" />
                                : <Trash2 size={13} />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    <tr style={{ borderTop: '2px solid #e2e8f0', background: '#f8fafc' }}>
                      <td colSpan={5} className="px-4 py-3 text-sm font-semibold text-right"
                          style={{ color: 'var(--color-text-muted)' }}>
                        Total
                      </td>
                      <td className="px-4 py-3 text-sm font-bold" style={{ color: 'var(--color-brand)' }}>
                        {formatCurrency(String(totalCustos))}
                      </td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Formulários ── */}
      <EmpreendimentoForm
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSave={handleUpdate}
        initial={data}
      />

      {numId && (
        <ContaBancariaForm
          open={contaFormOpen}
          empreendimentoId={numId}
          onClose={() => { setContaFormOpen(false); setEditingConta(null) }}
          onSave={handleSaveConta}
          initial={editingConta}
        />
      )}

      {numId && (
        <CustoEmpreendimentoForm
          open={custoFormOpen}
          empreendimentoId={numId}
          onClose={() => { setCustoFormOpen(false); setEditingCusto(null) }}
          onSave={handleSaveCusto}
          initial={editingCusto}
        />
      )}

      {/* Modal de exclusão de empreendimento */}
      {deleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
             style={{ background: 'rgba(0,0,0,0.5)' }}>
          <div className="w-full max-w-md rounded-2xl p-6 flex flex-col gap-5"
               style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-lg)' }}>
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-full flex items-center justify-center shrink-0"
                   style={{ background: '#fee2e2' }}>
                <Trash2 size={20} style={{ color: '#c53030' }} />
              </div>
              <div>
                <h3 className="text-base font-bold mb-1"
                    style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                  Excluir empreendimento?
                </h3>
                <p className="text-sm leading-relaxed"
                   style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  O empreendimento <strong>"{data?.empreendimento}"</strong> será movido para o lixo.
                  Um administrador poderá restaurá-lo posteriormente.
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteModal(false)} disabled={deleting}
                className="flex-1 py-2.5 rounded-lg text-sm font-semibold"
                style={{ border: '1.5px solid #e2e8f0', background: 'transparent',
                  color: 'var(--color-text-muted)', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                Cancelar
              </button>
              <button
                onClick={handleDelete} disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold"
                style={{ background: deleting ? '#fca5a5' : '#dc2626', border: 'none', color: '#FFFFFF',
                  cursor: deleting ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-body)' }}>
                {deleting
                  ? <><Loader2 size={14} className="animate-spin" />Excluindo…</>
                  : <><Trash2 size={14} />Mover para lixo</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default EmpreendimentoDetailPage
