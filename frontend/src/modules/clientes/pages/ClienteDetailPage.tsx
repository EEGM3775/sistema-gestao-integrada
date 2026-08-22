import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Users, ArrowLeft, Pencil, Trash2, Plus, FileText,
  ExternalLink, Building2, CreditCard, Landmark, Wallet, HardHat,
} from 'lucide-react'
import { AbaFinanceiro } from '../carteira/AbaFinanceiro'
import { AbaObra } from '../carteira/AbaObra'
import { useCliente } from '../hooks/useCliente'
import ClienteForm from '../components/ClienteForm'
import AquisicaoForm from '../components/AquisicaoForm'
import ContratoForm from '../components/ContratoForm'
import DadoBancarioForm from '../components/DadoBancarioForm'
import DocumentoUploadForm from '../components/DocumentoUploadForm'
import type {
  ClienteFormData, ClienteEmpreendimento, ClienteEmpreendimentoFormData,
  ContratoCliente, ContratoClienteFormData, StatusContrato, DadoBancarioClienteFormData,
} from '@/types'

import { abrirEmNovaAba } from '@/lib/arquivo'
import { useAuth } from '@/hooks/useAuth'
import { formatCPFCNPJ } from '@/utils/masks'

// ─── helpers ────────────────────────────────────────────────────────────────

