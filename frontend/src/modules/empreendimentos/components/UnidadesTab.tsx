import React, { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import type { SituacaoUnidade, Unidade, UnidadeFormData } from '@/types'
import UnidadeForm from './UnidadeForm'
import {
  createUnidade, deleteUnidade, updateUnidade, useUnidades, type FiltrosUnidades,
} from '../hooks/useUnidades'

/**
 * A aba Unidades: linhas e colunas para ver o que o empreendimento tem à venda.
 *
 * Mesma mecânica da carteira de clientes — colunas ordenáveis (**no servidor**,
 * sobre o estoque inteiro, não sobre a página carregada), filtros e carregamento
 * por página. A ordem padrão é a do endereço, quadra › lote › bloco › andar ›
 * apto, e **numérica**: em ordem de texto o lote 10 viria antes do 2.
 *
 * Visual: mantém a linguagem atual da página de empreendimento (a migração para
 * a identidade Malha é passo à parte, ainda não feito aqui).
 */
interface Props {
  empreendimentoId: number
  /** Avisa a página para recarregar os contadores da Visão Geral. */
  onMudou?: () => void
}

interface ColunaUnidade {
  chave: string
  titulo: string
  largura?: string
  alinhamento?: 'left' | 'right' | 'center'
  /** Chave aceita pelo backend em `?ordering=`; sem ela a coluna não ordena. */
  ordenar?: string
  valor: (u: Unidade) => React.ReactNode
}

const brl = (v: string | null) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const CORES_SITUACAO: Record<SituacaoUnidade, [string, string]> = {
  disponivel: ['#dcfce7', '#166534'],
  reservada: ['#fef9c3', '#854d0e'],
  vendida: ['#e0e7ff', '#3730a3'],
  indisponivel: ['#f1f5f9', '#475569'],
}

function Pilula({ unidade }: { unidade: Unidade }) {
  const [fundo, cor] = CORES_SITUACAO[unidade.situacao] ?? CORES_SITUACAO.indisponivel
  return (
    <span style={{
      background: fundo, color: cor, borderRadius: 999, padding: '2px 9px',
      fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'nowrap',
    }}>
      {unidade.situacao_display}
    </span>
  )
}

const COLUNAS: ColunaUnidade[] = [
  { chave: 'rotulo', titulo: 'Unidade', largura: '190px', valor: u => u.rotulo },
  { chave: 'quadra', titulo: 'Quadra', largura: '80px', alinhamento: 'right', valor: u => u.quadra || '—' },
  { chave: 'lote', titulo: 'Lote', largura: '70px', alinhamento: 'right', valor: u => u.lote || '—' },
  { chave: 'bloco_torre', titulo: 'Bloco/Torre', largura: '110px', valor: u => u.bloco_torre || '—' },
  { chave: 'andar', titulo: 'Andar', largura: '70px', alinhamento: 'right', valor: u => u.andar || '—' },
  { chave: 'apto', titulo: 'Apto/Nº', largura: '90px', alinhamento: 'right', valor: u => u.apto || '—' },
  {
    chave: 'tipo', titulo: 'Tipo', largura: '110px', ordenar: 'tipo',
    valor: u => u.tipo_display,
  },
  {
    chave: 'area', titulo: 'Área (m²)', largura: '95px', alinhamento: 'right',
    ordenar: 'area_privativa',
    valor: u => (u.area_privativa ? Number(u.area_privativa).toLocaleString('pt-BR') : '—'),
  },
  {
    chave: 'valor_base', titulo: 'Valor de tabela', largura: '140px', alinhamento: 'right',
    ordenar: 'valor_base', valor: u => brl(u.valor_base),
  },
  { chave: 'situacao', titulo: 'Situação', largura: '110px', ordenar: 'situacao', valor: u => <Pilula unidade={u} /> },
  {
    chave: 'cliente', titulo: 'Comprador', largura: '180px',
    valor: u => u.cliente_nome || '—',
  },
]

const celula: React.CSSProperties = {
  padding: '9px 12px', fontSize: '0.8rem', color: 'var(--color-text)',
  borderBottom: '1px solid #f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden',
  textOverflow: 'ellipsis',
}

const campo: React.CSSProperties = {
  padding: '7px 10px', fontSize: '0.8rem', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', background: '#FFFFFF', color: 'var(--color-text)',
  outline: 'none', fontFamily: 'var(--font-body)',
}

const UnidadesTab: React.FC<Props> = ({ empreendimentoId, onMudou }) => {
  const [filtros, setFiltros] = useState<FiltrosUnidades>({})
  const [buscaDigitada, setBuscaDigitada] = useState('')
  const [formAberto, setFormAberto] = useState(false)
  const [editando, setEditando] = useState<Unidade | null>(null)
  const [erroAcao, setErroAcao] = useState<string | null>(null)

  const { unidades, total, loading, error, temMais, carregarMais, recarregar } =
    useUnidades(empreendimentoId, filtros)

  // As quadras já carregadas viram o filtro rápido — evita um endpoint só para
  // listar quadras enquanto a aba não precisa dele.
  const quadras = useMemo(
    () => [...new Set(unidades.map(u => u.quadra).filter(Boolean))].sort(
      (a, b) => Number(a) - Number(b) || a.localeCompare(b),
    ),
    [unidades],
  )

  const ordenarPor = (chave: string) => {
    const atual = filtros.ordering
    setFiltros(f => ({ ...f, ordering: atual === chave ? `-${chave}` : chave }))
  }

  const salvar = async (dados: UnidadeFormData) => {
    if (editando) await updateUnidade(editando.unidade_id, dados)
    else await createUnidade(dados)
    recarregar()
    onMudou?.()
  }

  const excluir = async (unidade: Unidade) => {
    setErroAcao(null)
    if (!window.confirm(`Excluir a unidade ${unidade.rotulo}?`)) return
    try {
      await deleteUnidade(unidade.unidade_id)
      recarregar()
      onMudou?.()
    } catch {
      setErroAcao(`${unidade.rotulo} não pôde ser excluída — unidade vendida. Cancele a aquisição antes.`)
    }
  }

  const disponiveis = unidades.filter(u => u.situacao === 'disponivel').length
  const vendidas = unidades.filter(u => u.situacao === 'vendida').length

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            {total} unidade{total !== 1 ? 's' : ''} cadastrada{total !== 1 ? 's' : ''}
            {unidades.length < total && ` · ${unidades.length} carregada${unidades.length !== 1 ? 's' : ''}`}
          </p>
          {unidades.length > 0 && (
            <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
              nesta lista: {disponiveis} à venda · {vendidas} vendida{vendidas !== 1 ? 's' : ''}
            </p>
          )}
        </div>
        <button onClick={() => { setEditando(null); setFormAberto(true) }}
          className="px-4 py-2 rounded-lg text-sm font-semibold inline-flex items-center gap-2"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
            cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
          <Plus size={16} /> Nova unidade
        </button>
      </div>

      {/* Filtros */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div style={{ position: 'relative', minWidth: 240 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
          <input
            value={buscaDigitada}
            onChange={e => setBuscaDigitada(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') setFiltros(f => ({ ...f, busca: buscaDigitada || undefined })) }}
            onBlur={() => setFiltros(f => ({ ...f, busca: buscaDigitada || undefined }))}
            placeholder="Buscar quadra, lote, apto…"
            style={{ ...campo, width: '100%', paddingLeft: 30 }}
          />
        </div>
        <select style={campo} value={filtros.situacao ?? ''}
          onChange={e => setFiltros(f => ({ ...f, situacao: e.target.value || undefined }))}>
          <option value="">Todas as situações</option>
          <option value="disponivel">Disponíveis</option>
          <option value="reservada">Reservadas</option>
          <option value="vendida">Vendidas</option>
          <option value="indisponivel">Indisponíveis</option>
        </select>
        <select style={campo} value={filtros.quadra ?? ''}
          onChange={e => setFiltros(f => ({ ...f, quadra: e.target.value || undefined }))}>
          <option value="">Todas as quadras</option>
          {quadras.map(q => <option key={q} value={q}>Quadra {q}</option>)}
        </select>
        {filtros.ordering && (
          <button onClick={() => setFiltros(f => ({ ...f, ordering: undefined }))}
            style={{ ...campo, cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            Ordem do endereço
          </button>
        )}
      </div>

      {erroAcao && (
        <p style={{ fontSize: '0.8rem', color: '#b91c1c', marginBottom: 8 }}>{erroAcao}</p>
      )}
      {error && (
        <p style={{ fontSize: '0.8rem', color: '#b91c1c', marginBottom: 8 }}>{error}</p>
      )}

      {unidades.length === 0 && !loading ? (
        <div style={{
          padding: '32px', textAlign: 'center', background: '#f8fafc',
          borderRadius: '10px', color: 'var(--color-text-muted)', fontSize: '0.85rem',
        }}>
          {filtros.busca || filtros.situacao || filtros.quadra
            ? 'Nenhuma unidade para os filtros aplicados.'
            : 'Nenhuma unidade cadastrada. O cadastro das unidades é o que permite vender pela ficha do cliente.'}
        </div>
      ) : (
        <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: '10px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {COLUNAS.map(coluna => {
                  const ativa = coluna.ordenar && filtros.ordering?.replace('-', '') === coluna.ordenar
                  const descendente = ativa && filtros.ordering?.startsWith('-')
                  return (
                    <th key={coluna.chave}
                      onClick={() => coluna.ordenar && ordenarPor(coluna.ordenar)}
                      title={coluna.ordenar ? `Ordenar por ${coluna.titulo}` : coluna.titulo}
                      style={{
                        padding: '9px 12px', fontSize: '0.68rem', fontWeight: 700,
                        letterSpacing: '0.06em', textTransform: 'uppercase',
                        color: 'var(--color-text-muted)', textAlign: coluna.alinhamento ?? 'left',
                        width: coluna.largura, whiteSpace: 'nowrap',
                        cursor: coluna.ordenar ? 'pointer' : 'default',
                        borderBottom: '1px solid #e2e8f0',
                      }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {coluna.titulo}
                        {ativa && (descendente ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                      </span>
                    </th>
                  )
                })}
                <th style={{ width: 80, borderBottom: '1px solid #e2e8f0' }} />
              </tr>
            </thead>
            <tbody>
              {unidades.map(unidade => (
                <tr key={unidade.unidade_id}>
                  {COLUNAS.map((coluna, i) => (
                    <td key={coluna.chave} style={{
                      ...celula,
                      textAlign: coluna.alinhamento ?? 'left',
                      fontWeight: i === 0 ? 600 : 400,
                      fontFamily: ['quadra', 'lote', 'andar', 'apto', 'valor_base', 'area', 'rotulo'].includes(coluna.chave)
                        ? 'var(--font-mono, monospace)' : 'var(--font-body)',
                    }}>
                      {coluna.valor(unidade)}
                    </td>
                  ))}
                  <td style={{ ...celula, textAlign: 'right' }}>
                    <button onClick={() => { setEditando(unidade); setFormAberto(true) }}
                      title="Editar" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', marginRight: 6 }}>
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => excluir(unidade)}
                      title={unidade.situacao === 'vendida' ? 'Unidade vendida — cancele a aquisição antes' : 'Excluir'}
                      disabled={unidade.situacao === 'vendida'}
                      style={{
                        background: 'none', border: 'none', color: '#b91c1c',
                        cursor: unidade.situacao === 'vendida' ? 'not-allowed' : 'pointer',
                        opacity: unidade.situacao === 'vendida' ? 0.35 : 1,
                      }}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(temMais || loading) && (
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <button onClick={carregarMais} disabled={loading}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: '#FFFFFF', border: '1.5px solid #e2e8f0', cursor: loading ? 'wait' : 'pointer',
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            {loading ? 'Carregando…' : `Carregar mais (${total - unidades.length} restantes)`}
          </button>
        </div>
      )}

      <UnidadeForm
        open={formAberto}
        empreendimentoId={empreendimentoId}
        initial={editando}
        onClose={() => { setFormAberto(false); setEditando(null) }}
        onSave={salvar}
      />
    </div>
  )
}

export default UnidadesTab
