import { useEffect, useRef, useState } from 'react'
import { Check, Columns3, Filter, Layers, Search, X } from 'lucide-react'
import type { ColunaDef } from './colunas'
import type { FiltrosCarteira, OpcoesCarteira, Visao } from './types'

const botao: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 11px',
  fontSize: 12.5, fontWeight: 600, borderRadius: 'var(--r-sm)', cursor: 'pointer',
  background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)',
}

const campo: React.CSSProperties = {
  padding: '6px 9px', fontSize: 12.5, color: 'var(--ink)', background: 'var(--surface)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', outline: 'none',
}

function Painel({ children, onFechar, largura = 260 }: { children: React.ReactNode; onFechar: () => void; largura?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const fora = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onFechar()
    }
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [onFechar])
  return (
    <div
      ref={ref}
      style={{
        position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 30, width: largura,
        background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
        boxShadow: 'var(--shadow-lg)', padding: 10, maxHeight: 420, overflowY: 'auto',
      }}
    >
      {children}
    </div>
  )
}

/**
 * A barra da planilha: o que é uma linha (visão), como as linhas se juntam
 * (agrupar por), o que aparece (colunas) e o que entra (filtros/busca).
 *
 * O agrupamento é empilhável até 3 níveis, como o *row grouping* dos grids
 * corporativos e os Subtotais do Excel: "empreendimento › quadra › faixa de
 * atraso" é uma pergunta legítima do dia a dia da carteira.
 */
