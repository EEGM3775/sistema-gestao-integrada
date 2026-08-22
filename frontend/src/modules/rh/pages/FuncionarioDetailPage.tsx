import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  UserCog, ArrowLeft, Pencil, Trash2, Plus, FileText,
  ExternalLink, CreditCard, ShieldAlert, Lock,
} from 'lucide-react'
import { useFuncionario } from '../hooks/useFuncionario'
import { useCargos } from '../hooks/useCargos'
import FuncionarioForm from '../components/FuncionarioForm'
import DadoMedicoForm from '../components/DadoMedicoForm'
import ASOForm from '../components/ASOForm'
import DadoBancarioRHForm from '../components/DadoBancarioRHForm'
import PagamentoForm from '../components/PagamentoForm'
import FolhaPagamentoForm from '../components/FolhaPagamentoForm'
import type {
  FuncionarioFormData, StatusContratoFuncionario,
  DadoMedicoFormData, ASOFuncionario, ASOFuncionarioFormData,
  DadoBancarioFuncionario, DadoBancarioFuncionarioFormData,
  PagamentoFuncionario, PagamentoFormData, FolhaPagamento, FolhaPagamentoFormData,
} from '@/types'

import { abrirEmNovaAba } from '@/lib/arquivo'
import { formatCPF, formatPISPASEP } from '@/utils/masks'

// ─── helpers ──────────────────────────────────────────────────────────────────

