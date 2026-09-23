import { useState } from 'react'
import { Btn, Modal } from '@/components/malha'
import { parseApiErrors } from '@/utils/formErrors'
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
          <Btn variant="primary" onClick={confirmar} disabled={salvando}>
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
          Escreva o que aconteceu. É o que a reunião da semana que vem lê.
        </span>
      </div>
    </Modal>
  )
}
