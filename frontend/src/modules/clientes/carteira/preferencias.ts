import { useCallback, useEffect, useState } from 'react'
import type { Visao } from './types'
import { COLUNAS_PADRAO, ORDEM_PADRAO } from './colunas'

/**
 * Como cada pessoa deixou a planilha. Fica no `localStorage` (mesmo padrão do
 * colapso da sidebar e da localidade do calendário): quem trabalha agrupando por
 * quadra não quer remontar isso toda manhã.
 *
 * **Guardado por visão**, não uma vez só: "Clientes" e "Unidades" são duas
 * planilhas diferentes — colunas, larguras, agrupamento e ordem não se
 * traduzem de uma para a outra. Prefereência única era o que fazia a visão de
 * Unidades abrir com o cliente na primeira coluna, ordenada por nome.
 */
export interface PreferenciasVisao {
  colunas: string[]
  larguras: Record<string, number>
  agrupamento: string[]
  ordenar: string
}

export interface PreferenciasCarteira {
  visao: Visao
  porVisao: Record<Visao, PreferenciasVisao>
}

// v2: a v1 guardava uma preferência só para as duas visões. Ler aquela forma
// devolveria justamente o defeito corrigido aqui, então a chave muda de nome.
const CHAVE = 'sgi_carteira_clientes_v2'

const padraoDaVisao = (visao: Visao): PreferenciasVisao => ({
  colunas: COLUNAS_PADRAO[visao],
  larguras: {},
  agrupamento: [],
  ordenar: ORDEM_PADRAO[visao],
})

const PADRAO: PreferenciasCarteira = {
  visao: 'clientes',
  porVisao: { clientes: padraoDaVisao('clientes'), unidades: padraoDaVisao('unidades') },
}

function lerVisao(visao: Visao, salvo?: Partial<PreferenciasVisao>): PreferenciasVisao {
  const padrao = padraoDaVisao(visao)
  if (!salvo) return padrao
  return {
    ...padrao,
    ...salvo,
    // Coluna removida do código não pode ressuscitar por preferência antiga.
    colunas: Array.isArray(salvo.colunas) && salvo.colunas.length ? salvo.colunas : padrao.colunas,
    ordenar: salvo.ordenar || padrao.ordenar,
  }
}

function ler(): PreferenciasCarteira {
  try {
    const bruto = localStorage.getItem(CHAVE)
    if (!bruto) return PADRAO
    const salvo = JSON.parse(bruto) as Partial<PreferenciasCarteira>
    return {
      visao: salvo.visao === 'unidades' ? 'unidades' : 'clientes',
      porVisao: {
        clientes: lerVisao('clientes', salvo.porVisao?.clientes),
        unidades: lerVisao('unidades', salvo.porVisao?.unidades),
      },
    }
  } catch {
    return PADRAO
  }
}

export function usePreferenciasCarteira() {
  const [estado, setEstado] = useState<PreferenciasCarteira>(ler)

  useEffect(() => {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(estado))
    } catch {
      /* modo privado / cota cheia: a tela funciona, só não lembra. */
    }
  }, [estado])

  /** Muda uma preferência **da visão ativa** — a outra fica como estava. */
  const alterar = useCallback(<K extends keyof PreferenciasVisao>(
    chave: K, valor: PreferenciasVisao[K],
  ) => setEstado(e => ({
    ...e,
    porVisao: { ...e.porVisao, [e.visao]: { ...e.porVisao[e.visao], [chave]: valor } },
  })), [])

  const trocarVisao = useCallback(
    (visao: Visao) => setEstado(e => ({ ...e, visao })),
    [],
  )

  const restaurarVisao = useCallback(() => setEstado(e => ({
    ...e,
    porVisao: { ...e.porVisao, [e.visao]: padraoDaVisao(e.visao) },
  })), [])

  return {
    visao: estado.visao,
    prefs: estado.porVisao[estado.visao],
    alterar,
    trocarVisao,
    restaurarVisao,
  }
}
