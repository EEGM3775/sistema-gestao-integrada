import apiClient from '@/api/apiClient'
import type {
  Apontamento, AvancoDoCronograma, CurvaS, Granularidade, LinhaDeApontamento,
  ResultadoDoApontamentoEmLote,
  Atividade, ComparacaoBase, CoberturaOrcamento, Cronograma, ObraOpt,
  AplicacaoDeModelo, Calendario, ContagemDeDiasUteis, EdicaoEmLote, EtapaOpt,
  ExcecaoCalendario, ItemOrcadoOpt, LocalOpt, OrcamentoOpt, Paginated, PayloadGantt,
  Precedencia, ResponsavelOpt, ResultadoCpm, ResultadoDaRenumeracao, ResultadoDoLote,
  StatusModulo,
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
