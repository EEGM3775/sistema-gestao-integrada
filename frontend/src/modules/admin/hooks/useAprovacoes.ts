import { useCallback, useEffect, useState } from 'react'
import apiClient from '@/api/apiClient'
import iamAdminClient from '@/api/iamAdminClient'
import type { CatalogoResposta } from '../types'

/**
 * As escadas de atesto do tenant — `/api/aprovacao/`.
 *
 * **Fica no `apiClient`, e não no `iamAdminClient`**, porque a máquina de
 * aprovação é do **backend** (`nucleo`), não da IAM: o que ela aprova são
 * documentos de negócio (medição, e amanhã pagamento acima de alçada). O que
 * vem da IAM é só o **catálogo de permissões**, para o seletor do degrau poder
 * oferecer códigos que existem em vez de pedir que alguém os digite.
 */

export interface AlvoDeAprovacao {
  id: number
  codigo: string
  rotulo: string
  modulo: string
}

export interface Degrau {
  nivel_id: number
  fluxo: number
  ordem: number
  nome: string
  permissao_exigida: string
  prazo_dias: number | null
}

export interface Fluxo {
  fluxo_id: number
  codigo: string
  nome: string
  alvo: number
  alvo_rotulo: string
  padrao: boolean
  permite_autoatesto: boolean
  ativo: boolean
  descricao: string
  niveis: Degrau[]
}

const lista = <T,>(dados: unknown): T[] =>
  Array.isArray(dados) ? (dados as T[]) : ((dados as { results?: T[] })?.results ?? [])

export function useAprovacoes() {
  const [fluxos, setFluxos] = useState<Fluxo[]>([])
  const [alvos, setAlvos] = useState<AlvoDeAprovacao[]>([])
  const [catalogo, setCatalogo] = useState<CatalogoResposta | null>(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState<string | null>(null)

  const buscar = useCallback(async () => {
    setCarregando(true)
    setErro(null)
    try {
      const [f, a] = await Promise.all([
        apiClient.get('aprovacao/fluxos/'),
        apiClient.get('aprovacao/fluxos/alvos/'),
      ])
      setFluxos(lista<Fluxo>(f.data))
      setAlvos(a.data as AlvoDeAprovacao[])
      // O catálogo é da IAM e pode falhar sozinho (quem não é admin do tenant
      // não o lê). A tela continua utilizável sem ele — o seletor de permissão
      // vira campo de texto —, então o erro **não** derruba a página.
      try {
        const cat = await iamAdminClient.get('/catalogo-permissoes/')
        setCatalogo(cat.data)
      } catch { /* seletor cai para texto livre */ }
    } catch {
      setErro(
        'Não deu para carregar as escadas de aprovação. Configurar alçada é ato '
        + 'de administrador do tenant (plataforma.fluxo_aprovacao.edit).',
      )
    } finally {
      setCarregando(false)
    }
  }, [])

  useEffect(() => { buscar() }, [buscar])

  const criarFluxo = async (dados: Partial<Fluxo>) => {
    const res = await apiClient.post('aprovacao/fluxos/', dados)
    await buscar()
    return res.data as Fluxo
  }

  const atualizarFluxo = async (id: number, dados: Partial<Fluxo>) => {
    const res = await apiClient.patch(`aprovacao/fluxos/${id}/`, dados)
    await buscar()
    return res.data as Fluxo
  }

  const excluirFluxo = async (id: number) => {
    await apiClient.delete(`aprovacao/fluxos/${id}/`)
    await buscar()
  }

  const criarDegrau = async (dados: Partial<Degrau>) => {
    await apiClient.post('aprovacao/niveis/', dados)
    await buscar()
  }

  const atualizarDegrau = async (id: number, dados: Partial<Degrau>) => {
    await apiClient.patch(`aprovacao/niveis/${id}/`, dados)
    await buscar()
  }

  const excluirDegrau = async (id: number) => {
    await apiClient.delete(`aprovacao/niveis/${id}/`)
    await buscar()
  }

  /** Reordena **numa transação no servidor**, e não trocando `ordem` de dois
   *  degraus com dois PATCH: a constraint `(fluxo, ordem)` é imediata, e uma
   *  falha no meio deixaria a escada com numeração quebrada — recusada pela
   *  validação e travando um documento que ninguém tocou. */
  const reordenarDegraus = async (fluxoId: number, idsEmOrdem: number[]) => {
    await apiClient.post(`aprovacao/fluxos/${fluxoId}/reordenar/`, {
      niveis: idsEmOrdem,
    })
    await buscar()
  }

  /** Pergunta ao servidor se a escada está utilizável **antes** de alguém
   *  depender dela — a validação natural aconteceria no momento em que o gestor
   *  submete a medição, que é o pior momento possível para descobrir um buraco
   *  na numeração dos degraus. */
  const validar = async (id: number) => {
    const res = await apiClient.get(`aprovacao/fluxos/${id}/validar/`)
    return res.data as { valido: boolean; problemas: string[] }
  }

  return {
    fluxos, alvos, catalogo, carregando, erro, recarregar: buscar,
    criarFluxo, atualizarFluxo, excluirFluxo,
    criarDegrau, atualizarDegrau, excluirDegrau, reordenarDegraus, validar,
  }
}
