import apiClient from '@/api/apiClient'
import type { Obra } from '@/types'
import type {
  AditivoContrato, FatorDeReajuste, AnexoOcorrencia, ApontamentoAvanco, Atividade, AvancoFisicoFinanceiro,
  CalendarioTrabalho, CandidatoDaSemana, CausaNaoCumprimento, EquipeObra,
  ClassificacaoOcorrencia, ConclusaoDaVerificacao, ContextoDeMedicao,
  ContratoObra, Cronograma, DialogoSeguranca, DominioVerificacao, EpiVencido, FontesDaPlanilha, LinhaParaPlanilha,
  EspecieAnexo, GravidadeNc, ItemContrato, ItemModeloVerificacao,
  ItemProgramacao, ItemVerificacao, JulgamentoDeItem, LiberacaoRetencao,
  LocalObra, Medicao, ModeloVerificacao, NaoConformidade, Ocorrencia,
  OcorrenciaResumo, PayloadBalanco, PayloadBusca, PayloadCarteira,
  PayloadGantt, PayloadHoje, PayloadMinhasFrentes, PayloadPostoMedicao,
  PayloadPostoQualidade, PayloadPostoSeguranca, PeriodoSugerido, PlanoAcao,
  ProgramacaoSemanal, PropostaDeMedicao, RankingDeCausas, Restricao,
  ResultadoDoArrasto, ResultadoItem, ResumoDoPpc, RetencaoDoContrato,
  FichaDoContrato, LinhaDeAditivoEntrada, SaldoDoContrato, StatusModulo, TipoCat, TipoOcorrencia, TipoPlanoAcao,
  Verificacao,
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
  /** Uma trava, como está agora — para conferir antes de destravar. */
  async obter(id: number): Promise<Restricao> {
    const { data } = await apiClient.get(`/pdca/restricoes/${id}/`)
    return data
  },
  /** Abertas e resolvidas de uma atividade: a resolvida fica na lista, com a
   *  nota, e pode voltar a ser aberta. */
  async daAtividade(atividadeId: number): Promise<Restricao[]> {
    const { data } = await apiClient.get('/pdca/restricoes/', {
      params: { atividade: atividadeId, page_size: 300, ordering: 'status' },
    })
    return lista<Restricao>(data).filter((r) => r.status !== 'cancelada')
  },
  /** A trava que voltou — resolvida → aberta, carimbada no histórico. */
  async reabrir(id: number): Promise<Restricao> {
    const { data } = await apiClient.post(`/pdca/restricoes/${id}/reabrir/`, {})
    return data
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

/** As equipes da obra — a composição que assume compromissos na semana. */
export const equipes = {
  async daObra(obraId: number): Promise<EquipeObra[]> {
    const { data } = await apiClient.get('/pdca/equipes/', {
      params: { obra: obraId, ativa: true, page_size: 200, ordering: 'nome' },
    })
    return lista<EquipeObra>(data)
  },
  async criar(corpo: Pick<EquipeObra, 'obra' | 'nome' | 'funcionarios' | 'fornecedores'>): Promise<EquipeObra> {
    const { data } = await apiClient.post('/pdca/equipes/', corpo)
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
    id: number, corpo: { motivo?: string; arrastar?: boolean; aceitar_sem_causa?: boolean } = {},
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
  /** O compromisso pede o material da semana ao almoxarifado (requisição em rascunho). */
  async pedirMaterial(id: number): Promise<{ requisicao: number; status: string; itens: number }> {
    const { data } = await apiClient.post(`/pdca/itens-programacao/${id}/pedir-material/`, {})
    return data
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
  async descartar(id: number): Promise<void> {
    await apiClient.delete(`/pdca/cronogramas/${id}/`)
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
  /** Previsto × realizado por etapa e a curva S mensal (o avanço é do PDCA). */
  async avancoFisicoFinanceiro(id: number): Promise<AvancoFisicoFinanceiro> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${id}/avanco-fisico-financeiro/`)
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
  async criar(corpo: Partial<LocalObra>): Promise<LocalObra> {
    const { data } = await apiClient.post('/pdca/locais/', corpo)
    return data
  },
  async remover(id: number): Promise<void> {
    await apiClient.delete(`/pdca/locais/${id}/`)
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

/* --------------------------------------------------------------------------
 * MEDIÇÃO — o contrato, o boletim e o dinheiro (F.4)
 * ------------------------------------------------------------------------ */

/** B3 — a carteira de contratos **com saldo** e a fila do dinheiro, numa
 *  leitura só.
 *
 *  A separada `contratos/{id}/saldo/` continua existindo e é a do documento
 *  aberto; esta é a da tela que abre. Em chamadas separadas a carteira pediria
 *  um saldo **por contrato** — numa obra com doze empreiteiros, treze idas ao
 *  servidor para desenhar doze linhas, cada resposta de um instante diferente. */
export const posto = {
  async medicao(obraId: number): Promise<PayloadPostoMedicao> {
    const { data } = await apiClient.get('/pdca/medicao/', {
      params: { obra: obraId },
    })
    return data
  },
  /** B8 — a fila do laço aberto e o painel de conformidade, numa leitura. */
  async qualidade(obraId: number): Promise<PayloadPostoQualidade> {
    const { data } = await apiClient.get('/pdca/qualidade/', {
      params: { obra: obraId },
    })
    return data
  },
  /** B9 — a fila da SSMA, os indicadores e as frentes interditadas. */
  async seguranca(obraId: number): Promise<PayloadPostoSeguranca> {
    const { data } = await apiClient.get('/pdca/seguranca/', {
      params: { obra: obraId },
    })
    return data
  },
}

/* --------------------------------------------------------------------------
 * QUALIDADE — a ficha, o defeito e o laço que o fecha (F.5)
 * ------------------------------------------------------------------------ */

/** Monta `FormData` quando há arquivo e JSON quando não há — o `PATCH` da
 *  resposta leva a foto **na mesma requisição**, que é o que evita o segundo
 *  gesto no canteiro. */
function corpoComArquivo(
  campos: Record<string, unknown>, arquivo?: { campo: string; valor: File | null },
): FormData | Record<string, unknown> {
  if (!arquivo?.valor) return campos
  const form = new FormData()
  for (const [chave, valor] of Object.entries(campos)) {
    if (valor === undefined || valor === null) continue
    form.append(chave, String(valor))
  }
  form.append(arquivo.campo, arquivo.valor)
  return form
}

export const modelos = {
  async listar(params: Params = {}): Promise<ModeloVerificacao[]> {
    const { data } = await apiClient.get('/pdca/modelos-verificacao/', {
      params: { page_size: 200, ordering: 'codigo', ...params },
    })
    return lista<ModeloVerificacao>(data)
  },
  async obter(id: number): Promise<ModeloVerificacao> {
    const { data } = await apiClient.get(`/pdca/modelos-verificacao/${id}/`)
    return data
  },
  async criar(corpo: {
    codigo: string; nome: string; dominio: DominioVerificacao; descricao?: string
  }): Promise<ModeloVerificacao> {
    const { data } = await apiClient.post('/pdca/modelos-verificacao/', corpo)
    return data
  },
  async atualizar(
    id: number, corpo: Partial<Pick<ModeloVerificacao, 'nome' | 'descricao' | 'ativo'>>,
  ): Promise<ModeloVerificacao> {
    const { data } = await apiClient.patch(`/pdca/modelos-verificacao/${id}/`, corpo)
    return data
  },
  async excluir(id: number): Promise<void> {
    await apiClient.delete(`/pdca/modelos-verificacao/${id}/`)
  },
  async duplicar(id: number, codigo: string, nome?: string): Promise<ModeloVerificacao> {
    const { data } = await apiClient.post(
      `/pdca/modelos-verificacao/${id}/duplicar/`, { codigo, nome },
    )
    return data
  },
  async criarItem(corpo: {
    modelo: number; ordem: number; texto: string; criterio?: string
    obrigatorio?: boolean; exige_foto?: boolean
  }): Promise<ItemModeloVerificacao> {
    const { data } = await apiClient.post('/pdca/itens-modelo-verificacao/', corpo)
    return data
  },
  async atualizarItem(
    id: number, corpo: Partial<Omit<ItemModeloVerificacao, 'item_modelo_id' | 'modelo'>>,
  ): Promise<ItemModeloVerificacao> {
    const { data } = await apiClient.patch(`/pdca/itens-modelo-verificacao/${id}/`, corpo)
    return data
  },
  async excluirItem(id: number): Promise<void> {
    await apiClient.delete(`/pdca/itens-modelo-verificacao/${id}/`)
  },
}

export const verificacoes = {
  async daObra(obraId: number, params: Params = {}): Promise<Verificacao[]> {
    const { data } = await apiClient.get('/pdca/verificacoes/', {
      params: { obra: obraId, page_size: 100, ordering: '-data', ...params },
    })
    return lista<Verificacao>(data)
  },
  async obter(id: number): Promise<Verificacao> {
    const { data } = await apiClient.get(`/pdca/verificacoes/${id}/`)
    return data
  },
  async itens(id: number): Promise<ItemVerificacao[]> {
    const { data } = await apiClient.get('/pdca/itens-verificacao/', {
      params: { verificacao: id, page_size: 500, ordering: 'ordem' },
    })
    return lista<ItemVerificacao>(data)
  },
  /** A ficha **não** se cria por `POST` cru: nasce copiando o modelo para
   *  dentro dela, que é o congelamento da pergunta. */
  async aplicar(corpo: {
    modelo: number; obra: number; data: string
    local?: number | null; atividade?: number | null; inspetor?: string
  }): Promise<Verificacao> {
    const { data } = await apiClient.post('/pdca/verificacoes/aplicar/', corpo)
    return data
  },
  async responder(
    itemId: number,
    corpo: {
      resultado: ResultadoItem; observacao?: string; gravidade?: GravidadeNc | null
    },
    foto?: File | null,
  ): Promise<ItemVerificacao> {
    const { data } = await apiClient.patch(
      `/pdca/itens-verificacao/${itemId}/`,
      corpoComArquivo(corpo, { campo: 'foto', valor: foto ?? null }),
    )
    return data
  },
  async concluir(id: number): Promise<ConclusaoDaVerificacao> {
    const { data } = await apiClient.post(`/pdca/verificacoes/${id}/concluir/`, {})
    return data
  },
  /** Uma NC por reprovado, cada uma com a gravidade do seu item — sem corpo. */
  async abrirNcs(id: number): Promise<{ abertas: number; ncs: number[] }> {
    const { data } = await apiClient.post(`/pdca/verificacoes/${id}/abrir-ncs/`, {})
    return data
  },
}

export const ncs = {
  async daObra(obraId: number, params: Params = {}): Promise<NaoConformidade[]> {
    const { data } = await apiClient.get('/pdca/ncs/', {
      params: { obra: obraId, page_size: 200, ordering: '-aberta_em', ...params },
    })
    return lista<NaoConformidade>(data)
  },
  async obter(id: number): Promise<NaoConformidade> {
    const { data } = await apiClient.get(`/pdca/ncs/${id}/`)
    return data
  },
  async abrir(
    corpo: {
      obra: number; descricao: string; gravidade: GravidadeNc
      local?: number | null; atividade?: number | null
    },
    foto?: File | null,
  ): Promise<NaoConformidade> {
    const { data } = await apiClient.post(
      '/pdca/ncs/', corpoComArquivo(corpo, { campo: 'foto', valor: foto ?? null }),
    )
    return data
  },
  async eficacia(
    id: number, corpo: { data: string; eficaz: boolean; evidencia: string },
  ): Promise<{ nc: NaoConformidade }> {
    const { data } = await apiClient.post(`/pdca/ncs/${id}/eficacia/`, corpo)
    return data
  },
  async encerrar(id: number, nota: string): Promise<NaoConformidade> {
    const { data } = await apiClient.post(`/pdca/ncs/${id}/encerrar/`, { nota })
    return data
  },
  async cancelar(id: number, motivo: string): Promise<NaoConformidade> {
    const { data } = await apiClient.post(`/pdca/ncs/${id}/cancelar/`, { motivo })
    return data
  },
  async gerarRestricao(
    id: number, corpo: { prazo?: string | null; responsavel?: string },
  ): Promise<{ restricao: number; nc: NaoConformidade }> {
    const { data } = await apiClient.post(`/pdca/ncs/${id}/gerar-restricao/`, corpo)
    return data
  },
}

export const planosAcao = {
  async criar(corpo: {
    nao_conformidade: number; tipo: TipoPlanoAcao; o_que: string
    por_que?: string; onde?: string; quando?: string | null; quem?: string
    como?: string; quanto?: string
  }): Promise<PlanoAcao> {
    const { data } = await apiClient.post('/pdca/planos-acao/', corpo)
    return data
  },
  async concluir(id: number): Promise<PlanoAcao> {
    const { data } = await apiClient.post(`/pdca/planos-acao/${id}/concluir/`, {})
    return data
  },
}

/* --------------------------------------------------------------------------
 * SEGURANÇA — o diálogo antes do turno e o fato que ninguém queria (F.5)
 * ------------------------------------------------------------------------ */

export const dds = {
  async daObra(obraId: number, params: Params = {}): Promise<DialogoSeguranca[]> {
    const { data } = await apiClient.get('/pdca/dds/', {
      params: { obra: obraId, page_size: 100, ordering: '-data', ...params },
    })
    return lista<DialogoSeguranca>(data)
  },
  async obter(id: number): Promise<DialogoSeguranca> {
    const { data } = await apiClient.get(`/pdca/dds/${id}/`)
    return data
  },
  async abrir(corpo: {
    obra: number; data: string; tema: string; assunto?: string
    duracao_min?: number | null; responsavel_nome?: string
    local?: number | null; atividade?: number | null
  }): Promise<DialogoSeguranca> {
    const { data } = await apiClient.post('/pdca/dds/', corpo)
    return data
  },
  /** A lista chega **em lote** — metade gravada sem ninguém saber onde parou
   *  seria pior que nenhuma. */
  async presenca(
    id: number, participantes: { nome: string; presente?: boolean; assinou?: boolean }[],
  ): Promise<{ registrados: number; total: number; dds: DialogoSeguranca }> {
    const { data } = await apiClient.post(`/pdca/dds/${id}/presenca/`, { participantes })
    return data
  },
  async encerrar(
    id: number, publicar_no_diario: boolean,
  ): Promise<{ presentes: number; publicado_no_diario: boolean; dds: DialogoSeguranca }> {
    const { data } = await apiClient.post(`/pdca/dds/${id}/encerrar/`, { publicar_no_diario })
    return data
  },
}

export const ocorrencias = {
  async daObra(obraId: number, params: Params = {}): Promise<OcorrenciaResumo[]> {
    const { data } = await apiClient.get('/pdca/ocorrencias/', {
      params: { obra: obraId, page_size: 200, ordering: '-ocorrido_em', ...params },
    })
    return lista<OcorrenciaResumo>(data)
  },
  async obter(id: number): Promise<Ocorrencia> {
    const { data } = await apiClient.get(`/pdca/ocorrencias/${id}/`)
    return data
  },
  /** A porta larga: tipo, hora e o que aconteceu. Todo campo a mais aqui é
   *  subnotificação depois. */
  async registrar(corpo: {
    obra: number; tipo: TipoOcorrencia; ocorrido_em: string; descricao: string
    local?: number | null; atividade?: number | null
    acidentado_nome?: string; agente_causador?: string
  }): Promise<Ocorrencia> {
    const { data } = await apiClient.post('/pdca/ocorrencias/', corpo)
    return data
  },
  async classificar(id: number, corpo: {
    classificacao: Exclude<ClassificacaoOcorrencia, 'pendente'>
    dias_perdidos?: number | null; dias_debitados?: number | null
  }): Promise<Ocorrencia> {
    const { data } = await apiClient.post(`/pdca/ocorrencias/${id}/classificar/`, corpo)
    return data
  },
  async cat(id: number, corpo: {
    tipo: TipoCat; emitida_em: string; protocolo?: string
  }): Promise<{ dentro_do_prazo: boolean; ocorrencia: Ocorrencia }> {
    const { data } = await apiClient.post(`/pdca/ocorrencias/${id}/cat/`, corpo)
    return data
  },
  async interditar(id: number, prazo?: string | null): Promise<{ restricao: number }> {
    const { data } = await apiClient.post(`/pdca/ocorrencias/${id}/interditar/`, { prazo })
    return data
  },
  async investigar(id: number): Promise<{ nc: number }> {
    const { data } = await apiClient.post(`/pdca/ocorrencias/${id}/investigar/`, {})
    return data
  },
  async encerrar(id: number, nota: string): Promise<Ocorrencia> {
    const { data } = await apiClient.post(`/pdca/ocorrencias/${id}/encerrar/`, { nota })
    return data
  },
  async anexar(corpo: {
    ocorrencia: number; especie: EspecieAnexo; descricao?: string; arquivo: File
  }): Promise<AnexoOcorrencia> {
    const form = new FormData()
    form.append('ocorrencia', String(corpo.ocorrencia))
    form.append('especie', corpo.especie)
    if (corpo.descricao) form.append('descricao', corpo.descricao)
    form.append('arquivo', corpo.arquivo)
    const { data } = await apiClient.post('/pdca/anexos-ocorrencia/', form)
    return data
  },
  /** O seam com o SIL — cobra `sil.epi.view`, que é permissão do outro
   *  módulo; a tela só chama quem a tem. */
  async epiVencido(obraId: number): Promise<EpiVencido> {
    const { data } = await apiClient.get('/pdca/ocorrencias/epi-vencido/', {
      params: { obra: obraId },
    })
    return data
  },
}

export const contratos = {
  async obter(id: number): Promise<ContratoObra> {
    const { data } = await apiClient.get(`/pdca/contratos/${id}/`)
    return data
  },
  /** O contrato é `ModelViewSet` — montar o contrato é um ato só, e por isso
   *  ele não tem a escada de verbos da medição. A segregação que importa está
   *  do outro lado: quem monta o contrato pode não ser quem ateste. */
  async criar(corpo: Record<string, unknown>): Promise<ContratoObra> {
    // As parcelas da fórmula de reajuste são filhas do contrato: nascem depois
    // dele. Falhar numa não desfaz o contrato (ele já existe e é editável) —
    // o erro sobe e a tela diz qual parcela faltou.
    const { parcelas_reajuste: parcelas, ...contrato } = corpo as {
      parcelas_reajuste?: { indice: number; peso: string; rotulo: string }[]
    } & Record<string, unknown>
    const { data } = await apiClient.post('/pdca/contratos/', contrato)
    for (const p of parcelas ?? []) {
      await apiClient.post('/pdca/parcelas-reajuste/', { contrato: data.contrato_id, ...p })
    }
    return data
  },
  /** O fator da fórmula numa data, com a memória de cada parcela. */
  async fatorDeReajuste(id: number, data?: string): Promise<FatorDeReajuste> {
    const { data: corpo } = await apiClient.get(`/pdca/contratos/${id}/fator-de-reajuste/`, {
      params: data ? { data } : undefined,
    })
    return corpo
  },
  /** O contrato inteiro numa leitura: financeiro do ERP, itens e linha do tempo. */
  async ficha(id: number): Promise<FichaDoContrato> {
    const { data } = await apiClient.get(`/pdca/contratos/${id}/ficha/`)
    return data
  },
  async saldo(id: number): Promise<SaldoDoContrato> {
    const { data } = await apiClient.get(`/pdca/contratos/${id}/saldo/`)
    return data
  },
  /** Rascunho → vigente (achado do dono: "fica em rascunho eternamente"). */
  async ativar(id: number): Promise<ContratoObra> {
    const { data } = await apiClient.post(`/pdca/contratos/${id}/ativar/`)
    return data
  },
  /** Itens do orçamento e atividades do plano, prontos para a planilha. */
  async fontesDaPlanilha(id: number): Promise<FontesDaPlanilha> {
    const { data } = await apiClient.get(`/pdca/contratos/${id}/fontes-da-planilha/`)
    return data
  },
  /** Várias linhas de uma vez — do orçamento, do plano ou coladas do Excel. */
  async incluirNaPlanilha(id: number, linhas: LinhaParaPlanilha[]): Promise<ItemContrato[]> {
    const { data } = await apiClient.post(`/pdca/contratos/${id}/incluir-na-planilha/`, { linhas })
    return data
  },
  async periodoSugerido(id: number): Promise<PeriodoSugerido> {
    const { data } = await apiClient.get(`/pdca/contratos/${id}/periodo-sugerido/`)
    return data
  },
  /** A prévia: o que se mediria neste período, **sem gravar nada**.
   *
   *  Separada de `abrir` porque o gesto do gestor é olhar antes de decidir —
   *  abrir a medição só para ver a proposta encheria o contrato de rascunhos
   *  que ele teria de apagar depois. */
  async propostaDeMedicao(
    id: number, inicio: string, fim: string,
  ): Promise<PropostaDeMedicao> {
    const { data } = await apiClient.get(
      `/pdca/contratos/${id}/proposta-de-medicao/`, { params: { inicio, fim } },
    )
    return data
  },
  async retencao(id: number): Promise<RetencaoDoContrato> {
    const { data } = await apiClient.get(`/pdca/contratos/${id}/retencao/`)
    return data
  },
  /** Põe na escada o pedido de devolver o retido — **escada própria**, não a
   *  da medição: quem ateste medição confere serviço executado; quem libera
   *  caução confere condição contratual cumprida. */
  async liberarRetencao(
    id: number,
    corpo: { valor: string; data: string; condicao_atendida: string },
  ): Promise<{ estado: string; liberacao: LiberacaoRetencao }> {
    const { data } = await apiClient.post(
      `/pdca/contratos/${id}/liberar-retencao/`, corpo,
    )
    return data
  },
}

export const itensDeContrato = {
  async listar(contratoId: number): Promise<ItemContrato[]> {
    const { data } = await apiClient.get('/pdca/itens-contrato/', {
      params: { contrato: contratoId, page_size: 500, ordering: 'ordem' },
    })
    return lista<ItemContrato>(data)
  },
  async criar(corpo: Partial<ItemContrato>): Promise<ItemContrato> {
    const { data } = await apiClient.post('/pdca/itens-contrato/', corpo)
    return data
  },
  async atualizar(
    id: number, corpo: Partial<ItemContrato>,
  ): Promise<ItemContrato> {
    const { data } = await apiClient.patch(`/pdca/itens-contrato/${id}/`, corpo)
    return data
  },
  async remover(id: number): Promise<void> {
    await apiClient.delete(`/pdca/itens-contrato/${id}/`)
  },
}

/** O boletim — **abre, submete, retifica; não se edita por PUT**.
 *
 *  O documento tem ciclo de vida, e um `PATCH` genérico publicaria um caminho
 *  que atravessa o congelamento. É a mesma forma do apontamento de avanço. */
export const medicoes = {
  /** A lista do contrato pede `?resumo=1`: quem lista quer o cabeçalho, e o
   *  serializer completo mandava todos os itens de todas as medições. */
  async doContrato(contratoId: number): Promise<Medicao[]> {
    const { data } = await apiClient.get('/pdca/medicoes/', {
      params: {
        contrato: contratoId, resumo: 1, page_size: 100, ordering: '-numero',
      },
    })
    return lista<Medicao>(data)
  },
  async obter(id: number): Promise<Medicao> {
    const { data } = await apiClient.get(`/pdca/medicoes/${id}/`)
    return data
  },
  /** A grade inteira, calculada no servidor: contratado, aditivos, acumulado
   *  anterior, proposta do período, saldo e a **memória de cálculo** de cada
   *  linha. Um endpoint, uma verdade — a tela não soma nada. */
  async contexto(id: number): Promise<ContextoDeMedicao> {
    const { data } = await apiClient.get(`/pdca/medicoes/${id}/contexto/`)
    return data
  },
  async abrir(corpo: {
    contrato: number
    inicio: string
    fim: string
    linhas?: { item_contrato_id: number; quantidade: string }[]
    custo_reembolsavel?: string | null
    observacao?: string
  }): Promise<Medicao> {
    const { data } = await apiClient.post('/pdca/medicoes/abrir/', corpo)
    return data
  },
  /** Reescreve a grade do rascunho — **substitui, não soma**: a grade da tela
   *  é o documento inteiro, e um endpoint que acumulasse faria dois envios
   *  acidentais dobrarem a medição. */
  async linhas(
    id: number,
    linhas: {
      item_contrato_id: number
      quantidade?: string
      quantidade_estocada?: string
      observacao?: string
    }[],
  ): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/linhas/`, {
      linhas,
    })
    return data
  },
  /** Os descontos que **não voltam** — imposto retido, amortização de
   *  adiantamento, multa. Retenção contratual não entra aqui: ela é cláusula
   *  do contrato e volta pela liberação. */
  async deducoes(
    id: number,
    deducoes: {
      tipo: string
      descricao?: string
      base_calculo?: string | null
      percentual?: string | null
      valor?: string | null
    }[],
  ): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/deducoes/`, {
      deducoes,
    })
    return data
  },
  /** Custo reembolsável e observação — os dois campos do documento que não são
   *  a grade. No regime de administração **não há linha nenhuma**: o que se
   *  mede é o custo, e sem esta porta o regime inteiro ficava sem tela. */
  async cabecalho(
    id: number, corpo: { custo_reembolsavel?: string | null; observacao?: string },
  ): Promise<Medicao> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/cabecalho/`, corpo)
    return data
  },
  async submeter(
    id: number, observacao = '',
  ): Promise<{ estado: string; avisos: string[]; medicao: Medicao }> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/submeter/`, {
      observacao,
    })
    return data
  },
  /** Um degrau da escada, decidido **de dentro da tela da medição**: quem
   *  ateste está olhando a grade, e mandá-lo a outra tela para clicar em
   *  "aprovar" separaria a decisão da evidência. */
  async atestar(
    id: number, corpo: { aprovar: boolean; observacao?: string },
  ): Promise<{ estado_do_pedido: string; medicao: Medicao }> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/atestar/`, corpo)
    return data
  },
  async cancelar(id: number, motivo: string): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/cancelar/`, {
      motivo,
    })
    return data
  },
  /** Corrigir medição aprovada é abrir a que a retifica — o mesmo desenho do
   *  estorno do apontamento: a original continua legível ao lado. */
  async retificar(id: number, motivo: string): Promise<Medicao> {
    const { data } = await apiClient.post(`/pdca/medicoes/${id}/retificar/`, {
      motivo,
    })
    return data
  },
}

export interface CabecalhoDoAditivo {
  objeto: string
  justificativa: string
  data_assinatura?: string | null
  nova_data_fim?: string | null
  retencao_percentual_nova?: string | null
}

export const aditivos = {
  async doContrato(contratoId: number): Promise<AditivoContrato[]> {
    const { data } = await apiClient.get('/pdca/aditivos/', {
      params: { contrato: contratoId, page_size: 100, ordering: '-numero' },
    })
    return lista<AditivoContrato>(data)
  },
  async obter(id: number): Promise<AditivoContrato> {
    const { data } = await apiClient.get(`/pdca/aditivos/${id}/`)
    return data
  },
  async abrir(corpo: {
    contrato: number
  } & CabecalhoDoAditivo & { itens?: LinhaDeAditivoEntrada[] }): Promise<AditivoContrato> {
    const { data } = await apiClient.post('/pdca/aditivos/abrir/', corpo)
    return data
  },
  /** O cabeçalho do rascunho — só o que vier no corpo muda. */
  async cabecalho(id: number, corpo: Partial<CabecalhoDoAditivo>): Promise<AditivoContrato> {
    const { data } = await apiClient.post(`/pdca/aditivos/${id}/cabecalho/`, corpo)
    return data
  },
  /** As linhas do rascunho — substitui, não soma. */
  async itens(id: number, itens: LinhaDeAditivoEntrada[]): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/aditivos/${id}/itens/`, { itens })
    return data
  },
  async excluir(id: number): Promise<void> {
    await apiClient.delete(`/pdca/aditivos/${id}/`)
  },
  async cancelar(id: number, motivo: string): Promise<AditivoContrato> {
    const { data } = await apiClient.post(`/pdca/aditivos/${id}/cancelar/`, { motivo })
    return data
  },
  async submeter(id: number): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/aditivos/${id}/submeter/`, {})
    return data
  },
  async atestar(
    id: number, corpo: { aprovar: boolean; observacao?: string },
  ): Promise<unknown> {
    const { data } = await apiClient.post(`/pdca/aditivos/${id}/atestar/`, corpo)
    return data
  },
}

export const liberacoes = {
  async doContrato(contratoId: number): Promise<LiberacaoRetencao[]> {
    const { data } = await apiClient.get('/pdca/liberacoes/', {
      params: { contrato: contratoId, page_size: 100, ordering: '-data' },
    })
    return lista<LiberacaoRetencao>(data)
  },
}
