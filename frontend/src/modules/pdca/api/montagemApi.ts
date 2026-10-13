import apiClient from '@/api/apiClient'
import type {
  Atividade, CalendarioTrabalho, Cronograma, Precedencia, TipoPrecedencia,
} from '../types'

/** Etapa da obra como o PDCA a enxerga: só o que o seletor precisa. */
export interface EtapaDaObra {
  etapa_id: number
  nome_etapa: string
  ordem: number
}

/** Uma linha de planilha colada ou de XML do MS Project, antes de virar
 *  atividade. Os códigos são os do arquivo — servem só para as predecessoras
 *  se acharem; o servidor renumera a EAP no fim. */
export interface LinhaImportada {
  nome: string
  codigo?: string
  nivel?: number | null
  duracao_dias?: string | null
  eh_marco?: boolean | null
  predecessoras?: string
  nao_comecar_antes_de?: string | null
  peso?: string | null
}

export interface ResultadoDaImportacao {
  criadas: number
  ligacoes: number
  avisos: string[]
  avisos_total: number
}

export interface OrcamentoDaObra {
  orcamento_id: number
  descricao: string
  versao: number
  status: string
  status_rotulo: string
  itens: number
  /** Quantas etapas o cronograma físico-financeiro do Orçamento já pôs no tempo. */
  etapas_no_tempo: number
  valor_total: string | null
  ja_no_plano: boolean
}

/** Do orçamento vêm só etapas (decisão do dono, 10/10/2026). */
export interface ResumoDoOrcamento {
  orcamento: number
  versao: number
  linhas: number
  planejadas: number
  sem_plano: number
  simulado: boolean
  criadas?: number
}

/** O aviso do "copia e avisa": o cronograma do orçamento mudou desde que o
 *  plano trouxe as etapas? */
export interface SituacaoDoOrcamento {
  tem_etapas_do_orcamento: boolean
  origem: number | null
  origem_versao: number | null
  origem_status: string | null
  vigente: number | null
  vigente_versao: number | null
  mudou: boolean
  motivo: 'nova_versao' | 'cronograma_editado' | null
  atualizar_de: number | null
  pode_atualizar: boolean
}

export interface AtualizacaoDoOrcamento {
  orcamento: number
  versao: number
  atualizadas: number
  criadas: number
  fora_do_orcamento: { atividade: number; nome: string }[]
}

export interface FuncionarioCurto {
  funcionario_id: number
  nome_completo: string
}

export interface ItemOrcadoCurto {
  item_orcado_id: number
  codigo_eap: string
  descricao: string
  total_com_bdi: string | null
}

function lista<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  const pagina = data as { results?: T[] } | null
  return pagina?.results ?? []
}

/** A montagem do plano: tudo o que o planejador faz **dentro** do posto PLANO,
 *  sem sair para o cadastro da obra. */
export const precedencias = {
  async criar(corpo: {
    origem: number; destino: number; tipo?: TipoPrecedencia; atraso_dias?: number
  }): Promise<Precedencia> {
    const { data } = await apiClient.post('/pdca/precedencias/', {
      tipo: 'FS', atraso_dias: 0, ...corpo,
    })
    return data
  },
  async atualizar(
    id: number, corpo: { tipo?: TipoPrecedencia; atraso_dias?: number },
  ): Promise<Precedencia> {
    const { data } = await apiClient.patch(`/pdca/precedencias/${id}/`, corpo)
    return data
  },
  async remover(id: number): Promise<void> {
    await apiClient.delete(`/pdca/precedencias/${id}/`)
  },
}

