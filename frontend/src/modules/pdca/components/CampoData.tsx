import { useEffect, useState, type CSSProperties } from 'react'
import { maxCalendarioISO, minCalendarioISO } from '@/utils/dates'

function valida(iso: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) && iso >= minCalendarioISO && iso <= maxCalendarioISO
}

/** Data que grava **só quando está inteira e dentro da faixa**.
 *
 *  O `<input type="date">` gravando a cada `onChange` quebrava quem digita: o
 *  ano entra um dígito por vez e o navegador entrega "0002-10-06", "0020-…",
 *  "0202-…" antes de "2026-…" — cada um ia ao servidor, que recusava (e o CPM
 *  recalculava no meio). Aqui o calendário do navegador continua gravando no
 *  clique; a digitação grava quando o ano fecha, ou no Enter / ao sair.
 *  Data pela metade ao sair volta ao valor gravado — esvaziar é pelo botão de
 *  soltar de quem usa o campo, nunca por acidente. */
export function CampoData(
  { valor, aoGravar, rotulo, estilo }: {
    valor: string | null
    aoGravar: (iso: string) => unknown
    rotulo?: string
    estilo?: CSSProperties
  },
) {
  const [rascunho, setRascunho] = useState(valor ?? '')
  useEffect(() => { setRascunho(valor ?? '') }, [valor])

  function gravar(iso: string) {
    if (iso !== (valor ?? '') && valida(iso)) void aoGravar(iso)
  }

  return (
    <input
      type="date"
      min={minCalendarioISO}
      max={maxCalendarioISO}
      aria-label={rotulo}
      value={rascunho}
      onChange={(e) => { setRascunho(e.target.value); gravar(e.target.value) }}
      onBlur={() => { if (!valida(rascunho)) setRascunho(valor ?? '') }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        if (e.key === 'Escape') { setRascunho(valor ?? ''); (e.target as HTMLInputElement).blur() }
      }}
      style={estilo}
    />
  )
}