export function BarraCarteira({
  visao, onVisao, busca, onBusca, agrupamento, onAgrupamento, colunas, colunasVisiveis,
  ancora, onColunas, filtros, onFiltros, opcoes, total, repetidosEmGrupos = 0,
  podeFinanceiro,
}: {
  visao: Visao
  onVisao: (v: Visao) => void
  busca: string
  onBusca: (v: string) => void
  agrupamento: string[]
  onAgrupamento: (n: string[]) => void
  colunas: ColunaDef[]
  colunasVisiveis: string[]
  /** A coluna que identifica a linha na visão ativa — fixa, não se desliga. */
  ancora: string
  onColunas: (c: string[]) => void
  filtros: FiltrosCarteira
  onFiltros: (f: FiltrosCarteira) => void
  opcoes?: OpcoesCarteira
  /** O total de linhas do recorte — o mesmo número agrupado ou não. */
  total: number
  /**
   * Quantas linhas aparecem em mais de um cabeçalho, quando se agrupa por uma
   * dimensão de muitos (o cliente que comprou em dois empreendimentos está nos
   * dois grupos). Zero na maioria das combinações.
   *
   * Existe para **explicar** a diferença, não para escondê-la: sem esta frase,
   * quem soma os cabeçalhos à mão encontra um número maior que o total e passa
   * a desconfiar dos dois.
   */
  repetidosEmGrupos?: number
  podeFinanceiro: boolean
}) {
  const [painel, setPainel] = useState<'grupo' | 'colunas' | 'filtros' | null>(null)
  const dimensoes = opcoes?.dimensoes[visao] ?? []
  const filtrosAtivos = Object.entries(filtros).filter(([k, v]) => k !== 'busca' && v).length

  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        padding: '10px 18px', background: 'var(--surface)', borderBottom: '1px solid var(--line)',
      }}
    >
      {/* Visão: o que é uma linha */}
      <div style={{ display: 'inline-flex', gap: 2, padding: 2, background: 'var(--inset)', border: '1px solid var(--line)', borderRadius: 999 }}>
        {([
          ['clientes', 'Clientes', 'Uma linha por pessoa, em ordem alfabética'],
          ['unidades', 'Unidades', 'Uma linha por unidade, na ordem quadra › lote › bloco/torre › andar › apto'],
        ] as const).map(([v, rotulo, explicacao]) => (
          <button
            key={v}
            onClick={() => onVisao(v)}
            title={explicacao}
            style={{
              border: 'none', borderRadius: 999, padding: '5px 13px', fontSize: 12.5, fontWeight: 650,
              cursor: 'pointer', whiteSpace: 'nowrap',
              background: visao === v ? 'var(--surface)' : 'transparent',
              color: visao === v ? 'var(--ink)' : 'var(--ink-3)',
              boxShadow: visao === v ? 'var(--shadow-sm)' : 'none',
            }}
          >
            {rotulo}
          </button>
        ))}
      </div>

      {/* Busca */}
      <div style={{ position: 'relative', minWidth: 260, flex: '1 1 260px', maxWidth: 420 }}>
        <Search size={14} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)' }} />
        <input
          value={busca}
          onChange={e => onBusca(e.target.value)}
          placeholder={visao === 'unidades' ? 'Buscar por cliente, CPF, quadra ou lote…' : 'Buscar por nome, CPF, e-mail ou telefone…'}
          style={{ ...campo, width: '100%', paddingLeft: 28 }}
        />
      </div>

      {/* Agrupar por */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setPainel(p => (p === 'grupo' ? null : 'grupo'))}
          style={{ ...botao, ...(agrupamento.length ? { borderColor: 'var(--accent)', color: 'var(--accent-ink)', background: 'var(--accent-soft)' } : {}) }}
        >
          <Layers size={14} />
          {agrupamento.length
            ? agrupamento.map(a => dimensoes.find(d => d.chave === a)?.rotulo ?? a).join(' › ')
            : 'Agrupar por'}
        </button>
        {painel === 'grupo' && (
          <Painel onFechar={() => setPainel(null)} largura={280}>
            <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 8 }}>
              Empilhe até 3 níveis. A ordem dos cliques é a ordem dos níveis.
            </div>
            {dimensoes.map(d => {
              const posicao = agrupamento.indexOf(d.chave)
              return (
                <button
                  key={d.chave}
                  onClick={() =>
                    onAgrupamento(
                      posicao >= 0
                        ? agrupamento.filter(a => a !== d.chave)
                        : agrupamento.length < 3 ? [...agrupamento, d.chave] : agrupamento,
                    )
                  }
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
                    padding: '7px 8px', border: 'none', borderRadius: 'var(--r-sm)', cursor: 'pointer',
                    background: posicao >= 0 ? 'var(--accent-soft)' : 'transparent',
                    color: posicao >= 0 ? 'var(--accent-ink)' : 'var(--ink-2)', fontSize: 12.5,
                  }}
                >
                  <span className="num" style={{ width: 14, fontSize: 11, opacity: posicao >= 0 ? 1 : 0.25 }}>
                    {posicao >= 0 ? posicao + 1 : '·'}
                  </span>
                  {d.rotulo}
                </button>
              )
            })}
            {agrupamento.length > 0 && (
              <button onClick={() => onAgrupamento([])} style={{ ...botao, width: '100%', marginTop: 8, justifyContent: 'center' }}>
                <X size={13} /> Sem agrupamento
              </button>
            )}
          </Painel>
        )}
      </div>

      {/* Colunas */}
      <div style={{ position: 'relative' }}>
        <button onClick={() => setPainel(p => (p === 'colunas' ? null : 'colunas'))} style={botao}>
          <Columns3 size={14} /> Colunas
        </button>
        {painel === 'colunas' && (
          <Painel onFechar={() => setPainel(null)}>
            {colunas.map(c => {
              const visivel = colunasVisiveis.includes(c.chave)
              const fixa = c.chave === ancora
              return (
                <button
                  key={c.chave}
                  onClick={() =>
                    onColunas(
                      visivel
                        ? colunasVisiveis.filter(x => x !== c.chave)
                        : [...colunasVisiveis, c.chave],
                    )
                  }
                  disabled={fixa || (visivel && colunasVisiveis.length === 1)}
                  title={fixa ? 'Identifica a linha nesta visão — sempre a primeira coluna' : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
                    padding: '7px 8px', border: 'none', borderRadius: 'var(--r-sm)',
                    cursor: fixa ? 'default' : 'pointer', background: 'transparent', fontSize: 12.5,
                    color: visivel ? 'var(--ink)' : 'var(--ink-3)',
                  }}
                >
                  <Check size={13} style={{ opacity: visivel ? 1 : 0.15 }} />
                  {c.titulo}
                  {fixa && (
                    <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--ink-3)' }}>fixa</span>
                  )}
                </button>
              )
            })}
            <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 8, lineHeight: 1.5 }}>
              Arraste o cabeçalho para reordenar; a borda direita redimensiona. Toda coluna
              tem “Ordenar por” no cabeçalho.
              {!podeFinanceiro && ' Colunas de valores exigem permissão de cobranças.'}
            </div>
          </Painel>
        )}
      </div>

      {/* Filtros */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setPainel(p => (p === 'filtros' ? null : 'filtros'))}
          style={{ ...botao, ...(filtrosAtivos ? { borderColor: 'var(--accent)', color: 'var(--accent-ink)', background: 'var(--accent-soft)' } : {}) }}
        >
          <Filter size={14} /> Filtros{filtrosAtivos ? ` (${filtrosAtivos})` : ''}
        </button>
        {painel === 'filtros' && (
          <Painel onFechar={() => setPainel(null)} largura={300}>
            <Campo rotulo="Empreendimento">
              <select
                value={filtros.empreendimento ?? ''}
                onChange={e => onFiltros({ ...filtros, empreendimento: e.target.value })}
                style={{ ...campo, width: '100%' }}
              >
                <option value="">Todos</option>
                {opcoes?.empreendimentos.map(e => (
                  <option key={e.id} value={e.id}>{e.nome}</option>
                ))}
              </select>
            </Campo>
            <Campo rotulo="Situação">
              <select
                value={filtros.faixa ?? ''}
                onChange={e => onFiltros({ ...filtros, faixa: e.target.value })}
                style={{ ...campo, width: '100%' }}
              >
                <option value="">Todas</option>
                {opcoes?.faixas.map(f => (
                  <option key={f.chave} value={f.chave}>{f.rotulo}</option>
                ))}
              </select>
            </Campo>
            <Campo rotulo="Quadra">
              <select
                value={filtros.quadra ?? ''}
                onChange={e => onFiltros({ ...filtros, quadra: e.target.value })}
                style={{ ...campo, width: '100%' }}
              >
                <option value="">Todas</option>
                {opcoes?.quadras.map(q => <option key={q} value={q}>{q}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Cidade">
              <select
                value={filtros.cidade ?? ''}
                onChange={e => onFiltros({ ...filtros, cidade: e.target.value })}
                style={{ ...campo, width: '100%' }}
              >
                <option value="">Todas</option>
                {opcoes?.cidades.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Ano da compra">
              <select
                value={filtros.ano_compra ?? ''}
                onChange={e => onFiltros({ ...filtros, ano_compra: e.target.value })}
                style={{ ...campo, width: '100%' }}
              >
                <option value="">Todos</option>
                {opcoes?.anos.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </Campo>
            {filtrosAtivos > 0 && (
              <button onClick={() => onFiltros({ busca: filtros.busca })} style={{ ...botao, width: '100%', justifyContent: 'center' }}>
                <X size={13} /> Limpar filtros
              </button>
            )}
          </Painel>
        )}
      </div>

      <span
        className="num"
        style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--ink-3)', textAlign: 'right' }}
        title={repetidosEmGrupos > 0
          ? `Somando os grupos dá ${(total + repetidosEmGrupos).toLocaleString('pt-BR')}: `
            + `${repetidosEmGrupos.toLocaleString('pt-BR')} aparecem em mais de um grupo `
            + '(quem comprou em mais de um empreendimento, por exemplo). '
            + 'O total ao lado conta cada um uma vez.'
          : undefined}
      >
        {total.toLocaleString('pt-BR')} {visao === 'unidades' ? 'unidades' : 'clientes'}
        {repetidosEmGrupos > 0 && (
          <span style={{ display: 'block', fontSize: 10.5, color: 'var(--ink-3)' }}>
            {repetidosEmGrupos.toLocaleString('pt-BR')} em mais de um grupo
          </span>
        )}
      </span>
    </div>
  )
}

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', marginBottom: 9 }}>
      <span style={{ display: 'block', fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 4 }}>
        {rotulo}
      </span>
      {children}
    </label>
  )
}
