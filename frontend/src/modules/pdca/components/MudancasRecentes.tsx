import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, CalendarCheck, ClipboardCheck, FileCheck2,
  GitBranch, HardHat, Unlock,
} from 'lucide-react'
import { Card, SectionHead } from '@/components/malha'
import { POSTO_DA_ORIGEM } from '../postos'
import type { FatoRecente, MudancasRecentes as Mudancas } from '../types'
import { SemPermissaoAviso } from './SemPermissaoAviso'

/** Para onde clicar num fato leva, e com que ícone ele aparece. */
const FATO: Record<string, { icone: typeof GitBranch; origem: keyof typeof POSTO_DA_ORIGEM }> = {
  medicao: { icone: FileCheck2, origem: 'medicao' },
  programacao: { icone: CalendarCheck, origem: 'programacao' },
  cronograma: { icone: GitBranch, origem: 'qualidade' },
  restricao: { icone: Unlock, origem: 'restricao' },
  nc: { icone: AlertTriangle, origem: 'qualidade' },
  verificacao: { icone: ClipboardCheck, origem: 'qualidade' },
  ocorrencia: { icone: HardHat, origem: 'seguranca' },
}

/** **Fatos, não posts** — o que mudou na obra desde que você saiu.
 *
 *  Cada linha é um ato com carimbo de quem o praticou, lido do próprio campo
 *  que o registrou. Responde à pergunta de quem tirou sexta-feira, e é a única
 *  faixa do cockpit que olha para trás. */
export function MudancasRecentes({
  mudancas, obraId,
}: { mudancas: Mudancas; obraId: number }) {
  const navigate = useNavigate()

  return (
    <section>
      <SectionHead sub={`Últimos ${mudancas.dias} dias`}>O que mudou</SectionHead>

      {mudancas.sem_permissao.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <SemPermissaoAviso itens={mudancas.sem_permissao} />
        </div>
      )}

      {mudancas.fatos.length === 0 ? (
        <Card>
          <span style={{ fontSize: 13, color: 'var(--ink-3)' }}>
            Nada foi atestado, encerrado ou registrado nesta obra nos últimos{' '}
            {mudancas.dias} dias.
          </span>
        </Card>
      ) : (
        <Card pad={false}>
          {mudancas.fatos.map((fato, i) => {
            const desenho = FATO[fato.tipo] ?? { icone: GitBranch, origem: 'qualidade' as const }
            const Icone = desenho.icone
            return (
              <button
                key={`${fato.chave}-${fato.verbo}`}
                type="button"
                onClick={() =>
                  navigate(`/app/pdca/o/${obraId}/${POSTO_DA_ORIGEM[desenho.origem]}`)
                }
                style={{
                  display: 'flex', alignItems: 'center', gap: 11, width: '100%',
                  padding: '10px 14px', background: 'none', cursor: 'pointer',
                  border: 'none', textAlign: 'left',
                  borderTop: i === 0 ? 'none' : '1px solid var(--line-2)',
                }}
              >
                <Icone size={14} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span
                    style={{
                      display: 'block', fontSize: 12.5, color: 'var(--ink)',
                      overflow: 'hidden', textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap', lineHeight: 1.4,
                    }}
                  >
                    <strong style={{ fontWeight: 650 }}>{fato.verbo}</strong>
                    {' · '}
                    {fato.titulo}
                  </span>
                  <span style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)' }}>
                    {quando(fato)}
                    {fato.quem && ` · por ${fato.quem}`}
                  </span>
                </span>
              </button>
            )
          })}
        </Card>
      )}
    </section>
  )
}

/** "há 2 dias" diz mais que a data absoluta numa lista do que aconteceu. */
function quando(fato: FatoRecente): string {
  const data = new Date(fato.quando)
  const dias = Math.floor((Date.now() - data.getTime()) / 86_400_000)
  if (dias <= 0) return `hoje, ${data.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
  if (dias === 1) return 'ontem'
  return `há ${dias} dias`
}
