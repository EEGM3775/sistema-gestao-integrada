import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Btn, Modal } from '@/components/malha'
import { parseApiErrors } from '@/utils/formErrors'
import { restricoes } from '../api/pdcaApi'
import { AndamentoDaCompra } from '../components/AndamentoDaCompra'
import type { TravaDaFrente } from '../types'

/** Destravar no canteiro — **uma decisão, uma tela**.
 *
 *  Quem vê o material chegar é quem está lá, e obrigá-lo a avisar o escritório
 *  para que o escritório destrave é o caminho que faz a trava sobreviver à
 *  entrega. A nota continua obrigatória, pela mesma razão do escritório: a
 *  reunião da semana que vem precisa saber se ela foi resolvida ou esquecida. */
export function DialogoDeDestrave({
  trava, salvando, aoFechar, aoConfirmar,
}: {
  trava: TravaDaFrente
  salvando: boolean
  aoFechar: () => void
  aoConfirmar: (nota: string) => Promise<void>
}) {
  const [nota, setNota] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  // A conferência no sistema: a trava ainda está aberta? a compra que ela abriu chegou?
  const conferencia = useQuery({
    queryKey: ['pdca', 'restricao', trava.restricao, 'conferencia'],
    queryFn: () => restricoes.obter(trava.restricao),
    staleTime: 0, retry: false,
  })
  const atual = conferencia.data
  const jaResolvida = !!atual && atual.status !== 'aberta'
  const compra = atual?.compra ?? null

  async function confirmar() {
    setErro(null)
    try {
      await aoConfirmar(nota)
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(erros.nota ?? erros._form ?? erros.detail ?? 'Não foi possível destravar.')
    }
  }

  return (
    <Modal
      titulo="Como foi resolvida"
      onClose={aoFechar}
      largura={440}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={confirmar} disabled={salvando || jaResolvida}>
            {salvando ? 'Destravando…' : 'Destravar'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        {erro && (
          <div
            role="alert"
            style={{
              fontSize: 13, padding: '11px 13px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)',
              lineHeight: 1.5,
            }}
          >
            {erro}
          </div>
        )}

        <div
          style={{
            fontSize: 13.5, color: 'var(--ink-2)', lineHeight: 1.5,
            background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: '11px 13px',
          }}
        >
          {trava.descricao}
        </div>

        <div
          role="status"
          style={{
            fontSize: 12.5, lineHeight: 1.5, borderRadius: 'var(--r-sm)', padding: '10px 12px',
            border: '1px solid var(--line)', background: 'var(--surface-2)', color: 'var(--ink-2)',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}
        >
          <b style={{ color: 'var(--ink)' }}>Conferência no sistema</b>
          {conferencia.isPending && <span>Conferindo a trava e a compra…</span>}
          {conferencia.isError && (
            <span>Não consegui conferir agora. A nota abaixo é o registro de como foi resolvida.</span>
          )}
          {jaResolvida && (
            <span style={{ color: 'var(--danger-ink)' }}>
              Esta trava já não está aberta ({atual?.status_rotulo?.toLowerCase()}
              {atual?.removida_por ? ` por ${atual.removida_por}` : ''}). Nada a destravar.
            </span>
          )}
          {atual && !jaResolvida && !compra && (
            <span>
              {trava.demanda_scm
                ? `Há a demanda #${trava.demanda_scm} no Suprimentos, sem andamento registrado ainda.`
                : 'Sem compra ligada a esta trava — nada no Suprimentos confirma; vale a sua palavra e a nota.'}
            </span>
          )}
          {compra && (
            <>
              <AndamentoDaCompra compra={compra} />
              <span style={{ color: compra.sugerir_destravar ? 'var(--good-ink)' : 'var(--warn-ink, var(--ink-2))' }}>
                {compra.sugerir_destravar
                  ? 'O Suprimentos registra o material recebido — pode destravar.'
                  : 'O Suprimentos ainda não registra o recebimento completo. Se o material chegou, avise o escritório para dar a entrada.'}
              </span>
            </>
          )}
        </div>

        <textarea
          value={nota}
          onChange={(e) => { setNota(e.target.value); setErro(null) }}
          rows={3}
          autoFocus
          placeholder="Ex.: material chegou hoje de manhã e já está na frente"
          style={{
            width: '100%', padding: '12px 13px', borderRadius: 10, fontSize: 16,
            border: '1px solid var(--line)', background: 'var(--surface)',
            color: 'var(--ink)', fontFamily: 'inherit', resize: 'vertical',
          }}
        />
        <span style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          Descreva o que aconteceu. A reunião da semana seguinte lê este texto.
        </span>
      </div>
    </Modal>
  )
}