function formatDate(v: string | null) {
  if (!v) return '—'
  const [y, m, d] = v.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

function formatCurrency(v: string | null) {
  if (!v) return '—'
  return parseFloat(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const STATUS_CONTRATO_COLORS: Record<StatusContrato, { bg: string; color: string }> = {
  ativo:     { bg: '#dcfce7', color: '#166534' },
  inativo:   { bg: '#f1f5f9', color: '#475569' },
  cancelado: { bg: '#fee2e2', color: '#991b1b' },
  concluido: { bg: '#dbeafe', color: '#1d4ed8' },
}

const STATUS_CONTRATO_LABEL: Record<StatusContrato, string> = {
  ativo: 'Ativo', inativo: 'Inativo', cancelado: 'Cancelado', concluido: 'Concluído',
}

// ─── sub-componentes menores ────────────────────────────────────────────────

const Field: React.FC<{ label: string; value?: string | null }> = ({ label, value }) => (
  <div>
    <p style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--color-text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'var(--font-body)', marginBottom: '2px' }}>
      {label}
    </p>
    <p style={{ fontSize: '0.875rem', color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
      {value || '—'}
    </p>
  </div>
)

const SectionHeader: React.FC<{ title: string; onAdd?: () => void; addLabel?: string }> = ({ title, onAdd, addLabel }) => (
  <div className="flex items-center justify-between mb-4">
    <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--color-brand)' }}>
      {title}
    </h3>
    {onAdd && (
      <button onClick={onAdd}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
        style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
        <Plus size={13} /> {addLabel ?? 'Adicionar'}
      </button>
    )}
  </div>
)

// ─── página principal ────────────────────────────────────────────────────────

type Tab = 'dados' | 'aquisicoes' | 'documentos' | 'bancario' | 'financeiro' | 'obra'

const ClienteDetailPage: React.FC = () => {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const clienteId = Number(id)

  const {
    data, aquisicoes, contratos, documentos, dadosBancarios,
    loading, error,
    updateCliente, deleteCliente,
    createAquisicao, updateAquisicao, deleteAquisicao, gerarParcelas, corrigirParcelas,
    createContrato, updateContrato, deleteContrato,
    uploadDocumento, deleteDocumento,
    createDadoBancario, updateDadoBancario, deleteDadoBancario,
  } = useCliente(clienteId)

  // Vender e emitir o carnê são atos distintos, com permissões distintas: o
  // comercial fecha a venda, o financeiro materializa os títulos. O backend é
  // quem decide (403); aqui a tela só evita oferecer o que vai ser recusado.
  const { hasPermission } = useAuth()
  const podeVender      = hasPermission('cadastro.venda.edit')
  const podeGerarCarne  = hasPermission('cadastro.venda.gerar_carne')

  const [activeTab, setActiveTab]           = useState<Tab>('dados')
  const [editOpen, setEditOpen]             = useState(false)
  const [confirmDelete, setConfirmDelete]   = useState(false)
  const [aquisicaoForm, setAquisicaoForm]   = useState<{ open: boolean; editing: ClienteEmpreendimento | null }>({ open: false, editing: null })
  const [avisoParcelas, setAvisoParcelas]   = useState<string | null>(null)
  const [erroParcelas, setErroParcelas]     = useState<string | null>(null)
  const [previaCorrecao, setPreviaCorrecao] = useState<
    { aquisicaoId: number; dados: import('@/types').RespostaCorrecao } | null
  >(null)
  const [corrigindo, setCorrigindo]         = useState(false)
  const [contratoForm, setContratoForm]     = useState<{ open: boolean; editing: ContratoCliente | null }>({ open: false, editing: null })
  const [bancoForm, setBancoForm]           = useState<{ open: boolean; editing: import('@/types').DadoBancarioCliente | null }>({ open: false, editing: null })
  const [docFormOpen, setDocFormOpen]       = useState(false)
  const [deleting, setDeleting]             = useState(false)

  // ── handlers ────────────────────────────────────────────────────────────────

  const handleUpdate = async (formData: ClienteFormData) => {
    await updateCliente(formData)
    setEditOpen(false)
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteCliente()
      navigate('/app/clientes')
    } finally {
      setDeleting(false)
    }
  }

  const handleSaveAquisicao = async (formData: ClienteEmpreendimentoFormData) => {
    if (aquisicaoForm.editing) {
      await updateAquisicao(aquisicaoForm.editing.cliente_empreendimento_id, formData)
    } else {
      await createAquisicao(formData)
    }
    setAquisicaoForm({ open: false, editing: null })
  }

  const handleSaveContrato = async (formData: ContratoClienteFormData) => {
    if (contratoForm.editing) {
      await updateContrato(contratoForm.editing.contrato_cliente_id, formData)
    } else {
      await createContrato(formData)
    }
    setContratoForm({ open: false, editing: null })
  }

  const handleSaveBanco = async (formData: DadoBancarioClienteFormData) => {
    if (bancoForm.editing) {
      await updateDadoBancario(bancoForm.editing.id, formData)
    } else {
      await createDadoBancario(formData)
    }
  }

  const handleUploadDoc = async (fd: FormData) => {
    await uploadDocumento(fd)
  }

  // ── estados de carregamento ──────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-8 h-8 rounded-full border-2 animate-spin"
          style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="px-6 py-8">
        <button onClick={() => navigate('/app/clientes')} className="flex items-center gap-2 text-sm mb-6"
          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
          <ArrowLeft size={16} /> Voltar
        </button>
        <p style={{ color: '#c53030', fontFamily: 'var(--font-body)' }}>
          {error ?? 'Cliente não encontrado.'}
        </p>
      </div>
    )
  }

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'dados',      label: 'Ficha', icon: <Users size={14} /> },
    { id: 'aquisicoes', label: `Aquisições (${aquisicoes.length + contratos.length})`, icon: <Building2 size={14} /> },
    { id: 'documentos', label: `Documentos (${documentos.length})`, icon: <FileText size={14} /> },
    { id: 'bancario',   label: `Dados bancários (${dadosBancarios.length})`, icon: <Landmark size={14} /> },
    { id: 'financeiro', label: 'Financeiro', icon: <Wallet size={14} /> },
    { id: 'obra',       label: 'Obra', icon: <HardHat size={14} /> },
  ]

  return (
    <div className="px-6 py-8 max-w-5xl">

      {/* Volta */}
      <button onClick={() => navigate('/app/clientes')}
        className="flex items-center gap-2 text-sm mb-5"
        style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
        <ArrowLeft size={15} /> Clientes
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
            <Users size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {data.nome_completo}
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {formatCPFCNPJ(data.cpf_cnpj)} · Cadastrado em {formatDate(data.data_cadastro)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setEditOpen(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer',
              color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
            <Pencil size={14} /> Editar
          </button>
          <button onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid #fee2e2', background: '#fff5f5', cursor: 'pointer',
              color: '#dc2626', fontFamily: 'var(--font-body)' }}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b" style={{ borderColor: '#e2e8f0' }}>
        {TABS.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors duration-150"
            style={{
              fontFamily: 'var(--font-body)', border: 'none', cursor: 'pointer',
              background: 'none', borderBottom: '2px solid',
              borderBottomColor: activeTab === tab.id ? 'var(--color-brand)' : 'transparent',
              color: activeTab === tab.id ? 'var(--color-brand)' : 'var(--color-text-muted)',
              marginBottom: '-1px',
            }}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* ── Aba: Dados Cadastrais ─────────────────────────────────────────────── */}
      {activeTab === 'dados' && (
        <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <Field label="Nome completo"     value={data.nome_completo} />
            <Field label="CPF / CNPJ"        value={formatCPFCNPJ(data.cpf_cnpj)} />
            <Field label="Data de nascimento" value={formatDate(data.data_nascimento)} />
            <Field label="Estado civil"       value={data.estado_civil ?? undefined} />
            <Field label="Profissão"          value={data.profissao ?? undefined} />
            <div />
            <Field label="E-mail" value={data.email} />
            <Field label="Telefone" value={data.telefone || undefined} />
            <div />
            <Field label="Logradouro"
              value={[data.endereco, data.numero_endereco, data.complemento_endereco].filter(Boolean).join(', ') || undefined} />
            <Field label="Bairro" value={data.bairro || undefined} />
            <Field label="Cidade / UF"
              value={data.cidade && data.estado ? `${data.cidade} — ${data.estado}` : data.cidade || data.estado || undefined} />
            <Field label="CEP" value={data.cep || undefined} />
          </div>
        </div>
      )}

      {/* ── Aba: Aquisições / Contratos ───────────────────────────────────────── */}
      {activeTab === 'aquisicoes' && (
        <div className="flex flex-col gap-6">

          {/* Aquisições */}
          <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
            <SectionHeader title="Aquisições" addLabel="Nova aquisição"
              onAdd={podeVender ? () => setAquisicaoForm({ open: true, editing: null }) : undefined} />
            {avisoParcelas && (
              <p className="text-xs mb-2" style={{ color: '#166534', fontFamily: 'var(--font-body)' }}>{avisoParcelas}</p>
            )}
            {erroParcelas && (
              <p className="text-xs mb-2" style={{ color: '#b91c1c', fontFamily: 'var(--font-body)' }}>{erroParcelas}</p>
            )}
            {aquisicoes.length === 0 ? (
              <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                Nenhuma aquisição registrada.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {aquisicoes.map(a => (
                  <div key={a.cliente_empreendimento_id}
                    className="flex items-start justify-between p-4 rounded-lg"
                    style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                        {a.empreendimento_nome} — {a.rotulo_unidade}
                      </span>
                      <span className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                        {formatDate(a.data_compra)} · {formatCurrency(a.valor_compra)} · {CONDICAO_LABEL[a.condicoes_pagamento]}
                      </span>
                      {/* O plano em uma linha: o que se paga, e como. */}
                      {Number(a.valor_total_plano) > 0 && (
                        <span className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                          Plano: {formatCurrency(a.entrada_valor)} de entrada
                          {a.num_parcelas > 0 && ` + ${a.num_parcelas}x ${a.sistema_amortizacao === 'sac' ? 'SAC' : 'Price'}`}
                          {Number(a.juros_mensal) > 0 ? ` a ${a.juros_mensal}% a.m.` : ' sem juros'}
                          {a.balao_quantidade > 0 && ` + ${a.balao_quantidade} balão(ões)`}
                          {' · total '}{formatCurrency(a.valor_total_plano)}
                        </span>
                      )}
                      {/* A correção é do contrato, não do boleto: o rótulo diz a
                          âncora para o vendedor não procurá-la na emissão. */}
                      {a.indice_correcao_codigo && (
                        <span className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                          Correção {a.indice_correcao_nome ?? a.indice_correcao_codigo.toUpperCase()}
                          {a.periodicidade_correcao === 'mensal' ? ' mensal' : ' anual'}
                          {' · data-base '}{formatDate((a.data_base_correcao ?? a.data_compra).slice(0, 10))}
                        </span>
                      )}
                      {a.parcelas_geradas_em ? (
                        <span className="text-xs" style={{ color: '#166534', fontFamily: 'var(--font-body)' }}>
                          Parcelas geradas em {formatDate(a.parcelas_geradas_em.slice(0, 10))} — veja na aba Financeiro
                        </span>
                      ) : podeGerarCarne && (
                        <button
                          onClick={async () => {
                            setErroParcelas(null)
                            try {
                              const r = await gerarParcelas(a.cliente_empreendimento_id)
                              setAvisoParcelas(
                                `${r.geradas} parcelas geradas para ${a.rotulo_unidade} — ${formatCurrency(r.total)}.`
                                + ' Elas estão na aba Financeiro deste cliente. Boletos são emitidos à parte, no ERP.',
                              )
                            } catch {
                              setErroParcelas('Não foi possível gerar as parcelas desta aquisição.')
                            }
                          }}
                          className="text-xs font-semibold text-left"
                          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                            color: 'var(--color-brand)', fontFamily: 'var(--font-body)', width: 'fit-content' }}>
                          Gerar parcelas no financeiro →
                        </button>
                      )}

                      {/* Reajustar só existe depois que há carnê e índice: sem
                          título em aberto não há o que corrigir. */}
                      {podeGerarCarne && a.parcelas_geradas_em && a.indice_correcao_codigo && (
                        <button
                          onClick={async () => {
                            setErroParcelas(null)
                            setCorrigindo(true)
                            try {
                              const dados = await corrigirParcelas(a.cliente_empreendimento_id, false)
                              setPreviaCorrecao({ aquisicaoId: a.cliente_empreendimento_id, dados })
                            } catch {
                              setErroParcelas('Não foi possível calcular o reajuste desta aquisição.')
                            } finally {
                              setCorrigindo(false)
                            }
                          }}
                          disabled={corrigindo}
                          className="text-xs font-semibold text-left"
                          style={{ background: 'none', border: 'none', padding: 0,
                            cursor: corrigindo ? 'wait' : 'pointer',
                            color: 'var(--color-brand)', fontFamily: 'var(--font-body)', width: 'fit-content' }}>
                          {corrigindo ? 'Calculando…' : 'Ver reajuste das parcelas em aberto →'}
                        </button>
                      )}
                    </div>
                    {podeVender && (
                      <div className="flex items-center gap-1 shrink-0">
                        <button onClick={() => setAquisicaoForm({ open: true, editing: a })}
                          className="p-1.5 rounded" title="Editar"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => deleteAquisicao(a.cliente_empreendimento_id)}
                          className="p-1.5 rounded" title="Remover"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Contratos */}
          <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
            <SectionHeader title="Contratos" onAdd={() => setContratoForm({ open: true, editing: null })} addLabel="Novo contrato" />
            {contratos.length === 0 ? (
              <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                Nenhum contrato registrado.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {contratos.map(c => {
                  const sc = STATUS_CONTRATO_COLORS[c.status_contrato]
                  return (
                    <div key={c.contrato_cliente_id}
                      className="flex items-start justify-between p-4 rounded-lg"
                      style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                            Contrato {c.numero_contrato}
                          </span>
                          <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                            style={{ background: sc.bg, color: sc.color, fontFamily: 'var(--font-body)' }}>
                            {STATUS_CONTRATO_LABEL[c.status_contrato]}
                          </span>
                        </div>
                        <span className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                          {c.empreendimento_nome} · Assinado em {formatDate(c.data_assinatura)}
                        </span>
                        <span className="text-xs" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                          {c.objeto_contrato}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {c.arquivo_contrato && (
                          <a href={c.arquivo_contrato} target="_blank" rel="noreferrer"
                            className="p-1.5 rounded" title="Abrir arquivo"
                            style={{ color: 'var(--color-brand)' }}>
                            <ExternalLink size={14} />
                          </a>
                        )}
                        <button onClick={() => setContratoForm({ open: true, editing: c })}
                          className="p-1.5 rounded" title="Editar"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => deleteContrato(c.contrato_cliente_id)}
                          className="p-1.5 rounded" title="Remover"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Aba: Documentos ──────────────────────────────────────────────────── */}
      {activeTab === 'documentos' && (
        <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
          <div className="flex items-center justify-between mb-4">
            <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--color-brand)' }}>
              Documentos
            </h3>
            <button onClick={() => setDocFormOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
              <Plus size={13} /> Anexar documento
            </button>
          </div>
          {documentos.length === 0 ? (
            <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              Nenhum documento anexado.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {documentos.map(doc => (
                <div key={doc.documento_cliente_id}
                  className="flex items-center justify-between p-4 rounded-lg"
                  style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                  <div className="flex items-center gap-3">
                    <FileText size={18} style={{ color: 'var(--color-brand)', flexShrink: 0 }} />
                    <div>
                      <p className="text-sm font-medium" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                        {doc.nome_documento}
                      </p>
                      <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                        {doc.tipo_documento_display} · {formatDate(doc.data_upload)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {/* D70 — documento do titular sai pela porta única, com token. */}
                    <button onClick={() => abrirEmNovaAba(doc.arquivo)}
                      className="p-1.5 rounded" title="Abrir"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-brand)' }}>
                      <ExternalLink size={14} />
                    </button>
                    <button onClick={() => deleteDocumento(doc.documento_cliente_id)}
                      className="p-1.5 rounded" title="Remover"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Aba: Dados Bancários ──────────────────────────────────────────────── */}
      {activeTab === 'bancario' && (
        <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
          <SectionHeader title="Dados Bancários" onAdd={() => setBancoForm({ open: true, editing: null })} addLabel="Adicionar conta" />
          {dadosBancarios.length === 0 ? (
            <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              Nenhum dado bancário cadastrado.
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              {dadosBancarios.map(db => (
                <div key={db.id}
                  className="p-4 rounded-lg grid grid-cols-2 sm:grid-cols-3 gap-4 relative"
                  style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                  <div className="col-span-2 sm:col-span-3 flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <CreditCard size={16} style={{ color: 'var(--color-brand)' }} />
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                        {db.titular_nome}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button onClick={() => setBancoForm({ open: true, editing: db })}
                        className="p-1.5 rounded" title="Editar"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => deleteDadoBancario(db.id)}
                        className="p-1.5 rounded" title="Remover"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <Field label="Banco" value={db.codigo_banco} />
                  <Field label="Agência" value={db.agencia_dv ? `${db.agencia}-${db.agencia_dv}` : db.agencia} />
                  <Field label="Conta" value={db.conta_dv ? `${db.conta}-${db.conta_dv}` : db.conta} />
                  <Field label="Tipo" value={TIPO_CONTA_LABEL[db.tipo_conta] ?? db.tipo_conta} />
                  <Field label="Chave PIX" value={db.chave_pix ?? undefined} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Aba: Financeiro — o histórico de pagamento e os boletos ─────────── */}
      {activeTab === 'financeiro' && <AbaFinanceiro clienteId={clienteId} />}

      {/* ── Aba: Obra — o que ele comprou está sendo construído ─────────────── */}
      {activeTab === 'obra' && <AbaObra clienteId={clienteId} />}

      {/* ── Confirm delete ──────────────────────────────────────────────────── */}
      {/* Prévia do reajuste — a conta antes de aplicar. Reajuste mexe em valor
          já prometido ao comprador; ver depois de gravado é tarde. */}
      {previaCorrecao && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setPreviaCorrecao(null)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 flex flex-col"
            style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', width: 'min(680px, 92vw)', maxHeight: '82vh' }}>
            <h3 className="text-base font-bold mb-1" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Reajuste — {previaCorrecao.dados.indice.toUpperCase()}
              {previaCorrecao.dados.periodicidade === 'mensal' ? ' mensal' : ' anual'}
            </h3>
            <p className="text-xs mb-3" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Data-base {formatDate(previaCorrecao.dados.dataBase)} · cada parcela é trazida até o
              próprio vencimento. Só entram as parcelas em aberto.
            </p>
            {previaCorrecao.dados.parcelas.some(p => p.mesesFaltandoNaSerie > 0) && (
              <p className="text-xs mb-3 p-2 rounded" style={{ background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e' }}>
                A série do índice não cobre todos os meses do período. O reajuste abaixo é o que
                está publicado — carregue as competências que faltam antes de aplicar.
              </p>
            )}
            <div style={{ overflowY: 'auto', flex: 1 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
                <thead>
                  <tr style={{ color: 'var(--color-text-muted)', textAlign: 'left' }}>
                    <th style={{ padding: '4px 6px' }}>Parcela</th>
                    <th style={{ padding: '4px 6px' }}>Vencimento</th>
                    <th style={{ padding: '4px 6px', textAlign: 'right' }}>Nominal</th>
                    <th style={{ padding: '4px 6px', textAlign: 'right' }}>Corrigida</th>
                    <th style={{ padding: '4px 6px', textAlign: 'right' }}>Acréscimo</th>
                  </tr>
                </thead>
                <tbody>
                  {previaCorrecao.dados.parcelas.map(p => (
                    <tr key={p.contaReceberId} style={{ borderTop: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '4px 6px' }}>{p.descricao}</td>
                      <td style={{ padding: '4px 6px' }}>{formatDate(p.vencimento)}</td>
                      <td style={{ padding: '4px 6px', textAlign: 'right' }}>{formatCurrency(p.valorOriginal)}</td>
                      <td style={{ padding: '4px 6px', textAlign: 'right', fontWeight: 600 }}>{formatCurrency(p.valorCorrigido)}</td>
                      <td style={{ padding: '4px 6px', textAlign: 'right', color: Number(p.acrescimo) > 0 ? '#166534' : 'var(--color-text-muted)' }}>
                        {Number(p.acrescimo) === 0 ? '—' : formatCurrency(p.acrescimo)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-3 mt-4">
              <button onClick={() => setPreviaCorrecao(null)}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ border: '1.5px solid #e2e8f0', background: 'none', cursor: 'pointer',
                  color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                Fechar
              </button>
              <button
                disabled={corrigindo || previaCorrecao.dados.parcelas.every(p => Number(p.acrescimo) === 0)}
                onClick={async () => {
                  setCorrigindo(true)
                  try {
                    const r = await corrigirParcelas(previaCorrecao.aquisicaoId, true)
                    setAvisoParcelas(`${r.alteradas ?? 0} parcela(s) reajustada(s) pelo ${r.indice.toUpperCase()}.`)
                    setPreviaCorrecao(null)
                  } catch {
                    setErroParcelas('Não foi possível aplicar o reajuste.')
                  } finally {
                    setCorrigindo(false)
                  }
                }}
                className="px-5 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
                  cursor: corrigindo ? 'wait' : 'pointer', fontFamily: 'var(--font-body)' }}>
                {corrigindo ? 'Aplicando…' : 'Aplicar reajuste'}
              </button>
            </div>
          </div>
        </>
      )}

      {confirmDelete && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setConfirmDelete(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-80"
            style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <h3 className="text-base font-bold mb-2" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Excluir cliente?
            </h3>
            <p className="text-sm mb-5" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Esta ação é permanente. Contratos e aquisições vinculados serão afetados.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDelete(false)}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ border: '1.5px solid #e2e8f0', background: 'none', cursor: 'pointer',
                  color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                Cancelar
              </button>
              <button onClick={handleDelete} disabled={deleting}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: '#dc2626', color: '#FFFFFF', border: 'none',
                  cursor: deleting ? 'not-allowed' : 'pointer', opacity: deleting ? 0.7 : 1,
                  fontFamily: 'var(--font-body)' }}>
                {deleting ? 'Excluindo…' : 'Sim, excluir'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Forms ──────────────────────────────────────────────────────────── */}
      <ClienteForm open={editOpen} onClose={() => setEditOpen(false)} onSave={handleUpdate} initial={data} />

      <AquisicaoForm
        open={aquisicaoForm.open}
        clienteId={clienteId}
        onClose={() => setAquisicaoForm({ open: false, editing: null })}
        onSave={handleSaveAquisicao}
        initial={aquisicaoForm.editing}
      />

      <ContratoForm
        open={contratoForm.open}
        clienteId={clienteId}
        aquisicoes={aquisicoes}
        onClose={() => setContratoForm({ open: false, editing: null })}
        onSave={handleSaveContrato}
        initial={contratoForm.editing}
      />

      <DadoBancarioForm
        open={bancoForm.open}
        clienteId={clienteId}
        onClose={() => setBancoForm({ open: false, editing: null })}
        onSave={handleSaveBanco}
        initial={bancoForm.editing}
      />

      <DocumentoUploadForm
        open={docFormOpen}
        clienteId={clienteId}
        onClose={() => setDocFormOpen(false)}
        onSave={handleUploadDoc}
      />
    </div>
  )
}

// ─── lookup tables locais ─────────────────────────────────────────────────────

const CONDICAO_LABEL: Record<string, string> = {
  a_vista: 'À Vista',
  financiamento_bancario: 'Financiamento Bancário',
  financiamento_direto: 'Financiamento Direto',
  permuta: 'Permuta',
  cartao: 'Cartão',
  outro: 'Outro',
}

const TIPO_CONTA_LABEL: Record<string, string> = {
  corrente: 'Corrente', poupanca: 'Poupança', investimento: 'Investimento',
  salario: 'Salário', outros: 'Outros',
}

export default ClienteDetailPage
