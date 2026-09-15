import apiClient from '@/api/apiClient'
import type {
  Apontamento, AvancoDoCronograma, CurvaS, Granularidade, LinhaDeApontamento,
  ResultadoDoApontamentoEmLote,
  Atividade, ComparacaoBase, CoberturaOrcamento, Cronograma, ObraOpt,
  AplicacaoDeModelo, Calendario, ContagemDeDiasUteis, EdicaoEmLote, EtapaOpt,
  ExcecaoCalendario, ItemOrcadoOpt, LocalOpt, OrcamentoOpt, Paginated, PayloadGantt,
  Precedencia, ResponsavelOpt, ResultadoCpm, ResultadoDaRenumeracao, ResultadoDoLote,
  StatusModulo,
  Contrato, ItemDeContrato, LiberacaoDeRetencao, Medicao, PropostaDeMedicao,
  ResultadoDaSubmissao, RetencaoDoContrato, SaldoDoContrato, TotaisDaMedicao,
  Aditivo, ContextoDeMedicao, LinhaDeAditivo, LinhaDeDeducao, LinhaParaApi,
  PeriodoSugerido, ResumoDoAditivo,
} from '../types'

type Params = Record<string, unknown>

export const getStatusModulo = async () =>
  (await apiClient.get<StatusModulo>('pdca/status/')).data

export const cronogramas = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Cronograma>>('pdca/cronogramas/', { params })).data,
  obter: async (id: number) =>
    (await apiClient.get<Cronograma>(`pdca/cronogramas/${id}/`)).data,
  criar: async (payload: Partial<Cronograma>) =>
    (await apiClient.post<Cronograma>('pdca/cronogramas/', payload)).data,
  atualizar: async (id: number, payload: Partial<Cronograma>) =>
    (await apiClient.patch<Cronograma>(`pdca/cronogramas/${id}/`, payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/cronogramas/${id}/`) },

  // O Gantt vem inteiro numa chamada: árvore, setas e linha de base juntas.
  gantt: async (id: number) =>
    (await apiClient.get<PayloadGantt>(`pdca/cronogramas/${id}/gantt/`)).data,
  calcular: async (id: number) =>
    (await apiClient.post<ResultadoCpm>(`pdca/cronogramas/${id}/calcular/`)).data,
  publicar: async (id: number) =>
    (await apiClient.post<{ cronograma: Cronograma; cpm: ResultadoCpm }>(`pdca/cronogramas/${id}/publicar/`)).data,
  replanejar: async (id: number, motivo: string) =>
    (await apiClient.post<Cronograma>(`pdca/cronogramas/${id}/replanejar/`, { motivo })).data,
  linhaDeBase: async (id: number) =>
    (await apiClient.get<ComparacaoBase>(`pdca/cronogramas/${id}/linha-de-base/`)).data,
  cobertura: async (id: number) =>
    (await apiClient.get<CoberturaOrcamento>(`pdca/cronogramas/${id}/cobertura/`)).data,

  // -- PDCA.2: o que a obra respondeu ---------------------------------------
  avanco: async (id: number) =>
    (await apiClient.get<AvancoDoCronograma>(`pdca/cronogramas/${id}/avanco/`)).data,

  /** A curva S vem **do servidor**, e não do navegador: o previsto é
   *  distribuído nos dias úteis do calendário de cada atividade (a régua com
   *  que o CPM produziu as datas) e o realizado cruza apontamento com peso —
   *  duas tabelas que o cliente não tem. */
  curvaS: async (id: number, granularidade: Granularidade = 'semana') =>
    (await apiClient.get<CurvaS>(`pdca/cronogramas/${id}/curva-s/`, {
      params: { granularidade },
    })).data,

  // -- Plano modelo (PDCA.1b) ------------------------------------------------
  // A biblioteca de padrões da empresa. Rota de coleção, e não filtro da
  // listagem: quem vai aplicar um padrão numa obra nova não quer ver as 40
  // versões de plano das obras em andamento no meio.
  modelos: async () =>
    (await apiClient.get<Paginated<Cronograma>>('pdca/cronogramas/modelos/', {
      params: { page_size: 200 },
    })).data,
  marcarModelo: async (id: number, nome: string) =>
    (await apiClient.post<Cronograma>(`pdca/cronogramas/${id}/marcar-modelo/`, { nome })).data,
  desmarcarModelo: async (id: number) =>
    (await apiClient.post<Cronograma>(`pdca/cronogramas/${id}/desmarcar-modelo/`)).data,
  aplicarModelo: async (id: number, payload: AplicacaoDeModelo) =>
    (await apiClient.post<Cronograma>(`pdca/cronogramas/${id}/aplicar-modelo/`, payload)).data,

  /** Reescreve a EAP inteira na ordem da árvore. Não passa pelo `lote/` porque
   *  fatiar quebraria a troca de códigos: o servidor faz as duas passadas numa
   *  transação só. `simular` conta sem escrever. */
  renumerarEap: async (id: number, simular = false) =>
    (await apiClient.post<ResultadoDaRenumeracao>(
      `pdca/cronogramas/${id}/renumerar-eap/`, { simular },
    )).data,

  /** Muitas células numa requisição — o gesto de colar planilha. */
  lote: async (id: number, edicoes: EdicaoEmLote[]) =>
    (await apiClient.post<ResultadoDoLote>(`pdca/cronogramas/${id}/lote/`, { edicoes })).data,
}

export const atividades = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Atividade>>('pdca/atividades/', { params })).data,
  criar: async (payload: Partial<Atividade>) =>
    (await apiClient.post<Atividade>('pdca/atividades/', payload)).data,
  atualizar: async (id: number, payload: Partial<Atividade>) =>
    (await apiClient.patch<Atividade>(`pdca/atividades/${id}/`, payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/atividades/${id}/`) },

  /** O gesto de arrastar a barra: fixa a restrição e deixa o CPM decidir. */
  reprogramar: async (id: number, payload: { nao_comecar_antes_de?: string | null; duracao_dias?: number }) =>
    (await apiClient.post<{ atividade: Atividade; cpm: ResultadoCpm }>(`pdca/atividades/${id}/reprogramar/`, payload)).data,
}

