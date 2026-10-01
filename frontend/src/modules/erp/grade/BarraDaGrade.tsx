import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Layers, Loader2, Search, X } from 'lucide-react'
import { formatBRL } from '@/utils/money'
import type { Dimensao, Somas } from './tipos'

/** Espera depois da última tecla — o bastante para não pedir uma busca por letra. */
const ESPERA_DA_BUSCA_MS = 300

const reais = (v?: string) => formatBRL(Math.round(Number(v ?? 0) * 100))

/**
 * A busca que responde enquanto se digita (item 51 do dono: "igual o Google").
 * O texto na caixa é da pessoa; a busca só parte quando ela para de digitar, e
 * a grade continua mostrando o resultado anterior até o novo chegar.
 */
export function CaixaDeBusca({ valor, onBuscar, placeholder, buscando }: {
  valor: string
  onBuscar: (termo: string) => void
  placeholder: string
  buscando: boolean
}) {
  const [texto, setTexto] = useState(valor)
  const ultimo = useRef(valor)

  useEffect(() => { if (valor !== ultimo.current) { setTexto(valor); ultimo.current = valor } }, [valor])

  useEffect(() => {
    const id = setTimeout(() => {
      const termo = texto.trim()
      if (termo !== ultimo.current) { ultimo.current = termo; onBuscar(termo) }
    }, ESPERA_DA_BUSCA_MS)
    return () => clearTimeout(id)
  }, [texto, onBuscar])

  return (
    <div style={{ position: 'relative', flex: '1 1 340px', minWidth: 240 }}>
      <Search size={17} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)' }} />
      <input
        type="search"
        value={texto}
        onChange={e => setTexto(e.target.value)}
        onKeyDown={e => { if (e.key === 'Escape') setTexto('') }}
        placeholder={placeholder}
        aria-label={placeholder}
        style={{
          width: '100%', padding: '10px 38px 10px 38px', borderRadius: 'var(--r-md)', fontSize: 14,
          border: '1.5px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)',
          outline: 'none', fontFamily: 'var(--sans)',
        }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--line)')}
      />
      <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', display: 'flex' }}>
        {buscando ? (
          <Loader2 size={16} className="animate-spin" style={{ color: 'var(--ink-3)' }} />
        ) : texto ? (
          <button type="button" aria-label="Limpar busca" onClick={() => setTexto('')}
            style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'var(--ink-3)', display: 'flex' }}>
            <X size={16} />
          </button>
        ) : null}
      </span>
    </div>
  )
}

export interface OpcaoSituacao {
  valor: string
  rotulo: string
}

/** Os recortes que a pessoa usa o dia inteiro, a um clique. */
export function Situacoes({ opcoes, valor, onEscolher }: {
  opcoes: OpcaoSituacao[]
  valor: string
  onEscolher: (v: string) => void
}) {
  return (
    <div role="radiogroup" aria-label="Situação" style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: 3, gap: 2 }}>
      {opcoes.map(o => {
        const ativa = o.valor === valor
        return (
          <button
            key={o.valor || 'todas'}
            type="button"
            role="radio"
            aria-checked={ativa}
            onClick={() => onEscolher(o.valor)}
            style={{
              border: 'none', borderRadius: 'var(--r-sm)', padding: '6px 12px', fontSize: 12.5, cursor: 'pointer',
              fontWeight: ativa ? 650 : 500, fontFamily: 'var(--sans)',
              background: ativa ? 'var(--surface)' : 'transparent', color: ativa ? 'var(--ink)' : 'var(--ink-3)',
              boxShadow: ativa ? 'var(--shadow-sm, 0 1px 2px rgba(0,0,0,.08))' : 'none',
            }}
          >
            {o.rotulo}
          </button>
        )
      })}
    </div>
  )
}

/** "Agrupar por", empilhável até o teto do `planos.py`. */
export function AgruparPor({ dimensoes, niveis, teto, onMudar }: {
  dimensoes: Dimensao[]
  niveis: string[]
  teto: number
  onMudar: (niveis: string[]) => void
}) {
  const livres = dimensoes.filter(d => !niveis.includes(d.chave))
  const rotulo = (chave: string) => dimensoes.find(d => d.chave === chave)?.rotulo ?? chave
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <Layers size={15} style={{ color: 'var(--ink-3)' }} />
      {niveis.map((n, i) => (
        <span key={n} style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 6px 4px 10px', borderRadius: 999,
          background: 'var(--accent-soft)', color: 'var(--accent-ink)', fontSize: 12, fontWeight: 600,
        }}>
          {i > 0 && <span style={{ opacity: 0.6 }}>›</span>} {rotulo(n)}
          <button type="button" aria-label={`Parar de agrupar por ${rotulo(n)}`} onClick={() => onMudar(niveis.filter(x => x !== n))}
            style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'inherit', display: 'flex' }}>
            <X size={13} />
          </button>
        </span>
      ))}
      {niveis.length < teto && livres.length > 0 && (
        <select
          value=""
          aria-label="Agrupar por"
          onChange={e => e.target.value && onMudar([...niveis, e.target.value])}
          style={{
            border: '1.5px solid var(--line)', borderRadius: 'var(--r-sm)', padding: '5px 8px', fontSize: 12.5,
            background: 'var(--surface)', color: 'var(--ink-2)', cursor: 'pointer', fontFamily: 'var(--sans)',
          }}
        >
          <option value="">{niveis.length ? '+ subgrupo' : 'Agrupar por…'}</option>
          {livres.map(d => <option key={d.chave} value={d.chave}>{d.rotulo}</option>)}
        </select>
      )}
    </div>
  )
}

/** O recorte num relance — do banco, sobre tudo o que o filtro pega. */
export function Totais({ totais, substantivo, mostrarSaldo, extra }: {
  totais?: Somas
  substantivo: [string, string]
  mostrarSaldo: boolean
  extra?: ReactNode
}) {
  if (!totais) return <div style={{ height: 22 }} />
  const n = totais.contagem
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap', fontSize: 13, color: 'var(--ink-2)', fontVariantNumeric: 'tabular-nums' }}>
      <span><strong style={{ color: 'var(--ink)' }}>{n.toLocaleString('pt-BR')}</strong> {n === 1 ? substantivo[0] : substantivo[1]}</span>
      {mostrarSaldo ? (
        <>
          <span><strong style={{ color: 'var(--ink)' }}>{reais(totais.saldo)}</strong> em aberto</span>
          {Number(totais.vencido ?? 0) > 0 && (
            <span style={{ color: 'var(--danger-ink)' }}><strong>{reais(totais.vencido)}</strong> vencido</span>
          )}
        </>
      ) : (
        <span><strong style={{ color: 'var(--ink)' }}>{reais(totais.valor)}</strong> no total</span>
      )}
      {extra}
    </div>
  )
}
