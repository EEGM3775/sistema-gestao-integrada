import { useState } from 'react'
import { BotaoExportar, Btn, Card, Empty, Loading, Modal, Num, Pill } from '@/components/malha'
import { dateToBR, maxCalendarioISO, maxTodayISO, minCalendarioISO } from '@/utils/dates'
import { percentual, primeiraFrase } from '../formato'
import { useAplicarFicha, useFichas, useModelos } from '../hooks'
import { Ajuda, Campo, FaixaDeErro, Linha } from './Formulario'
import { SeletorDeLugar } from './SeletorDeLugar'
import type { Verificacao } from '../types'
import { entrada } from '../estilos'

/** As fichas aplicadas nesta obra — as em andamento primeiro, porque são as
 *  que alguém ainda precisa terminar. */
export function ListaDeFichas({
  obraId, podeAplicar, aoAbrir, aoIrParaModelos,
}: {
  obraId: number
  podeAplicar: boolean
  aoAbrir: (id: number) => void
  aoIrParaModelos: () => void
}) {
  const fichas = useFichas(obraId)
  const [aplicando, setAplicando] = useState(false)

  const lista = [...(fichas.data ?? [])].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'em_andamento' ? -1 : 1
    return b.data.localeCompare(a.data)
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 12.5, color: 'var(--ink-3)', flex: 1 }}>
          A ficha é a inspeção de um serviço contra o modelo da empresa — o que se
          confere e com que critério.
        </span>
        <BotaoExportar tam="md" recurso="pdca.verificacao" recorte={{ obra: obraId }} />
        {podeAplicar && (
          <Btn variant="primary" onClick={() => setAplicando(true)}>Aplicar uma ficha</Btn>
        )}
      </div>

      {fichas.isLoading ? (
        <Loading o="as fichas da obra" />
      ) : lista.length === 0 ? (
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              Nenhuma ficha aplicada nesta obra ainda.
            </span>
            {podeAplicar && (
              <Btn variant="primary" onClick={() => setAplicando(true)}>Aplicar a primeira ficha</Btn>
            )}
          </Empty>
        </Card>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {lista.map((ficha) => (
            <LinhaDaFicha key={ficha.verificacao_id} ficha={ficha} aoAbrir={aoAbrir} />
          ))}
        </Card>
      )}

      {aplicando && (
        <AplicarFicha
          obraId={obraId}
          aoFechar={() => setAplicando(false)}
          aoIrParaModelos={() => { setAplicando(false); aoIrParaModelos() }}
          aoAplicar={(nova) => { setAplicando(false); aoAbrir(nova.verificacao_id) }}
        />
      )}
    </div>
  )
}

function LinhaDaFicha({ ficha, aoAbrir }: { ficha: Verificacao; aoAbrir: (id: number) => void }) {
  const r = ficha.resultado
  const julgados = r ? r.conformes + r.nao_conformes : 0
  return (
    <button
      type="button"
      onClick={() => aoAbrir(ficha.verificacao_id)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, width: '100%',
        padding: '11px 14px', borderTop: '1px solid var(--line-2)',
        background: 'transparent', border: 'none', borderTopStyle: 'solid',
        cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13.5, color: 'var(--ink)', fontWeight: 650 }}>{ficha.modelo_nome}</span>
          <Pill kind={ficha.status === 'em_andamento' ? 'accent' : 'good'}>{ficha.status_rotulo}</Pill>
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
          {dateToBR(ficha.data)}
          {ficha.inspetor && ` · ${ficha.inspetor}`}
          {[ficha.local_rotulo, ficha.atividade_nome].filter(Boolean).map((t) => ` · ${t}`).join('')}
        </div>
      </div>
      {r && (
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          {julgados ? (
            <Num size={14} tone={r.nao_conformes ? 'var(--danger-ink)' : 'var(--ink)'}>
              {percentual(r.conformidade)}
            </Num>
          ) : (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>sem apuração</span>
          )}
          <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            {r.total - r.pendentes}/{r.total} respondidas
          </div>
        </div>
      )}
    </button>
  )
}

/** Abrir a ficha **é copiar o modelo para dentro dela** — o congelamento da
 *  pergunta. Por isso a tela pede o modelo primeiro, e só os ativos. */
export function AplicarFicha({
  obraId, aoFechar, aoAplicar, aoIrParaModelos, inicial,
}: {
  obraId: number
  aoFechar: () => void
  aoAplicar: (ficha: Verificacao) => void
  aoIrParaModelos?: () => void
  inicial?: { local?: number | null; atividade?: number | null; inspetor?: string }
}) {
  const modelos = useModelos(false)
  const aplicar = useAplicarFicha()
  const [modelo, setModelo] = useState<number | ''>('')
  const [data, setData] = useState(maxTodayISO())
  const [local, setLocal] = useState<number | null>(inicial?.local ?? null)
  const [atividade, setAtividade] = useState<number | null>(inicial?.atividade ?? null)
  const [inspetor, setInspetor] = useState(inicial?.inspetor ?? '')
  const [erro, setErro] = useState<string | null>(null)

  const ativos = modelos.data ?? []

  return (
    <Modal
      titulo="Aplicar uma ficha de verificação"
      onClose={aoFechar}
      largura={620}
      alto
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={modelo === '' || !data || aplicar.isPending}
            onClick={async () => {
              if (modelo === '') return
              setErro(null)
              try {
                aoAplicar(await aplicar.mutateAsync({
                  modelo, obra: obraId, data, local, atividade, inspetor: inspetor.trim(),
                }))
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            {aplicar.isPending ? 'Abrindo…' : 'Abrir a ficha'}
          </Btn>
        </div>
      }
    >
      <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <FaixaDeErro>{erro}</FaixaDeErro>

        {!modelos.isLoading && ativos.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
            A empresa ainda não tem modelo de ficha. O modelo é o método de vocês —
            o que se confere em cada serviço e com que critério — e por isso ele
            começa vazio.
            {aoIrParaModelos && (
              <div style={{ marginTop: 10 }}>
                <Btn variant="primary" onClick={aoIrParaModelos}>Montar o primeiro modelo</Btn>
              </div>
            )}
          </div>
        ) : (
          <>
            <Campo rotulo="Modelo">
              <select
                value={modelo}
                onChange={(e) => setModelo(e.target.value ? Number(e.target.value) : '')}
                style={entrada}
                disabled={modelos.isLoading}
              >
                <option value="">{modelos.isLoading ? 'Carregando…' : 'Escolha o modelo'}</option>
                {ativos.map((m) => (
                  <option key={m.modelo_id} value={m.modelo_id}>
                    {m.codigo} · {m.nome} ({m.itens_count} {m.itens_count === 1 ? 'pergunta' : 'perguntas'})
                  </option>
                ))}
              </select>
            </Campo>
            <Linha>
              <Campo rotulo="Data da inspeção">
                <input
                  type="date" value={data} min={minCalendarioISO} max={maxCalendarioISO}
                  onChange={(e) => setData(e.target.value)} style={entrada}
                />
              </Campo>
              <Campo rotulo="Quem inspeciona" larga>
                <input value={inspetor} onChange={(e) => setInspetor(e.target.value)} style={entrada} />
                <Ajuda>O nome que vai assinar a ficha.</Ajuda>
              </Campo>
            </Linha>
            <SeletorDeLugar
              obraId={obraId}
              local={local}
              atividade={atividade}
              aoMudarLocal={setLocal}
              aoMudarAtividade={setAtividade}
            />
          </>
        )}
      </div>
    </Modal>
  )
}