export const precedencias = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Precedencia>>('pdca/precedencias/', { params })).data,
  criar: async (payload: Partial<Precedencia>) =>
    (await apiClient.post<Precedencia>('pdca/precedencias/', payload)).data,
  atualizar: async (id: number, payload: Partial<Precedencia>) =>
    (await apiClient.patch<Precedencia>(`pdca/precedencias/${id}/`, payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/precedencias/${id}/`) },
}

export const calendarios = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Calendario>>('pdca/calendarios/', { params })).data,
  detalhar: async (id: number) =>
    (await apiClient.get<Calendario>(`pdca/calendarios/${id}/`)).data,
  criar: async (payload: Partial<Calendario>) =>
    (await apiClient.post<Calendario>('pdca/calendarios/', payload)).data,
  atualizar: async (id: number, payload: Partial<Calendario>) =>
    (await apiClient.patch<Calendario>(`pdca/calendarios/${id}/`, payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/calendarios/${id}/`) },

  /** Quantos dias úteis há entre duas datas — e **se a base de feriados está
   *  sincronizada**, que é o que impede a tela de apresentar como certo um
   *  número calculado sem os feriados do país. */
  diasUteis: async (id: number, inicio: string, fim: string) =>
    (await apiClient.get<ContagemDeDiasUteis>(`pdca/calendarios/${id}/dias-uteis/`, {
      params: { inicio, fim },
    })).data,
}

