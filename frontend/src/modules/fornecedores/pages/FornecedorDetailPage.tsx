import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Truck, ArrowLeft, Pencil, Trash2, Plus, CreditCard, Package, Landmark,
} from 'lucide-react'
import { useFornecedor } from '../hooks/useFornecedor'
import FornecedorForm from '../components/FornecedorForm'
import DadoBancarioFornecedorForm from '../components/DadoBancarioFornecedorForm'
import ProdutoServicoForm from '../components/ProdutoServicoForm'
import type {
  FornecedorFormData,
  DadoBancarioFornecedor, DadoBancarioFornecedorFormData,
  ProdutoServicoFornecedor, ProdutoServicoFormData,
} from '@/types'

import { formatCNPJ } from '@/utils/masks'

// ─── helpers ─────────────────────────────────────────────────────────────────

function formatPhone(v: string) {
  const d = v.replace(/\D/g, '')
  if (d.length === 11) return d.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3')
  if (d.length === 10) return d.replace(/(\d{2})(\d{4})(\d{4})/, '($1) $2-$3')
  return v
}

function formatCurrency(v: string) {
  return parseFloat(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const TIPO_CONTA_LABEL: Record<string, string> = {
  corrente: 'Conta Corrente', poupanca: 'Conta Poupança', outro: 'Outro',
}

// ─── sub-componentes ──────────────────────────────────────────────────────────

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

// ─── página principal ─────────────────────────────────────────────────────────

type Tab = 'dados' | 'produtos' | 'bancario'

const FornecedorDetailPage: React.FC = () => {
  const { id }        = useParams<{ id: string }>()
  const navigate      = useNavigate()
  const fornecedorId  = Number(id)

  const {
    data, dadosBancarios, produtos,
    loading, error,
    updateFornecedor, deleteFornecedor,
    createDadoBancario, updateDadoBancario, deleteDadoBancario,
    createProduto, updateProduto, deleteProduto,
  } = useFornecedor(fornecedorId)

  const [activeTab, setActiveTab]         = useState<Tab>('dados')
  const [editOpen, setEditOpen]           = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting]           = useState(false)

  const [bancoForm, setBancoForm] = useState<{ open: boolean; editing: DadoBancarioFornecedor | null }>({ open: false, editing: null })
  const [produtoForm, setProdutoForm] = useState<{ open: boolean; editing: ProdutoServicoFornecedor | null }>({ open: false, editing: null })

  // ── handlers ──────────────────────────────────────────────────────────────

  const handleUpdate = async (formData: FornecedorFormData) => {
    await updateFornecedor(formData)
    setEditOpen(false)
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteFornecedor()
      navigate('/app/fornecedores')
    } finally {
      setDeleting(false)
    }
  }

  const handleSaveBanco = async (formData: DadoBancarioFornecedorFormData) => {
    if (bancoForm.editing) {
      await updateDadoBancario(bancoForm.editing.id, formData)
    } else {
      await createDadoBancario(formData)
    }
    setBancoForm({ open: false, editing: null })
  }

  const handleSaveProduto = async (formData: ProdutoServicoFormData) => {
    if (produtoForm.editing) {
      await updateProduto(produtoForm.editing.id, formData)
    } else {
      await createProduto(formData)
    }
    setProdutoForm({ open: false, editing: null })
  }

  // ── loading / error ────────────────────────────────────────────────────────

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
        <button onClick={() => navigate('/app/fornecedores')} className="flex items-center gap-2 text-sm mb-6"
          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
          <ArrowLeft size={16} /> Voltar
        </button>
        <p style={{ color: '#c53030', fontFamily: 'var(--font-body)' }}>
          {error ?? 'Fornecedor não encontrado.'}
        </p>
      </div>
    )
  }

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'dados',    label: 'Dados Cadastrais', icon: <Truck size={14} /> },
    { id: 'produtos', label: `Produtos / Serviços (${produtos.length})`, icon: <Package size={14} /> },
    { id: 'bancario', label: `Dados Bancários (${dadosBancarios.length})`, icon: <Landmark size={14} /> },
  ]

  return (
    <div className="px-6 py-8 max-w-5xl">

      {/* Volta */}
      <button onClick={() => navigate('/app/fornecedores')}
        className="flex items-center gap-2 text-sm mb-5"
        style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
        <ArrowLeft size={15} /> Fornecedores
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: '#fef3c7', color: 'var(--color-brand)' }}>
            <Truck size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {data.razao_social}
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {data.cnpj ? formatCNPJ(data.cnpj) : 'Sem CPF/CNPJ'}
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

      {/* ── Aba: Dados Cadastrais ──────────────────────────────────────────── */}
      {activeTab === 'dados' && (
        <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <Field label="Razão Social"  value={data.razao_social} />
            <Field label="CNPJ"          value={data.cnpj ? formatCNPJ(data.cnpj) : undefined} />
            <Field label="Contato"       value={data.contato} />
            <Field label="E-mail"        value={data.email} />
            <Field label="Telefone"      value={data.telefone ? formatPhone(data.telefone) : undefined} />
          </div>
        </div>
      )}

      {/* ── Aba: Produtos / Serviços ───────────────────────────────────────── */}
      {activeTab === 'produtos' && (
        <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
          <SectionHeader
            title="Produtos / Serviços"
            onAdd={() => setProdutoForm({ open: true, editing: null })}
            addLabel="Novo item"
          />
          {produtos.length === 0 ? (
            <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              Nenhum produto ou serviço cadastrado.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                    {['Nome', 'Tipo', 'Unidade', 'Preço Unitário', ''].map(h => (
                      <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-4 py-3"
                        style={{ color: 'var(--color-text-muted)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {produtos.map((p, i) => (
                    <tr key={p.id}
                      style={{ borderBottom: i < produtos.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                      <td className="px-4 py-3">
                        <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                          {p.nome_produto_servico}
                        </span>
                        {p.descricao && (
                          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                            {p.descricao}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs px-2 py-1 rounded-full"
                          style={{ background: '#f1f5f9', color: 'var(--color-text-muted)' }}>
                          {p.tipo_produto_servico}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                          {p.unidade_medida}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                          {formatCurrency(p.preco_unitario)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 justify-end">
                          <button onClick={() => setProdutoForm({ open: true, editing: p })}
                            className="p-1.5 rounded" title="Editar"
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => deleteProduto(p.id)}
                            className="p-1.5 rounded" title="Remover"
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Aba: Dados Bancários ───────────────────────────────────────────── */}
      {activeTab === 'bancario' && (
        <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
          <SectionHeader
            title="Dados Bancários"
            onAdd={() => setBancoForm({ open: true, editing: null })}
            addLabel="Adicionar conta"
          />
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
                        {TIPO_CONTA_LABEL[db.tipo_conta] ?? db.tipo_conta} — Banco {db.codigo_banco}
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
                  <Field label="Agência" value={db.agencia_dv ? `${db.agencia}-${db.agencia_dv}` : db.agencia} />
                  <Field label="Conta"   value={db.conta_dv ? `${db.conta}-${db.conta_dv}` : db.conta} />
                  <Field label="Tipo"    value={TIPO_CONTA_LABEL[db.tipo_conta] ?? db.tipo_conta} />
                  <Field label="Chave PIX" value={db.chave_pix} />
                  {db.codigo_cedente && <Field label="Código Cedente" value={db.codigo_cedente} />}
                  {db.carteira && <Field label="Carteira" value={db.carteira} />}
                  {db.observacoes && (
                    <div className="col-span-2 sm:col-span-3">
                      <Field label="Observações" value={db.observacoes} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Confirm delete ────────────────────────────────────────────────── */}
      {confirmDelete && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setConfirmDelete(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-80"
            style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <h3 className="text-base font-bold mb-2" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Excluir fornecedor?
            </h3>
            <p className="text-sm mb-5" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Esta ação é permanente. Produtos, serviços e dados bancários vinculados serão excluídos.
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

      {/* ── Forms ────────────────────────────────────────────────────────── */}
      <FornecedorForm open={editOpen} onClose={() => setEditOpen(false)} onSave={handleUpdate} initial={data} />

      <DadoBancarioFornecedorForm
        open={bancoForm.open}
        fornecedorId={fornecedorId}
        onClose={() => setBancoForm({ open: false, editing: null })}
        onSave={handleSaveBanco}
        initial={bancoForm.editing}
      />

      <ProdutoServicoForm
        open={produtoForm.open}
        fornecedorId={fornecedorId}
        onClose={() => setProdutoForm({ open: false, editing: null })}
        onSave={handleSaveProduto}
        initial={produtoForm.editing}
      />
    </div>
  )
}

export default FornecedorDetailPage
