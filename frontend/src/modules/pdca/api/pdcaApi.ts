import apiClient from '@/api/apiClient'
import type { Obra } from '@/types'
import type {
  ApontamentoAvanco, Atividade, CalendarioTrabalho, CandidatoDaSemana,
  CausaNaoCumprimento, Cronograma, ItemProgramacao, JulgamentoDeItem, LocalObra,
  PayloadBalanco, PayloadBusca, PayloadCarteira, PayloadGantt, PayloadHoje,
  PayloadMinhasFrentes, ProgramacaoSemanal, RankingDeCausas, Restricao,
  ResultadoDoArrasto, ResumoDoPpc, StatusModulo,
} from '../types'

type Params = Record<string, unknown>

/** O DRF pagina algumas listas e outras não; as duas formas chegam aqui. */
function lista<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  const pagina = data as { results?: T[] } | null
  return pagina?.results ?? []
}

export async function getStatusModulo(): Promise<StatusModulo> {
  const { data } = await apiClient.get('/pdca/status/')
  return data
}

/** As obras do tenant. O PDCA não é dono delas — só escolhe em qual trabalhar. */
export async function listarObras(): Promise<Obra[]> {
  const { data } = await apiClient.get('/obras/')
  return lista<Obra>(data)
}

/** O cockpit — as três leituras que atravessam.
 *
 *  Nenhuma delas é recurso de router: a carteira cruza obras, `hoje/` junta
 *  cinco assuntos de uma obra e `busca/` varre sete tabelas. Cada uma vem com
 *  `sem_permissao` no lugar do que a pessoa não pode ver — a tela mostra o
 *  cadeado com o motivo, nunca esconde em silêncio. */
export const cockpit = {
  /** B1 — as obras lado a lado, com o teto declarado na resposta. */
  async carteira(obras?: number[]): Promise<PayloadCarteira> {
    const { data } = await apiClient.get('/pdca/carteira/', {
      params: obras?.length ? { obras: obras.join(',') } : undefined,
    })
    return data
  },
  /** B2 + B6 — fila, pulso e o que mudou **numa leitura só**: em chamadas
   *  separadas a tela esperava três vezes e cada número chegava com um
   *  recorte de período diferente do vizinho. */
  async hoje(obraId: number, params: Params = {}): Promise<PayloadHoje> {
    const { data } = await apiClient.get('/pdca/hoje/', {
      params: { obra: obraId, ...params },
    })
    return data
  },
  /** B4 — a busca única sobre as sete espécies, sem acento nas duas pontas. */
  async busca(termo: string, obraId?: number): Promise<PayloadBusca> {
    const { data } = await apiClient.get('/pdca/busca/', {
      params: { q: termo, ...(obraId ? { obra: obraId } : {}) },
    })
    return data
  },
  /** B5 — o que está no meu nome, na semana corrente.
   *
   *  `como` troca o nome procurado: o escritório escreve o rótulo que usa no
   *  quadro ("Mestre Antônio"), que nem sempre é o nome do login. Sem essa
   *  saída, quem tem o cadastro divergente veria a frente vazia para sempre. */
  async minhasFrentes(
    { como, obraId }: { como?: string; obraId?: number } = {},
  ): Promise<PayloadMinhasFrentes> {
    const { data } = await apiClient.get('/pdca/minhas-frentes/', {
      params: {
        ...(como ? { como } : {}),
        ...(obraId ? { obra: obraId } : {}),
      },
    })
    return data
  },
}

/** O *constraint log* — o que trava a obra, e o ato de destravar. */
export const restricoes = {
  async listar(obraId: number, status = 'aberta'): Promise<Restricao[]> {
    const { data } = await apiClient.get('/pdca/restricoes/', {
      params: {
        'atividade__cronograma__obra': obraId,
        ...(status ? { status } : {}),
        page_size: 300,
        ordering: 'prazo',
      },
    })
    return lista<Restricao>(data)
  },
  async criar(corpo: Partial<Restricao>): Promise<Restricao> {
    const { data } = await apiClient.post('/pdca/restricoes/', corpo)
    return data
  },
  /** Exige dizer **como** — restrição que some sem explicação deixa a reunião
   *  seguinte sem saber se ela foi resolvida ou esquecida. */
  async remover(id: number, nota: string): Promise<Restricao> {
    const { data } = await apiClient.post(`/pdca/restricoes/${id}/remover/`, { nota })
    return data
  },
  /** O seam do SCM, vivo: restrição de material vira demanda de compra. */
  async gerarDemanda(
    id: number, corpo: { quantidade?: string | null; unidade?: string },
  ): Promise<{ demanda: number; restricao: Restricao }> {
    const { data } = await apiClient.post(
      `/pdca/restricoes/${id}/gerar-demanda/`, corpo,
    )
    return data
  },
}