export const excecoes = {
  listar: async (calendario: number) =>
    (await apiClient.get<Paginated<ExcecaoCalendario>>('pdca/excecoes-calendario/', {
      params: { calendario, page_size: 200, ordering: 'data' },
    })).data,
  criar: async (payload: Partial<ExcecaoCalendario>) =>
    (await apiClient.post<ExcecaoCalendario>('pdca/excecoes-calendario/', payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/excecoes-calendario/${id}/`) },
}


export const obras = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<ObraOpt> | ObraOpt[]>('obras/', { params: { page_size: 200, ...params } })).data,
}

// ---------------------------------------------------------------------------
// Vínculos — o que o cronograma amarra em outros módulos
// ---------------------------------------------------------------------------
//
// Os quatro endpoints abaixo **não são do PDCA**, e é por isso que cada um pode
// responder 403 sozinho: quem planeja pode não ter o Orçamento nem o RH no
// plano. A tela trata cada 403 como "esta ponte não está contratada" — com o
// motivo na própria linha —, nunca como lista vazia, que mentiria dizendo que a
// obra não tem etapa nenhuma.

export const vinculos = {
  locais: async (obra: number) =>
    (await apiClient.get<Paginated<LocalOpt>>('pdca/locais/', {
      params: { obra, page_size: 500, ordering: 'codigo' },
    })).data,

  etapas: async (obra: number) =>
    (await apiClient.get<Paginated<EtapaOpt> | EtapaOpt[]>('etapas-obras/', {
      params: { obra, page_size: 200 },
    })).data,

  orcamentos: async (obra: number) =>
    (await apiClient.get<Paginated<OrcamentoOpt> | OrcamentoOpt[]>('orcamento/orcamentos/', {
      params: { obra, page_size: 50, ordering: '-versao' },
    })).data,

  /** Itens de um orçamento, com busca server-side sem acento (F2 da revisão:
   *  nenhum select novo carrega tabela inteira). */
  itens: async (orcamento: number, busca: string) =>
    (await apiClient.get<Paginated<ItemOrcadoOpt>>('orcamento/itens/', {
      params: { orcamento, search: busca || undefined, page_size: 40, ordering: 'codigo_eap' },
    })).data,

  responsaveis: async (busca: string) =>
    (await apiClient.get<Paginated<ResponsavelOpt> | ResponsavelOpt[]>('funcionarios/', {
      params: { search: busca || undefined, page_size: 40 },
    })).data,
}

// ---------------------------------------------------------------------------
// PDCA.2 — o avanço apontado
// ---------------------------------------------------------------------------
//
// **Não há `atualizar` nem `excluir` aqui, e a ausência é a regra.** O livro do
// avanço é append-only: a API não expõe `PATCH`/`DELETE`, e corrigir é
// `estornar` — a linha errada continua legível e a correção aponta para ela.

export const apontamentos = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Apontamento>>('pdca/apontamentos/', { params })).data,
  criar: async (payload: Partial<Apontamento>) =>
    (await apiClient.post<Apontamento>('pdca/apontamentos/', payload)).data,

  /** A correção: um apontamento de sinal contrário, com motivo obrigatório. */
  estornar: async (id: number, motivo: string) =>
    (await apiClient.post<Apontamento>(`pdca/apontamentos/${id}/estornar/`, { motivo })).data,

  /** A grade da semana — N frentes numa transação. Ou entra tudo, ou nada. */
  lote: async (cronograma: number, linhas: LinhaDeApontamento[]) =>
    (await apiClient.post<ResultadoDoApontamentoEmLote>('pdca/apontamentos/lote/', {
      cronograma, linhas,
    })).data,
}

// ---------------------------------------------------------------------------
// PDCA.3 — contrato, medição e retenção
// ---------------------------------------------------------------------------
//
// **Não há `atualizar` na medição, e a ausência é a regra** — a mesma do
// apontamento. O documento tem ciclo de vida: criar é `abrir` (que roda a
// proposta a partir do avanço), mudar a grade é `linhas` e só em rascunho,
// corrigir depois de aprovada é `retificar`. Um `PATCH` genérico publicaria um
// caminho que atravessa o congelamento.

export const contratos = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Contrato>>('pdca/contratos/', { params })).data,
  obter: async (id: number) =>
    (await apiClient.get<Contrato>(`pdca/contratos/${id}/`)).data,
  criar: async (payload: Partial<Contrato>) =>
    (await apiClient.post<Contrato>('pdca/contratos/', payload)).data,
  atualizar: async (id: number, payload: Partial<Contrato>) =>
    (await apiClient.patch<Contrato>(`pdca/contratos/${id}/`, payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/contratos/${id}/`) },

  /** Contratado × medido × saldo × retenção — derivado inteiro no servidor
   *  (§4.9). Somar isto no navegador daria duas verdades sobre dinheiro. */
  saldo: async (id: number) =>
    (await apiClient.get<SaldoDoContrato>(`pdca/contratos/${id}/saldo/`)).data,

  /** A prévia: o que se mediria neste período, **sem gravar nada**. Abrir a
   *  medição só para ver a proposta encheria o contrato de rascunhos. */
  proposta: async (id: number, inicio: string, fim: string) =>
    (await apiClient.get<PropostaDeMedicao>(
      `pdca/contratos/${id}/proposta-de-medicao/`, { params: { inicio, fim } },
    )).data,

  retencao: async (id: number) =>
    (await apiClient.get<RetencaoDoContrato>(`pdca/contratos/${id}/retencao/`)).data,

  /** De quando a **próxima** medição deveria falar — encadeada na anterior.
   *  Medição de obra é uma corrente: abrir sempre em "1º do mês → hoje"
   *  produzia sobreposição no mês medido quinzenalmente e buraco no mês em que
   *  a medição atrasou, e nenhum dos dois aparecia em lugar nenhum. */
  periodoSugerido: async (id: number) =>
    (await apiClient.get<PeriodoSugerido>(
      `pdca/contratos/${id}/periodo-sugerido/`,
    )).data,

  liberarRetencao: async (
    id: number, payload: { valor: string; data: string; condicao_atendida: string },
  ) =>
    (await apiClient.post<{ estado: string; escada: number | null; liberacao: LiberacaoDeRetencao }>(
      `pdca/contratos/${id}/liberar-retencao/`, payload,
    )).data,
}

