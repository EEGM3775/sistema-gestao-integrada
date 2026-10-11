import { Check, FileSignature, Landmark } from 'lucide-react'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import type { LinhaDeContrato } from '../types'
import { paradasDoContrato, type Desvio, type Parada } from '../trilha'

/** **O mapa do contrato.** *Pedido do dono, 10/10/2026:* "não dá pra saber o que
 *  estou fazendo nem para onde estou indo. Não quero avisos na tela — quero
 *  igual um jogo com ótimo design de mapas: sempre deixa o usuário saber
 *  exatamente o caminho, mas sem ficar avisando o que tem que fazer."
 *
 *  O caminho é uma linha só, da planilha ao executado: o que já foi feito fica
 *  marcado, a **próxima parada brilha** e a parada aberta tem o anel de "você
 *  está aqui". Aditivos e retenção não são etapas — são desvios ao lado da
 *  estrada, e ficam no fim, menores. Nenhuma frase manda fazer nada: o mapa
 *  mostra, e clicar numa parada leva até ela. */
export function TrilhaDoContrato({
  contrato, aqui, aoIr, desvioAqui, aoDesviar,
}: {
  contrato: LinhaDeContrato
  aqui: Parada | null
  aoIr: (p: Parada) => void
  desvioAqui: Desvio | null
  aoDesviar: (d: Desvio) => void
}) {
  const nos = paradasDoContrato(contrato)
  const s = contrato.saldo
  return (
    <nav aria-label="Caminho do contrato" style={{ display: 'flex', alignItems: 'stretch', gap: 0, padding: '12px 18px', borderBottom: '1px solid var(--line-2)', background: 'var(--surface-2)', flexShrink: 0, overflowX: 'auto' }}>
      <ol style={{ display: 'flex', alignItems: 'flex-start', listStyle: 'none', margin: 0, padding: 0, flex: 1, minWidth: 620 }}>
        {nos.map((no, i) => {
          const estou = aqui === no.chave
          const cor = no.estado === 'feito' ? 'var(--good-ink)' : no.estado === 'agora' ? 'var(--brand)' : 'var(--ink-3)'
          return (
            <li key={no.chave} style={{ display: 'flex', alignItems: 'flex-start', flex: i < nos.length - 1 ? 1 : 'none' }}>
              <button
                type="button"
                onClick={() => aoIr(no.chave)}
                aria-current={estou ? 'step' : undefined}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, background: 'none', border: 'none', padding: '0 4px', cursor: 'pointer', minWidth: 96 }}
              >
                <span style={{
                  width: 28, height: 28, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 750, fontFamily: 'var(--mono)',
                  background: no.estado === 'feito' ? 'var(--good-soft)' : no.estado === 'agora' ? 'var(--brand)' : 'var(--surface)',
                  color: no.estado === 'agora' ? 'var(--brand-ink)' : cor,
                  border: `2px solid ${no.estado === 'depois' ? 'var(--line)' : cor}`,
                  boxShadow: estou ? '0 0 0 3px var(--surface-2), 0 0 0 5px var(--ink-2)' : no.estado === 'agora' ? '0 0 0 4px var(--accent-soft)' : 'none',
                }}>
                  {no.estado === 'feito' ? <Check size={14} /> : i + 1}
                </span>
                <span style={{ fontSize: 12, fontWeight: estou ? 750 : 650, color: estou ? 'var(--ink)' : cor }}>{no.rotulo}</span>
                <span style={{ fontSize: 10.5, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>{no.diz}</span>
              </button>
              {i < nos.length - 1 && (
                <span aria-hidden style={{
                  flex: 1, height: 2, marginTop: 14, minWidth: 16,
                  background: nos[i + 1].estado === 'depois' ? 'var(--line)' : 'var(--good-ink)',
                  opacity: nos[i + 1].estado === 'depois' ? 1 : 0.5,
                }} />
              )}
            </li>
          )
        })}
      </ol>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 16, marginLeft: 12, borderLeft: '1px dashed var(--line)', justifyContent: 'center' }}>
        {([
          { chave: 'aditivos' as const, rotulo: 'Aditivos', diz: s.aditivos_abertos > 0 ? `${s.aditivos_abertos} em aberto` : `${s.aditivos}`, icone: FileSignature },
          { chave: 'retencao' as const, rotulo: 'Retenção', diz: formatBRL(apiDecimalToCents(s.retencao?.disponivel ?? '0')), icone: Landmark },
        ]).map(({ chave, rotulo, diz, icone: Icone }) => (
          <button
            key={chave} type="button" onClick={() => aoDesviar(chave)}
            aria-current={desvioAqui === chave ? 'page' : undefined}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, background: desvioAqui === chave ? 'var(--surface)' : 'none',
              border: `1px solid ${desvioAqui === chave ? 'var(--line)' : 'transparent'}`, borderRadius: 6,
              padding: '3px 8px', cursor: 'pointer', fontSize: 11.5, color: desvioAqui === chave ? 'var(--ink)' : 'var(--ink-3)',
            }}
          >
            <Icone size={12} /> {rotulo} <span style={{ fontFamily: 'var(--mono)', fontSize: 10.5 }}>{diz}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