/** O catálogo de causas — de fábrica e extensível pelo tenant. */
export const causas = {
  async listar(): Promise<CausaNaoCumprimento[]> {
    const { data } = await apiClient.get('/pdca/causas/', {
      params: { ativo: true, page_size: 200, ordering: 'codigo' },
    })
    return lista<CausaNaoCumprimento>(data)
  },
  async criar(corpo: Partial<CausaNaoCumprimento>): Promise<CausaNaoCumprimento> {
    const { data } = await apiClient.post('/pdca/causas/', corpo)
    return data
  },
}

/** A semana — abre, compromete, julga, encerra. */
export const programacoes = {
  async daSemana(obraId: number, inicio: string): Promise<ProgramacaoSemanal | undefined> {
    const { data } = await apiClient.get('/pdca/programacoes/', {
      params: { obra: obraId, semana_inicio: inicio },
    })
    return lista<ProgramacaoSemanal>(data)[0]
  },
  /** Idempotente por semana: quem já existe volta como está. O servidor ancora
   *  na segunda-feira — deixar o navegador calcular produziria uma semana
   *  diferente por fuso. */
  async abrir(obraId: number, semana: string): Promise<ProgramacaoSemanal> {
    const { data } = await apiClient.post('/pdca/programacoes/abrir/', {
      obra: obraId, semana,
    })
    return data
  },
  async candidatos(id: number): Promise<CandidatoDaSemana[]> {
    const { data } = await apiClient.get(`/pdca/programacoes/${id}/candidatos/`)
    return data
  },
  async comprometer(id: number): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/programacoes/${id}/comprometer/`)
    return data
  },
  async julgar(id: number, julgamentos: JulgamentoDeItem[]): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/programacoes/${id}/julgar/`, {
      julgamentos,
    })
    return data
  },
  async encerrar(
    id: number, corpo: { motivo?: string; arrastar?: boolean } = {},
  ): Promise<ResumoDoPpc> {
    const { data } = await apiClient.post(`/pdca/programacoes/${id}/encerrar/`, corpo)
    return data
  },
  async arrastar(id: number): Promise<ResultadoDoArrasto> {
    const { data } = await apiClient.post(`/pdca/programacoes/${id}/arrastar/`)
    return data
  },
  async reabrir(id: number, motivo: string): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/programacoes/${id}/reabrir/`, { motivo })
    return data
  },
  async anotar(id: number, nota: string): Promise<ProgramacaoSemanal> {
    const { data } = await apiClient.patch(`/pdca/programacoes/${id}/`, { nota })
    return data
  },
  /** A série histórica — só semanas encerradas. Um PPC isolado não diz nada. */
  async ppc(obraId: number): Promise<{ obra: number; serie: PontoDaSerie[] }> {
    const { data } = await apiClient.get('/pdca/programacoes/ppc/', {
      params: { obra: obraId },
    })
    return data
  },
  /** O "Act" — por que os compromissos desta obra não saem. */
  async ranking(obraId: number, params: Params = {}): Promise<RankingDeCausas> {
    const { data } = await apiClient.get('/pdca/programacoes/causas/', {
      params: { obra: obraId, ...params },
    })
    return data
  },
}

export interface PontoDaSerie {
  programacao: number
  semana_inicio: string
  comprometidos: number
  cumpridos: number
  ppc: string
  peso_bases: string[]
  vezes_reaberta: number
  encerrada_antes_do_fim: boolean
}

export const itensProgramacao = {
  async listar(programacaoId: number): Promise<ItemProgramacao[]> {
    const { data } = await apiClient.get('/pdca/itens-programacao/', {
      params: { programacao: programacaoId, page_size: 300, ordering: 'ordem' },
    })
    return lista<ItemProgramacao>(data)
  },
  async criar(corpo: Partial<ItemProgramacao>): Promise<ItemProgramacao> {
    const { data } = await apiClient.post('/pdca/itens-programacao/', corpo)
    return data
  },
  async atualizar(
    id: number, corpo: Partial<ItemProgramacao>,
  ): Promise<ItemProgramacao> {
    const { data } = await apiClient.patch(`/pdca/itens-programacao/${id}/`, corpo)
    return data
  },
  async remover(id: number): Promise<void> {
    await apiClient.delete(`/pdca/itens-programacao/${id}/`)
  },
}

/** O livro-razão do avanço — **nasce e estorna; não edita nem apaga**. É o que
 *  o campo escreve, e de onde a medição e o pulso saem. */
export const apontamentos = {
  /** **A foto obriga `FormData`**, e por isso a escrita monta o corpo em vez de
   *  mandar o objeto: um JSON não transporta arquivo. Sem foto o corpo sai do
   *  mesmo jeito — um só caminho de escrita evita que o do canteiro e o do
   *  escritório divirjam no dia em que um deles mudar. */
  async criar(corpo: {
    atividade: number
    data: string
    percentual: string
    local?: number | null
    observacao?: string
    origem?: string
    foto?: File | null
  }): Promise<ApontamentoAvanco> {
    const form = new FormData()
    form.append('atividade', String(corpo.atividade))
    form.append('data', corpo.data)
    form.append('percentual', corpo.percentual)
    if (corpo.local != null) form.append('local', String(corpo.local))
    if (corpo.observacao) form.append('observacao', corpo.observacao)
    form.append('origem', corpo.origem ?? 'web')
    if (corpo.foto) form.append('foto', corpo.foto)
    const { data } = await apiClient.post('/pdca/apontamentos/', form)
    return data
  },
  async doItem(
    atividade: number, de: string, ate: string,
  ): Promise<ApontamentoAvanco[]> {
    const { data } = await apiClient.get('/pdca/apontamentos/', {
      params: { atividade, de, ate, page_size: 100, ordering: '-data' },
    })
    return lista<ApontamentoAvanco>(data)
  },
  /** Corrigir é estornar: a linha errada continua legível e a soma dá certo. */
  async estornar(id: number, motivo: string): Promise<ApontamentoAvanco> {
    const { data } = await apiClient.post(`/pdca/apontamentos/${id}/estornar/`, {
      motivo,
    })
    return data
  },
}

export const cronogramas = {
  async listar(params: Params = {}): Promise<Cronograma[]> {
    const { data } = await apiClient.get('/pdca/cronogramas/', { params })
    return lista<Cronograma>(data)
  },
  async obter(id: number): Promise<Cronograma> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${id}/`)
    return data
  },
  async criar(corpo: Partial<Cronograma>): Promise<Cronograma> {
    const { data } = await apiClient.post('/pdca/cronogramas/', corpo)
    return data
  },
  /** Árvore, setas, linha de base, cobertura e avanço numa chamada só. */
  async gantt(id: number): Promise<PayloadGantt> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${id}/gantt/`)
    return data
  },
  async calcular(id: number): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/cronogramas/${id}/calcular/`)
    return data
  },
  async publicar(id: number): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/cronogramas/${id}/publicar/`)
    return data
  },
  async replanejar(id: number, motivo: string): Promise<Cronograma> {
    const { data } = await apiClient.post(`/pdca/cronogramas/${id}/replanejar/`, { motivo })
    return data
  },
  async linhaDeBalanco(id: number): Promise<PayloadBalanco> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${id}/linha-de-balanco/`)
    return data
  },
  async curvaS(id: number, granularidade = 'semana'): Promise<unknown> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${id}/curva-s/`, {
      params: { granularidade },
    })
    return data
  },
}

export const atividades = {
  async atualizar(id: number, corpo: Partial<Atividade>): Promise<Atividade> {
    const { data } = await apiClient.patch(`/pdca/atividades/${id}/`, corpo)
    return data
  },
  async criar(corpo: Partial<Atividade>): Promise<Atividade> {
    const { data } = await apiClient.post('/pdca/atividades/', corpo)
    return data
  },
  async remover(id: number): Promise<void> {
    await apiClient.delete(`/pdca/atividades/${id}/`)
  },
}

export const locais = {
  async listar(obraId: number): Promise<LocalObra[]> {
    const { data } = await apiClient.get('/pdca/locais/', {
      params: { obra: obraId, page_size: 500 },
    })
    return lista<LocalObra>(data)
  },
}

export const calendarios = {
  /** `?para_obra=` traz os da obra **mais** os da empresa, na ordem de precedência
   *  do cálculo — o filtro exato `?obra=` escondia os da empresa (D118). */
  async listar(obraId: number): Promise<CalendarioTrabalho[]> {
    const { data } = await apiClient.get('/pdca/calendarios/', {
      params: { para_obra: obraId },
    })
    return lista<CalendarioTrabalho>(data)
  },
}
