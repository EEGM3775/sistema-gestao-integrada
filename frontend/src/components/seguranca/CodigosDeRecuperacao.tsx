import { useState } from 'react'
import { Copy, Download, Check } from 'lucide-react'
import { Btn } from '@/components/malha'

interface CodigosDeRecuperacaoProps {
  codigos: string[]
  conta: string
  aoConcluir: () => void
  rotuloConcluir?: string
}

/**
 * A única vez em que os códigos aparecem. Por isso o "continuar" só destrava
 * depois de a pessoa dizer que guardou — e há dois jeitos de guardar sem
 * redigitar: copiar e baixar.
 */
export function CodigosDeRecuperacao({ codigos, conta, aoConcluir, rotuloConcluir = 'Continuar' }: CodigosDeRecuperacaoProps) {
  const [guardou, setGuardou] = useState(false)
  const [copiou, setCopiou] = useState(false)
  const texto = `Códigos de recuperação — conta ${conta}\nCada código vale uma vez.\n\n${codigos.join('\n')}\n`

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(texto)
      setCopiou(true)
    } catch {
      setCopiou(false)
    }
  }
  const baixar = () => {
    const url = URL.createObjectURL(new Blob([texto], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `codigos-de-recuperacao-${conta}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5, margin: 0 }}>
        Guarde estes códigos longe do celular — impressos, ou num gerenciador de senhas. Se perder o
        celular, cada um deles entra no lugar do código do app <b>uma única vez</b>. Eles não serão
        mostrados de novo.
      </p>
      <ol
        data-codigos-de-recuperacao
        style={{
          display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '6px 18px',
          margin: 0, padding: '12px 14px 12px 34px', borderRadius: 'var(--r-sm)',
          background: 'var(--surface-2)', border: '1px solid var(--line)',
          fontFamily: 'var(--font-mono, monospace)', fontSize: 14, color: 'var(--ink)',
        }}
      >
        {codigos.map(c => <li key={c}>{c}</li>)}
      </ol>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Btn type="button" tam="sm" onClick={copiar}>
          {copiou ? <Check size={14} /> : <Copy size={14} />} {copiou ? 'Copiados' : 'Copiar'}
        </Btn>
        <Btn type="button" tam="sm" onClick={baixar}><Download size={14} /> Baixar arquivo</Btn>
      </div>
      <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, color: 'var(--ink)', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={guardou}
          onChange={e => setGuardou(e.target.checked)}
          style={{ width: 16, height: 16, marginTop: 1, accentColor: 'var(--brand)' }}
        />
        Guardei os códigos num lugar seguro.
      </label>
      <div>
        <Btn type="button" variant="brand" disabled={!guardou} onClick={aoConcluir}>{rotuloConcluir}</Btn>
      </div>
    </div>
  )
}