export const itensContrato = {
  listar: async (contrato: number) =>
    (await apiClient.get<Paginated<ItemDeContrato>>('pdca/itens-contrato/', {
      params: { contrato, page_size: 500, ordering: 'ordem' },
    })).data,
  criar: async (payload: Partial<ItemDeContrato>) =>
    (await apiClient.post<ItemDeContrato>('pdca/itens-contrato/', payload)).data,
  atualizar: async (id: number, payload: Partial<ItemDeContrato>) =>
    (await apiClient.patch<ItemDeContrato>(`pdca/itens-contrato/${id}/`, payload)).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/itens-contrato/${id}/`) },
}

export const medicoes = {
  /** `resumo` corta as linhas do payload. Quem lista quer o cabeçalho; quem
   *  abre um documento pede o documento. Sem isto, a lista lateral de um
   *  contrato com 40 boletins de 300 linhas trafegava meio megabyte de JSON
   *  para escrever quarenta linhas de texto. */
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Medicao>>('pdca/medicoes/', {
      params: { resumo: 1, ...params },
    })).data,
  obter: async (id: number) =>
    (await apiClient.get<Medicao>(`pdca/medicoes/${id}/`)).data,

  /** **A grade da medição, inteira, calculada no servidor.** É o endpoint que
   *  substituiu a aritmética que a tela fazia — e que mostrava "já medido"
   *  negativo para quem abrisse a medição pelo link direto. */
  contexto: async (id: number) =>
    (await apiClient.get<ContextoDeMedicao>(`pdca/medicoes/${id}/contexto/`)).data,

  /** Os campos do documento que não são a grade. No regime de administração
   *  **é** a medição: não há linha nenhuma, o que se mede é o custo. */
  cabecalho: async (
    id: number, payload: { custo_reembolsavel?: string | null; observacao?: string },
  ) => (await apiClient.post<Medicao>(`pdca/medicoes/${id}/cabecalho/`, payload)).data,

  /** Substitui as deduções — o que sai do bruto e **não volta** (imposto,
   *  amortização, multa). A retenção contratual não entra aqui: ela volta pela
   *  `LiberacaoRetencao`. */
  deducoes: async (id: number, deducoes: LinhaDeDeducao[]) =>
    (await apiClient.post<{ deducoes: number; totais: TotaisDaMedicao }>(
      `pdca/medicoes/${id}/deducoes/`, { deducoes },
    )).data,

  abrir: async (payload: {
    contrato: number; inicio: string; fim: string
    linhas?: LinhaParaApi[]
    custo_reembolsavel?: string | null
    observacao?: string
  }) => (await apiClient.post<Medicao>('pdca/medicoes/abrir/', payload)).data,

  /** **Substitui, não soma.** A grade da tela é o documento inteiro; um
   *  endpoint que acumulasse faria dois envios acidentais dobrarem a medição. */
  linhas: async (id: number, linhas: LinhaParaApi[]) =>
    (await apiClient.post<{ linhas: number; totais: TotaisDaMedicao }>(
      `pdca/medicoes/${id}/linhas/`, { linhas },
    )).data,

  submeter: async (id: number, observacao = '') =>
    (await apiClient.post<ResultadoDaSubmissao>(
      `pdca/medicoes/${id}/submeter/`, { observacao },
    )).data,

  /** Um degrau da escada, decidido de dentro da tela da medição — quem ateste
   *  está olhando a grade. Quem decide de verdade é o motor do `nucleo`. */
  atestar: async (id: number, aprovar: boolean, observacao = '') =>
    (await apiClient.post<{ estado_do_pedido: string; nivel_atual: string | null; medicao: Medicao }>(
      `pdca/medicoes/${id}/atestar/`, { aprovar, observacao },
    )).data,

  retificar: async (id: number, motivo: string) =>
    (await apiClient.post<Medicao>(`pdca/medicoes/${id}/retificar/`, { motivo })).data,
  cancelar: async (id: number, motivo = '') =>
    (await apiClient.post<Medicao>(`pdca/medicoes/${id}/cancelar/`, { motivo })).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/medicoes/${id}/`) },
}

