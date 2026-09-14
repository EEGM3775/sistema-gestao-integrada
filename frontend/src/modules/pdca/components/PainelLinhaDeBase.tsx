import { useMemo, useState } from 'react'
import { Card, Empty, KpiTile, Pill, SectionHead } from '@/components/malha'
import type { PillKind } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { contemSemAcento } from '@/utils/texto'
import type { ComparacaoBase, SituacaoNaBase } from '../types'

const APARENCIA: Record<SituacaoNaBase, { rotulo: string; kind: PillKind }> = {
  mantida: { rotulo: 'Mantida', kind: 'slate' },
  atrasada: { rotulo: 'Atrasada', kind: 'danger' },
  adiantada: { rotulo: 'Adiantada', kind: 'good' },
  nova: { rotulo: 'Nova', kind: 'info' },
  removida: { rotulo: 'Removida', kind: 'accent' },
}

const ORDEM: SituacaoNaBase[] = ['atrasada', 'nova', 'removida', 'adiantada', 'mantida']

/**
 * O desvio contra o que foi combinado.
 *
 * A pergunta que este painel responde não é "quando termina" — é **"atrasou
 * quanto desde que a gente combinou, e por causa de quê"**. Por isso a ordem
 * padrão não é a da EAP: é a do tamanho do estrago, com a atividade que mais
 * escorregou em cima. Quem abre isto tem uma reunião em quinze minutos.
 */
export default function PainelLinhaDeBase({ comparacao, terminoAtual, versaoAtual }: {
  comparacao: ComparacaoBase
  terminoAtual: string | null
  versaoAtual: number
}) {
  const [filtro, setFiltro] = useState('')
  const [situacoes, setSituacoes] = useState<ReadonlySet<SituacaoNaBase>>(new Set())

  const contagem = useMemo(() => {
    const mapa = { mantida: 0, atrasada: 0, adiantada: 0, nova: 0, removida: 0 }
    for (const l of comparacao.linhas) mapa[l.situacao] += 1
    return mapa
  }, [comparacao.linhas])

  const linhas = useMemo(() => {
    const filtradas = comparacao.linhas.filter(l => {
      if (situacoes.size && !situacoes.has(l.situacao)) return false
      if (!filtro) return true
      return contemSemAcento(l.nome, filtro) || contemSemAcento(l.codigo, filtro)
    })
    return [...filtradas].sort((a, b) => {
      const peso = (d: number | null) => (d == null ? -1 : Math.abs(d))
      return peso(b.desvio_dias) - peso(a.desvio_dias)
        || a.codigo.localeCompare(b.codigo, 'pt-BR', { numeric: true })
    })
  }, [comparacao.linhas, filtro, situacoes])

  if (!comparacao.tem_base) {
    return (
      <div style={{ padding: '18px 2px' }}>
        <Empty>
          Esta é a <strong>primeira versão</strong> do plano — não há o que comparar ainda. A linha de
          base nasce no primeiro replanejamento: a versão que estava vigente vira a régua da seguinte,
          e é contra ela que o desvio passa a ser medido.
        </Empty>
      </div>
    )
  }

  const alternar = (s: SituacaoNaBase) => {
    setSituacoes(atual => {
      const proxima = new Set(atual)
      if (proxima.has(s)) proxima.delete(s)
      else proxima.add(s)
      return proxima
    })
  }

  const desvioDoFim = comparacao.base?.termino && terminoAtual
    ? Math.round((new Date(terminoAtual).getTime() - new Date(comparacao.base.termino).getTime()) / 86_400_000)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 2px 20px' }}>
      <section style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        <KpiTile
          label="Linha de base"
          valor={'v' + (comparacao.base?.versao ?? '—')}
          base={'comparada com a v' + versaoAtual}
        />
        <KpiTile
          label="Término combinado"
          valor={comparacao.base?.termino ? dateToBR(comparacao.base.termino) : 'sem cálculo'}
          base="na versão que virou base"
        />
        <KpiTile
          label="Término deste plano"
          valor={terminoAtual ? dateToBR(terminoAtual) : 'sem cálculo'}
          base={desvioDoFim == null
            ? 'rode o CPM para saber'
            : desvioDoFim === 0 ? 'na data combinada'
              : desvioDoFim > 0 ? desvioDoFim + ' dias depois' : Math.abs(desvioDoFim) + ' dias antes'}
        />
        <KpiTile
          label="Atividades atrasadas"
          valor={String(contagem.atrasada)}
          base={contagem.adiantada + ' adiantadas · ' + contagem.mantida + ' mantidas'}
        />
      </section>

      <Card style={{ padding: 16 }}>
        <SectionHead
          sub="Ordenado pelo tamanho do desvio — o que mais escorregou vem primeiro"
          right={
            <input
              value={filtro} onChange={e => setFiltro(e.target.value)}
              placeholder="Buscar atividade"
              style={{
                fontSize: 12.5, padding: '5px 9px', borderRadius: 7,
                border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)',
              }}
            />
          }
        >
          Atividade a atividade
        </SectionHead>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {ORDEM.map(s => (
            <button
              key={s} type="button" onClick={() => alternar(s)}
              style={{
                border: '1px solid var(--line)', borderRadius: 999, padding: '3px 10px',
                fontSize: 11.5, cursor: 'pointer',
                background: situacoes.has(s) ? 'var(--inset)' : 'transparent',
                color: situacoes.has(s) ? 'var(--ink)' : 'var(--ink-3)',
              }}
            >
              {APARENCIA[s].rotulo} · {contagem[s]}
            </button>
          ))}
        </div>

        {linhas.length === 0 ? (
          <Empty>Nenhuma atividade nesse recorte.</Empty>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--ink-3)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  <th style={celulaCabecalho}>EAP</th>
                  <th style={celulaCabecalho}>Atividade</th>
                  <th style={celulaCabecalho}>Situação</th>
                  <th style={celulaCabecalho}>Combinado</th>
                  <th style={celulaCabecalho}>Neste plano</th>
                  <th style={{ ...celulaCabecalho, textAlign: 'right' }}>Desvio</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map(l => (
                  <tr key={l.codigo} style={{ borderTop: '1px solid var(--line)' }}>
                    <td style={{ ...celula, color: 'var(--ink-3)' }}><code>{l.codigo}</code></td>
                    <td style={celula}>{l.nome}</td>
                    <td style={celula}><Pill kind={APARENCIA[l.situacao].kind}>{APARENCIA[l.situacao].rotulo}</Pill></td>
                    <td style={celula}>{intervalo(l.base_inicio, l.base_termino)}</td>
                    <td style={celula}>{intervalo(l.inicio, l.termino)}</td>
                    <td style={{ ...celula, textAlign: 'right', fontWeight: l.desvio_dias ? 650 : 400, color: corDoDesvio(l.desvio_dias) }}>
                      {l.desvio_dias == null ? '—' : (l.desvio_dias > 0 ? '+' : '') + l.desvio_dias + ' d'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

const celulaCabecalho: React.CSSProperties = { padding: '6px 10px', fontWeight: 700 }
const celula: React.CSSProperties = { padding: '7px 10px', verticalAlign: 'top' }

const intervalo = (inicio: string | null, fim: string | null) =>
  inicio ? dateToBR(inicio) + ' a ' + (fim ? dateToBR(fim) : '—') : '—'

const corDoDesvio = (dias: number | null) =>
  dias == null || dias === 0 ? 'var(--ink-2)' : dias > 0 ? 'var(--danger-ink)' : 'var(--good-ink)'