export const plano = {
  /** A linha nasce **na posição**: logo abaixo de `depois_de`, ou no fim de `pai`. */
  async inserir(cronogramaId: number, corpo: {
    pai?: number | null; depois_de?: number | null; nome?: string
    duracao_dias?: number | null; eh_marco?: boolean; etapa?: number | null
  }): Promise<Atividade> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/inserir-atividade/`, corpo,
    )
    return data
  },
  /** Arrastar a linha, recuar, avançar, subir e descer — o servidor renumera. */
  async mover(atividadeId: number, pai: number | null, posicao?: number | null): Promise<Atividade> {
    const { data } = await apiClient.post(`/pdca/atividades/${atividadeId}/mover/`, {
      pai, posicao: posicao ?? null,
    })
    return data
  },
  /** O gesto da barra: fixa "não começar antes de" e/ou estica a duração, e o
   *  servidor recalcula — a barra pode voltar se uma predecessora não deixar. */
  async reprogramar(
    atividadeId: number,
    corpo: { nao_comecar_antes_de?: string | null; duracao_dias?: number },
  ): Promise<{ atividade: Atividade }> {
    const { data } = await apiClient.post(`/pdca/atividades/${atividadeId}/reprogramar/`, corpo)
    return data
  },
  async importarLinhas(
    cronogramaId: number, linhas: LinhaImportada[], referencia: 'codigo' | 'linha' = 'codigo',
  ): Promise<ResultadoDaImportacao> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/importar-linhas/`, { linhas, referencia },
    )
    return data
  },
  /** O desfazer da exclusão: recria a subárvore fotografada e devolve o mapa
   *  de ids antigos → novos. */
  async restaurar(cronogramaId: number, retrato: {
    pai: number | null; posicao: number
    atividades: Record<string, unknown>[]; ligacoes: Record<string, unknown>[]
  }): Promise<{ mapa: Record<string, number>; ligacoes: number }> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/restaurar-linhas/`, retrato,
    )
    return data
  },
  async orcamentos(cronogramaId: number): Promise<OrcamentoDaObra[]> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${cronogramaId}/orcamentos/`)
    return data
  },
  async gerarDoOrcamento(cronogramaId: number, corpo: {
    orcamento: number; duracao_padrao?: number; simular?: boolean
  }): Promise<ResumoDoOrcamento> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/gerar-do-orcamento/`, corpo,
    )
    return data
  },
  async situacaoDoOrcamento(cronogramaId: number): Promise<SituacaoDoOrcamento> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${cronogramaId}/situacao-do-orcamento/`)
    return data
  },
  async atualizarDoOrcamento(cronogramaId: number, corpo: { orcamento?: number | null } = {}): Promise<AtualizacaoDoOrcamento> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/atualizar-do-orcamento/`, corpo,
    )
    return data
  },
  async modelos(): Promise<Cronograma[]> {
    const { data } = await apiClient.get('/pdca/cronogramas/modelos/', {
      params: { page_size: 200 },
    })
    return lista<Cronograma>(data)
  },
  async aplicarModelo(modeloId: number, corpo: {
    obra: number; data_inicio: string; calendario?: number | null; descricao?: string
  }): Promise<Cronograma> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${modeloId}/aplicar-modelo/`, corpo,
    )
    return data
  },
  async anexarModelo(cronogramaId: number, modeloId: number): Promise<{ criadas: number }> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/anexar-modelo/`, { modelo: modeloId },
    )
    return data
  },
  async marcarModelo(cronogramaId: number, nome: string): Promise<Cronograma> {
    const { data } = await apiClient.post(
      `/pdca/cronogramas/${cronogramaId}/marcar-modelo/`, { nome },
    )
    return data
  },
  async desmarcarModelo(cronogramaId: number): Promise<Cronograma> {
    const { data } = await apiClient.post(`/pdca/cronogramas/${cronogramaId}/desmarcar-modelo/`)
    return data
  },
  async atualizar(
    cronogramaId: number, corpo: { calendario?: number | null; data_inicio?: string },
  ): Promise<Cronograma> {
    const { data } = await apiClient.patch(`/pdca/cronogramas/${cronogramaId}/`, corpo)
    return data
  },
}

/** O expediente converte duração em data: sem ele o plano não calcula prazo. */
export const expedientes = {
  async criar(corpo: {
    nome: string; obra: number | null; horas_por_dia: string
    trabalha_segunda: boolean; trabalha_terca: boolean; trabalha_quarta: boolean
    trabalha_quinta: boolean; trabalha_sexta: boolean; trabalha_sabado: boolean
    trabalha_domingo: boolean; considera_feriados: boolean
  }): Promise<CalendarioTrabalho> {
    const { data } = await apiClient.post('/pdca/calendarios/', corpo)
    return data
  },
  async criarExcecao(corpo: {
    calendario: number; data: string; trabalha: boolean; motivo: string
  }): Promise<void> {
    await apiClient.post('/pdca/excecoes-calendario/', corpo)
  },
  async removerExcecao(id: number): Promise<void> {
    await apiClient.delete(`/pdca/excecoes-calendario/${id}/`)
  },
}

export const etapasDaObra = {
  async listar(obraId: number): Promise<EtapaDaObra[]> {
    const { data } = await apiClient.get('/etapas-obras/', {
      params: { obra: obraId, page_size: 200 },
    })
    return lista<EtapaDaObra>(data)
  },
  /** A etapa nasce aqui, no ato de planejar; `ordem` segue a última da obra. */
  async criar(obraId: number, nome: string, ordem: number): Promise<EtapaDaObra> {
    const { data } = await apiClient.post('/etapas-obras/', {
      obra: obraId, nome_etapa: nome, ordem,
    })
    return data
  },
}

export async function renomearEtapa(etapaId: number, nome: string): Promise<EtapaDaObra> {
  const { data } = await apiClient.patch(`/etapas-obras/${etapaId}/`, { nome_etapa: nome })
  return data
}

/** O responsável vem do RH. Quem não tem o módulo recebe 403, e a tela diz
 *  isso no seletor em vez de mostrar uma lista vazia. */
export async function buscarFuncionarios(): Promise<FuncionarioCurto[]> {
  const { data } = await apiClient.get('/funcionarios/', { params: { page_size: 500 } })
  return lista<FuncionarioCurto>(data)
}

/** Os itens analíticos do orçamento, para ligar uma atividade ao custo. */
export async function buscarItensOrcados(
  orcamentoId: number, termo: string,
): Promise<ItemOrcadoCurto[]> {
  const { data } = await apiClient.get('/orcamento/itens/', {
    params: { orcamento: orcamentoId, search: termo || undefined, page_size: 30 },
  })
  return lista<ItemOrcadoCurto>(data)
}

/** Nome de etapa que ainda não existe na obra (`unique (obra, nome)`). */
export function nomeLivre(base: string, existentes: string[]): string {
  const usados = new Set(existentes.map((n) => n.trim().toLowerCase()))
  if (!usados.has(base.toLowerCase())) return base
  for (let n = 2; ; n++) {
    const candidato = `${base} ${n}`
    if (!usados.has(candidato.toLowerCase())) return candidato
  }
}

export interface FornecedorCurto {
  fornecedor_id: number
  razao_social: string
}

/** As empreiteiras — o mesmo cadastro do contrato de medição. */
export async function buscarFornecedores(): Promise<FornecedorCurto[]> {
  const { data } = await apiClient.get('/fornecedores/', { params: { page_size: 500 } })
  return lista<FornecedorCurto>(data)
}

/** O material informado na atividade — a compra sem orçamento. */
export interface MaterialInformado {
  material_id: number
  atividade: number
  item: number | null
  item_codigo: string | null
  descricao: string
  unidade: string
  categoria: 'material' | 'equipamento'
  quantidade: string
  custo_unitario: string | null
}

export const materiaisDaAtividade = {
  async listar(atividadeId: number): Promise<MaterialInformado[]> {
    const { data } = await apiClient.get('/pdca/materiais-atividade/', { params: { atividade: atividadeId, page_size: 200 } })
    return lista<MaterialInformado>(data)
  },
  async criar(corpo: Partial<MaterialInformado>): Promise<MaterialInformado> {
    const { data } = await apiClient.post('/pdca/materiais-atividade/', corpo)
    return data
  },
  async remover(id: number): Promise<void> {
    await apiClient.delete(`/pdca/materiais-atividade/${id}/`)
  },
}

export interface ItemDoCatalogo {
  item_id: number
  codigo_interno: string
  descricao: string
  unidade: string
}

export async function buscarNoCatalogo(termo: string): Promise<ItemDoCatalogo[]> {
  const { data } = await apiClient.get('/catalogo/itens/', { params: { search: termo, page_size: 15 } })
  return lista<ItemDoCatalogo>(data)
}