/**
 * PDCA.4 — o contrato mudando por escrito.
 *
 * Mesma forma da medição, pelo mesmo motivo: o documento tem ciclo de vida, e
 * não há `PATCH`. Criar é `abrir`, mudar as linhas é `itens` e só em rascunho,
 * decidir é `atestar` — e aprovar é outra permissão, porque quem negocia o
 * acréscimo com o empreiteiro não é quem autoriza a empresa a gastá-lo.
 */
export const aditivos = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<Aditivo>>('pdca/aditivos/', { params })).data,
  obter: async (id: number) =>
    (await apiClient.get<Aditivo>(`pdca/aditivos/${id}/`)).data,

  abrir: async (payload: {
    contrato: number
    objeto: string
    justificativa: string
    data_assinatura?: string | null
    nova_data_fim?: string | null
    itens?: LinhaDeAditivo[]
  }) => (await apiClient.post<Aditivo>('pdca/aditivos/abrir/', payload)).data,

  itens: async (id: number, itens: LinhaDeAditivo[]) =>
    (await apiClient.post<{ itens: number; resumo: ResumoDoAditivo }>(
      `pdca/aditivos/${id}/itens/`, { itens },
    )).data,

  submeter: async (id: number) =>
    (await apiClient.post<{
      estado: string; escada: number | null; avisos: string[]; aditivo: Aditivo
    }>(`pdca/aditivos/${id}/submeter/`, {})).data,

  atestar: async (id: number, aprovar: boolean, observacao = '') =>
    (await apiClient.post<{
      estado_do_pedido: string; nivel_atual: string | null; aditivo: Aditivo
    }>(`pdca/aditivos/${id}/atestar/`, { aprovar, observacao })).data,

  cancelar: async (id: number, motivo = '') =>
    (await apiClient.post<Aditivo>(`pdca/aditivos/${id}/cancelar/`, { motivo })).data,
  excluir: async (id: number) => { await apiClient.delete(`pdca/aditivos/${id}/`) },
}

export const liberacoes = {
  listar: async (params: Params = {}) =>
    (await apiClient.get<Paginated<LiberacaoDeRetencao>>('pdca/liberacoes/', { params })).data,
}

export interface FornecedorOpt { fornecedor_id: number; razao_social: string }

/**
 * Fornecedores para o select do contrato, com busca server-side.
 *
 * **`/api/fornecedores/` responde LISTA CRUA, não página** — e ignorar isso foi
 * um defeito de verdade: a primeira escrita lia `.data.results`, que é
 * `undefined` num array, e o select do contrato nascia **vazio para sempre**.
 * O dono achou com o formulário aberto. A leitura aceita as duas formas, para
 * continuar funcionando no dia em que o endpoint for paginado — que é quando o
 * F2 for fechado de verdade neste cadastro.
 *
 * Não é endpoint do PDCA: pode responder 403 sozinho (quem planeja pode não ter
 * `cadastro.fornecedor.view`), e a tela trata isso como "esta ponte não está
 * contratada", nunca como lista vazia.
 */
export const fornecedoresOpt = async (busca: string): Promise<FornecedorOpt[]> => {
  const { data } = await apiClient.get<
    FornecedorOpt[] | Paginated<FornecedorOpt>
  >('fornecedores/', { params: { search: busca || undefined, page_size: 40 } })
  return Array.isArray(data) ? data : (data?.results ?? [])
}