function formatDate(v: string | null) {
  if (!v) return '—'
  const [y, m, d] = v.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

function formatCurrency(v: string | null) {
  if (!v) return '—'
  return parseFloat(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function formatPhone(v: string | null) {
  if (!v) return undefined
  const d = v.replace(/\D/g, '')
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
  return v
}

function formatMes(v: string | null) {
  if (!v) return '—'
  const d = new Date(v + 'T00:00:00')
  return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
}

const STATUS_LABEL: Record<StatusContratoFuncionario, string> = {
  ativo: 'Ativo', inativo: 'Inativo', ferias: 'Férias', licenca: 'Licença', desligado: 'Desligado',
}
const STATUS_COLORS: Record<StatusContratoFuncionario, { bg: string; color: string }> = {
  ativo:     { bg: '#dcfce7', color: '#166534' },
  ferias:    { bg: '#dbeafe', color: '#1d4ed8' },
  licenca:   { bg: '#fef9c3', color: '#854d0e' },
  inativo:   { bg: '#f1f5f9', color: '#475569' },
  desligado: { bg: '#fee2e2', color: '#991b1b' },
}

const TIPO_CONTA_LABEL: Record<string, string> = {
  corrente: 'Corrente', poupanca: 'Poupança', salario: 'Salário',
  investimento: 'Investimento', conta_conjunta: 'Conjunta',
  conta_empresarial: 'Empresarial', outro: 'Outro',
}

const FORMA_PAG_LABEL: Record<string, string> = {
  pix: 'PIX', transferencia: 'Transferência', deposito: 'Depósito', boleto: 'Boleto',
  dinheiro: 'Dinheiro', cheque: 'Cheque', cartao_credito: 'Cartão Crédito',
  cartao_debito: 'Cartão Débito', outro: 'Outro',
}

const TIPO_ASO_LABEL: Record<string, string> = {
  admissional: 'Admissional', periodico: 'Periódico', demissional: 'Demissional',
}
const ASO_STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  ativo:     { bg: '#dcfce7', color: '#166534' },
  pendente:  { bg: '#fef9c3', color: '#854d0e' },
  inativo:   { bg: '#f1f5f9', color: '#475569' },
  cancelado: { bg: '#fee2e2', color: '#991b1b' },
}
const ASO_STATUS_LABEL: Record<string, string> = {
  ativo: 'Ativo', pendente: 'Pendente', inativo: 'Inativo', cancelado: 'Cancelado',
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

const AccessDenied: React.FC<{ role: string }> = ({ role }) => (
  <div className="flex flex-col items-center justify-center py-12 gap-3">
    <Lock size={32} style={{ color: '#94a3b8' }} />
    <p className="text-sm font-semibold" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
      Acesso restrito ao papel <code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>{role}</code>
    </p>
  </div>
)

// ─── página ───────────────────────────────────────────────────────────────────

type Tab = 'dados' | 'documentos' | 'saude' | 'financeiro'

const FuncionarioDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const funcionarioId = Number(id)
  const { cargos } = useCargos()

  const {
    data, dadoMedico, asos, documentos, dadosBancarios, pagamentos, folhas,
    loading, error, acessoMedicoNegado, acessoFinanceiroNegado,
    updateFuncionario, deleteFuncionario,
    uploadDocumento, deleteDocumento,
    saveDadoMedico,
    createASO, updateASO, deleteASO,
    createDadoBancario, updateDadoBancario, deleteDadoBancario,
    createPagamento, updatePagamento, deletePagamento,
    createFolha, updateFolha, deleteFolha,
  } = useFuncionario(funcionarioId)

  const [activeTab, setActiveTab]           = useState<Tab>('dados')
  const [editOpen, setEditOpen]             = useState(false)
  const [confirmDelete, setConfirmDelete]   = useState(false)
  const [deleting, setDeleting]             = useState(false)
  const [medicoOpen, setMedicoOpen]         = useState(false)
  const [asoForm, setAsoForm]               = useState<{ open: boolean; editing: ASOFuncionario | null }>({ open: false, editing: null })
  const [docFormOpen, setDocFormOpen]       = useState(false)
  const [bancoForm, setBancoForm]           = useState<{ open: boolean; editing: DadoBancarioFuncionario | null }>({ open: false, editing: null })
  const [pagForm, setPagForm]               = useState<{ open: boolean; editing: PagamentoFuncionario | null }>({ open: false, editing: null })
  const [folhaForm, setFolhaForm]           = useState<{ open: boolean; editing: FolhaPagamento | null }>({ open: false, editing: null })

  // upload state
  const [docFile, setDocFile]               = useState<File | null>(null)
  const [docTipo, setDocTipo]               = useState('')
  const [docNome, setDocNome]               = useState('')
  const [uploading, setUploading]           = useState(false)
  const fileInputRef                        = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!docFormOpen) { setDocFile(null); setDocTipo(''); setDocNome('') }
  }, [docFormOpen])

  const cargoNome = data?.cargo
    ? (cargos.find(c => c.cargo_id === data.cargo)?.nome_cargo ?? `#${data.cargo}`)
    : '—'

  const handleUpdate = async (fd: FuncionarioFormData) => {
    await updateFuncionario(fd)
    setEditOpen(false)
  }

  const handleDelete = async () => {
    setDeleting(true)
    try { await deleteFuncionario(); navigate('/app/rh') }
    finally { setDeleting(false) }
  }

  const handleUpload = async () => {
    if (!docFile || !docTipo || !docNome) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('arquivo', docFile)
      fd.append('tipo_documento', docTipo)
      fd.append('nome_documento', docNome)
      await uploadDocumento(fd)
      setDocFormOpen(false)
    } finally { setUploading(false) }
  }

  const handleSaveMedico = async (fd: DadoMedicoFormData) => {
    await saveDadoMedico(fd)
    setMedicoOpen(false)
  }

  const handleSaveASO = async (fd: ASOFuncionarioFormData, arquivo: File | null) => {
    if (asoForm.editing) await updateASO(asoForm.editing.aso_id, fd, arquivo)
    else await createASO(fd, arquivo)
    setAsoForm({ open: false, editing: null })
  }

  const handleSaveBanco = async (fd: DadoBancarioFuncionarioFormData) => {
    if (bancoForm.editing) await updateDadoBancario(bancoForm.editing.id, fd)
    else await createDadoBancario(fd)
    setBancoForm({ open: false, editing: null })
  }

  const handleSavePag = async (fd: PagamentoFormData) => {
    if (pagForm.editing) await updatePagamento(pagForm.editing.id, fd)
    else await createPagamento(fd)
    setPagForm({ open: false, editing: null })
  }

  const handleSaveFolha = async (fd: FolhaPagamentoFormData, holerite: File | null) => {
    if (folhaForm.editing) await updateFolha(folhaForm.editing.folha_id, fd, holerite)
    else await createFolha(fd, holerite)
    setFolhaForm({ open: false, editing: null })
  }

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
        <button onClick={() => navigate('/app/rh')} className="flex items-center gap-2 text-sm mb-6"
          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
          <ArrowLeft size={16} /> Funcionários
        </button>
        <p style={{ color: '#c53030', fontFamily: 'var(--font-body)' }}>{error ?? 'Funcionário não encontrado.'}</p>
      </div>
    )
  }

  const sc = STATUS_COLORS[data.status_contrato]

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'dados',      label: 'Dados Pessoais',                  icon: <UserCog size={14} /> },
    { id: 'documentos', label: `Documentos (${documentos.length})`, icon: <FileText size={14} /> },
    { id: 'saude',      label: 'Saúde',                           icon: <ShieldAlert size={14} /> },
    { id: 'financeiro', label: 'Financeiro',                      icon: <CreditCard size={14} /> },
  ]

  return (
    <div className="px-6 py-8 max-w-5xl">

      {/* Volta */}
      <button onClick={() => navigate('/app/rh')} className="flex items-center gap-2 text-sm mb-5"
        style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
        <ArrowLeft size={15} /> Funcionários
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: '#fef9c3', color: 'var(--color-brand)' }}>
            <UserCog size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold"
                style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                {data.nome_completo}
              </h1>
              <span className="text-xs font-semibold px-2 py-1 rounded-full"
                style={{ background: sc.bg, color: sc.color, fontFamily: 'var(--font-body)' }}>
                {STATUS_LABEL[data.status_contrato]}
              </span>
            </div>
            <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {formatCPF(data.cpf)} · {cargoNome} · Admitido em {formatDate(data.data_admissao)}
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

      {/* ── Aba: Dados Pessoais ─────────────────────────────────────────────── */}
      {activeTab === 'dados' && (
        <div className="flex flex-col gap-5">
          <Card title="Identificação">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              <Field label="Nome Completo"    value={data.nome_completo} />
              <Field label="CPF"              value={formatCPF(data.cpf)} />
              <Field label="RG"               value={data.rg ?? undefined} />
              <Field label="Data Nascimento"  value={formatDate(data.data_nascimento)} />
              <Field label="Gênero"           value={{ masculino: 'Masculino', feminino: 'Feminino', outro: 'Outro' }[data.genero]} />
              <Field label="Estado Civil"     value={data.estado_civil ? ({ solteiro: 'Solteiro(a)', casado: 'Casado(a)', divorciado: 'Divorciado(a)', viuvo: 'Viúvo(a)', uniao_estavel: 'União Estável' })[data.estado_civil] : undefined} />
            </div>
          </Card>

          <Card title="Contato & Endereço">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              <Field label="E-mail Pessoal"   value={data.email_pessoal ?? undefined} />
              <Field label="Telefone"         value={formatPhone(data.telefone_pessoal)} />
              <Field label="Celular (WhatsApp)" value={formatPhone(data.telefone_celular)} />
              <div className="col-span-full">
                <Field label="Endereço"       value={data.endereco_completo} />
              </div>
            </div>
          </Card>

          <Card title="Contrato">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              <Field label="Cargo"               value={cargoNome} />
              <Field label="Status"              value={STATUS_LABEL[data.status_contrato]} />
              <Field label="Data de Admissão"    value={formatDate(data.data_admissao)} />
              <Field label="Data de Demissão"    value={formatDate(data.data_demissao)} />
              <Field label="Salário Base"        value={formatCurrency(data.salario_base)} />
            </div>
          </Card>

          <Card title="Documentos Trabalhistas">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              <Field label="PIS/PASEP"   value={formatPISPASEP(data.pis_pasep)} />
              <Field label="Nº CTPS"     value={data.numero_ctps ?? undefined} />
              <Field label="Série CTPS"  value={data.serie_ctps ?? undefined} />
            </div>
          </Card>
        </div>
      )}

      {/* ── Aba: Documentos ─────────────────────────────────────────────────── */}
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
                <div key={doc.documento_id}
                  className="flex items-center justify-between p-4 rounded-lg"
                  style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                  <div className="flex items-center gap-3">
                    <FileText size={18} style={{ color: 'var(--color-brand)', flexShrink: 0 }} />
                    <div>
                      <p className="text-sm font-medium" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                        {doc.nome_documento}
                      </p>
                      <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                        {doc.tipo_documento.toUpperCase()} · {formatDate(doc.data_upload)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {/* D70: o arquivo saiu de `/media/` e passou a exigir token,
                        então abrir é XHR + object URL — `<a href>` chegaria sem
                        `Authorization` e levaria 401. */}
                    <button onClick={() => abrirEmNovaAba(doc.arquivo)}
                      className="p-1.5 rounded" title="Abrir"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-brand)' }}>
                      <ExternalLink size={14} />
                    </button>
                    <button onClick={() => deleteDocumento(doc.documento_id)}
                      className="p-1.5 rounded" title="Remover"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Form inline de upload */}
          {docFormOpen && (
            <div className="mt-5 p-4 rounded-xl" style={{ background: '#f8fafc', border: '1.5px dashed #e2e8f0' }}>
              <p className="text-xs font-bold mb-3" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)', textTransform: 'uppercase' }}>
                Novo Documento
              </p>
              <div className="flex flex-col gap-3">
                <select value={docTipo} onChange={e => setDocTipo(e.target.value)} style={inpStyle}>
                  <option value="">Tipo de documento…</option>
                  <option value="rg">RG</option>
                  <option value="cpf">CPF</option>
                  <option value="cnh">CNH</option>
                  <option value="ctps">CTPS</option>
                  <option value="comprovante_residencia">Comprovante de Residência</option>
                  <option value="certificado_curso">Certificado de Curso</option>
                  <option value="aso">ASO</option>
                  <option value="outros">Outros</option>
                </select>
                <input value={docNome} onChange={e => setDocNome(e.target.value)}
                  placeholder="Nome do documento" style={inpStyle} />
                {/* Arquivo */}
                <input ref={fileInputRef} type="file"
                  onChange={e => setDocFile(e.target.files?.[0] ?? null)}
                  style={{ display: 'none' }} />
                <button type="button" onClick={() => fileInputRef.current?.click()}
                  style={{ ...inpStyle, textAlign: 'left', cursor: 'pointer',
                    color: docFile ? 'var(--color-text)' : 'var(--color-text-muted)',
                    background: '#f8fafc' }}>
                  {docFile ? docFile.name : 'Escolher arquivo…'}
                </button>
                <div className="flex gap-2">
                  <button onClick={() => setDocFormOpen(false)} style={cancelBtnSm}>Cancelar</button>
                  <button onClick={handleUpload} disabled={!docFile || !docTipo || !docNome || uploading}
                    style={{ ...saveBtnSm, opacity: (!docFile || !docTipo || !docNome || uploading) ? 0.6 : 1 }}>
                    {uploading ? 'Enviando…' : 'Enviar'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Aba: Saúde ──────────────────────────────────────────────────────── */}
      {activeTab === 'saude' && (
        <div className="flex flex-col gap-5">
          {acessoMedicoNegado ? (
            <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
              <AccessDenied role="rh_medico" />
            </div>
          ) : (
            <>
              {/* Dados de Saúde (gerais — 1 por funcionário) */}
              <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
                <SectionHeader title="Dados de Saúde"
                  onAdd={() => setMedicoOpen(true)}
                  addLabel={dadoMedico ? 'Editar' : 'Preencher'} />
                {!dadoMedico ? (
                  <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                    Nenhum dado de saúde cadastrado.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                    <Field label="Cartão SUS"           value={dadoMedico.numero_cartao_sus ?? undefined} />
                    <Field label="Tipo Sanguíneo"       value={dadoMedico.tipo_sanguineo ?? undefined} />
                    <Field label="Alergias"             value={dadoMedico.alergias ?? undefined} />
                    <Field label="Medicamentos"         value={dadoMedico.medicamentos ?? undefined} />
                    <Field label="Contato Emergência"   value={dadoMedico.contato_emergencia_nome ?? undefined} />
                    <Field label="Tel. Emergência"      value={dadoMedico.contato_emergencia_telefone ?? undefined} />
                    <Field label="Observações"          value={dadoMedico.observacoes_medicas ?? undefined} />
                  </div>
                )}
              </div>

              {/* ASOs (múltiplos — um por exame ocupacional/ano) */}
              <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
                <SectionHeader title={`ASOs — Atestados de Saúde Ocupacional (${asos.length})`}
                  onAdd={() => setAsoForm({ open: true, editing: null })} addLabel="Registrar ASO" />
                {asos.length === 0 ? (
                  <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                    Nenhum ASO cadastrado. Registre um a cada exame ocupacional realizado (admissional, periódico ou demissional).
                  </p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {asos.map(aso => {
                      const sc = ASO_STATUS_COLORS[aso.status] ?? ASO_STATUS_COLORS.ativo
                      return (
                        <div key={aso.aso_id} className="p-4 rounded-lg relative"
                          style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <ShieldAlert size={15} style={{ color: 'var(--color-brand)' }} />
                              <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                                {TIPO_ASO_LABEL[aso.tipo_exame] ?? aso.tipo_exame}
                              </span>
                              <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                                style={{ background: sc.bg, color: sc.color, fontFamily: 'var(--font-body)' }}>
                                {ASO_STATUS_LABEL[aso.status] ?? aso.status}
                              </span>
                            </div>
                            <div className="flex gap-1">
                              <button onClick={() => setAsoForm({ open: true, editing: aso })}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                                <Pencil size={13} />
                              </button>
                              <button onClick={() => deleteASO(aso.aso_id)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                            <Field label="Data do Exame" value={formatDate(aso.data_exame)} />
                            <Field label="Validade"      value={formatDate(aso.data_validade)} />
                            {aso.arquivo && (
                              <div>
                                <p style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--color-text-muted)',
                                  textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'var(--font-body)', marginBottom: '2px' }}>
                                  Documento
                                </p>
                                <button onClick={() => abrirEmNovaAba(aso.arquivo!)}
                                  className="flex items-center gap-1"
                                  style={{ fontSize: '0.875rem', color: 'var(--color-brand)', fontFamily: 'var(--font-body)',
                                    background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                                  Abrir <ExternalLink size={12} />
                                </button>
                              </div>
                            )}
                          </div>
                          {aso.observacoes && (
                            <p className="text-xs mt-3" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                              {aso.observacoes}
                            </p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Aba: Financeiro ─────────────────────────────────────────────────── */}
      {activeTab === 'financeiro' && (
        <div className="flex flex-col gap-5">
          {acessoFinanceiroNegado ? (
            <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
              <AccessDenied role="rh_financeiro" />
            </div>
          ) : (
            <>
              {/* Dados Bancários */}
              <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
                <SectionHeader title="Dados Bancários"
                  onAdd={() => setBancoForm({ open: true, editing: null })} addLabel="Adicionar conta" />
                {dadosBancarios.length === 0 ? (
                  <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                    Nenhuma conta bancária cadastrada.
                  </p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {dadosBancarios.map(db => (
                      <div key={db.id} className="p-4 rounded-lg grid grid-cols-2 sm:grid-cols-3 gap-4 relative"
                        style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                        <div className="col-span-full flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <CreditCard size={15} style={{ color: 'var(--color-brand)' }} />
                            <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                              {db.titular_nome} · {TIPO_CONTA_LABEL[db.tipo_conta] ?? db.tipo_conta}
                            </span>
                          </div>
                          <div className="flex gap-1">
                            <button onClick={() => setBancoForm({ open: true, editing: db })}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                              <Pencil size={13} />
                            </button>
                            <button onClick={() => deleteDadoBancario(db.id)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>
                        <Field label="Banco"  value={db.codigo_banco} />
                        <Field label="Agência" value={db.agencia_dv ? `${db.agencia}-${db.agencia_dv}` : db.agencia} />
                        <Field label="Conta"  value={db.conta_dv ? `${db.conta}-${db.conta_dv}` : db.conta} />
                        <Field label="PIX"    value={db.chave_pix ?? undefined} />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Pagamentos */}
              <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
                <SectionHeader title="Pagamentos"
                  onAdd={() => setPagForm({ open: true, editing: null })} addLabel="Novo pagamento" />
                {pagamentos.length === 0 ? (
                  <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                    Nenhum pagamento registrado.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {pagamentos.map(p => (
                      <div key={p.id} className="flex items-center justify-between p-4 rounded-lg"
                        style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                        <div>
                          <p className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                            {formatCurrency(p.salario_liquido)} · {formatDate(p.data_pagamento)}
                          </p>
                          <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                            {FORMA_PAG_LABEL[p.forma_pagamento] ?? p.forma_pagamento}
                            {p.referencia_pagamento ? ` · Ref: ${p.referencia_pagamento}` : ''}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          {p.link_holerite && (
                            <a href={p.link_holerite} target="_blank" rel="noreferrer"
                              style={{ color: 'var(--color-brand)', padding: '4px' }}>
                              <ExternalLink size={13} />
                            </a>
                          )}
                          <button onClick={() => setPagForm({ open: true, editing: p })}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '4px' }}>
                            <Pencil size={13} />
                          </button>
                          <button onClick={() => deletePagamento(p.id)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: '4px' }}>
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Folhas de Pagamento */}
              <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
                <SectionHeader title="Folhas de Pagamento"
                  onAdd={() => setFolhaForm({ open: true, editing: null })} addLabel="Nova folha" />
                {folhas.length === 0 ? (
                  <p className="text-sm py-4 text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                    Nenhuma folha registrada.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {folhas.map(f => (
                      <div key={f.folha_id} className="flex items-center justify-between p-4 rounded-lg"
                        style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                        <div>
                          <p className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                            {formatMes(f.mes_referencia)} · Líquido: {formatCurrency(f.salario_liquido)}
                          </p>
                          <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                            Bruto: {formatCurrency(f.salario_bruto)} · Descontos: {formatCurrency(f.total_descontos)}
                            {f.data_pagamento ? ` · Pago em ${formatDate(f.data_pagamento)}` : ''}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          {/* D70: o holerite tem o MESMO gate dos valores da folha
                              (`rh.folha.view`) e agora sai pela porta única.
                              `link_holerite`, logo acima, é URL externa e continua
                              sendo `<a href>` — não é arquivo nosso. */}
                          {f.holerite && (
                            <button onClick={() => abrirEmNovaAba(f.holerite!)}
                              title="Abrir holerite"
                              style={{ background: 'none', border: 'none', cursor: 'pointer',
                                color: 'var(--color-brand)', padding: '4px' }}>
                              <ExternalLink size={13} />
                            </button>
                          )}
                          <button onClick={() => setFolhaForm({ open: true, editing: f })}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '4px' }}>
                            <Pencil size={13} />
                          </button>
                          <button onClick={() => deleteFolha(f.folha_id)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: '4px' }}>
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Confirm delete ─────────────────────────────────────────────────── */}
      {confirmDelete && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setConfirmDelete(false)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-80"
            style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <h3 className="text-base font-bold mb-2" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Excluir funcionário?
            </h3>
            <p className="text-sm mb-5" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Esta ação é permanente. Documentos e dados associados serão removidos.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDelete(false)} style={cancelBtnSm}>Cancelar</button>
              <button onClick={handleDelete} disabled={deleting}
                style={{ ...saveBtnSm, background: '#dc2626', opacity: deleting ? 0.7 : 1 }}>
                {deleting ? 'Excluindo…' : 'Sim, excluir'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Forms ──────────────────────────────────────────────────────────── */}
      <FuncionarioForm open={editOpen} onClose={() => setEditOpen(false)} onSave={handleUpdate} initial={data} />

      <DadoMedicoForm
        open={medicoOpen} onClose={() => setMedicoOpen(false)}
        onSave={handleSaveMedico} initial={dadoMedico} funcionarioId={funcionarioId} />

      <ASOForm
        open={asoForm.open} onClose={() => setAsoForm({ open: false, editing: null })}
        onSave={handleSaveASO} initial={asoForm.editing} funcionarioId={funcionarioId} />

      <DadoBancarioRHForm
        open={bancoForm.open} onClose={() => setBancoForm({ open: false, editing: null })}
        onSave={handleSaveBanco} initial={bancoForm.editing} funcionarioId={funcionarioId} />

      <PagamentoForm
        open={pagForm.open} onClose={() => setPagForm({ open: false, editing: null })}
        onSave={handleSavePag} initial={pagForm.editing} funcionarioId={funcionarioId} />

      <FolhaPagamentoForm
        open={folhaForm.open} onClose={() => setFolhaForm({ open: false, editing: null })}
        onSave={handleSaveFolha} initial={folhaForm.editing} funcionarioId={funcionarioId} />
    </div>
  )
}

// ─── Card wrapper ─────────────────────────────────────────────────────────────

const Card: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
    <h3 className="text-sm font-bold mb-4" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>{title}</h3>
    {children}
  </div>
)

const inpStyle: React.CSSProperties = {
  padding: '7px 10px', border: '1.5px solid #e2e8f0', borderRadius: '7px',
  fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
  background: '#FFFFFF', outline: 'none', width: '100%',
}
const cancelBtnSm: React.CSSProperties = {
  padding: '7px 14px', borderRadius: '7px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
  fontSize: '0.8125rem', color: 'var(--color-text-muted)',
}
const saveBtnSm: React.CSSProperties = {
  padding: '7px 16px', borderRadius: '7px', border: 'none',
  background: 'var(--color-brand)', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.8125rem', fontWeight: 600,
}

export default FuncionarioDetailPage
