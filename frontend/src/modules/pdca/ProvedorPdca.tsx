import { useMemo, useState, type ReactNode } from 'react'
import type { Obra } from '@/types'
import { Contexto, type ContextoPdca } from './contexto'
import type { Selecao } from './types'

export function ProvedorPdca(
  { obraId, obra, children }: { obraId: number; obra: Obra | undefined; children: ReactNode },
) {
  const [selecao, setSelecao] = useState<Selecao>(null)
  const [paletaAberta, setPaletaAberta] = useState(false)
  const [planoEscolhido, setPlanoEscolhido] = useState<number | null>(null)

  const valor = useMemo<ContextoPdca>(() => ({
    obraId,
    obra,
    selecao,
    selecionar: setSelecao,
    planoEscolhido,
    escolherPlano: setPlanoEscolhido,
    paletaAberta,
    abrirPaleta: () => setPaletaAberta(true),
    fecharPaleta: () => setPaletaAberta(false),
  }), [obraId, obra, selecao, planoEscolhido, paletaAberta])

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}
