import apiClient from '@/api/apiClient'

/** O cronograma puxa a compra — o contrato de `modulopdca.suprimentos`.
 *  Quantidades e dinheiro chegam em texto (Decimal do servidor), datas em ISO. */

export type SituacaoDaNecessidade = 'coberta' | 'comprar' | 'atrasada'

export interface LinhaDeNecessidade {
  atividade: number
  atividade_codigo: string
  atividade_nome: string
  etapa: number | null
  /** `atividade`: pelo item orçado ligado · `etapa`: item do orçamento da etapa
   *  que nenhuma atividade cita, posto na que começa primeiro. */
  origem: 'atividade' | 'etapa'
  item_orcado: number
  insumo: string
  item: number | null
  descricao: string
  unidade: string
  categoria: string
  tipo_demanda: 'material' | 'servico'
  quantidade: string
  restante: string
  executado_pct: string
  inicio_atividade: string
  antecedencia_dias: number
  antecedencia_origem: 'atividade' | 'insumo' | 'obra' | 'nenhuma'
  chegar_ate: string
  prazo_fornecedor_dias: number | null
  pedir_ate: string
  custo_unitario: string
  coberto_estoque: string
  coberto_pedido: string
  coberto_demanda: string
  a_comprar: string
  situacao: SituacaoDaNecessidade
}

export interface ResumoDeInsumo {
  insumo: string
  item: number | null
  descricao: string
  unidade: string
  categoria: string
  tipo_demanda: 'material' | 'servico'
  necessario: string
  a_comprar: string
  primeiro_pedir_ate: string
  primeira_falta?: string
  estoque: string
  em_pedido: string
  em_demanda: string
  valor_a_comprar: string
  atividades: number
  /** Saldo livre em outros almoxarifados (central, canteiro de outra obra). */
  fora_da_obra: string
}

export interface NecessidadeDeMaterial {
  cronograma: number
  obra: number | null
  orcamento: number | null
  antecedencia_padrao: number | null
  linhas: LinhaDeNecessidade[]
  por_insumo: ResumoDeInsumo[]
  cobertura: {
    folhas: number
    folhas_com_item_orcado: number
    folhas_fora_da_conta: number
    etapas_sem_orcamento: number
    tem_orcamento_vigente: boolean
    /** Atividades ligadas a item de versão anterior do orçamento (lidas pela vigente). */
    ligadas_a_versao_anterior: number
  }
}

export interface ValoresDeCusto {
  orcado: string
  comprometido: string
  recebido: string
  medido: string
}

export interface CustoDaAtividade extends ValoresDeCusto {
  atividade: number
  codigo: string
  nome: string
  etapa: number | null
}

export interface CustoDaEtapa extends ValoresDeCusto {
  etapa: number | null
  etapa_nome: string
  aplicado: string
  atividades: CustoDaAtividade[]
}

export interface CustoDoPlano {
  cronograma: number
  orcamento: number | null
  etapas: CustoDaEtapa[]
  total: ValoresDeCusto & { aplicado: string }
  nao_alocado: { comprometido: string; recebido: string; aplicado: string; medido: string }
  /** Pedido e recebido são rateados por insumo entre as atividades. */
  rateado: boolean
}

export interface AntecedenciaDeCompra {
  antecedencia_id: number
  obra: number
  item: number | null
  item_descricao?: string
  dias: number
}

export const suprimentos = {
  async necessidade(cronogramaId: number): Promise<NecessidadeDeMaterial> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${cronogramaId}/suprimentos/`)
    return data
  },
  async custo(cronogramaId: number): Promise<CustoDoPlano> {
    const { data } = await apiClient.get(`/pdca/cronogramas/${cronogramaId}/custo/`)
    return data
  },
  async religarOrcamento(cronogramaId: number): Promise<{ atividades: number }> {
    const { data } = await apiClient.post(`/pdca/cronogramas/${cronogramaId}/religar-orcamento/`, {})
    return data
  },
  async gerarDemanda(
    cronogramaId: number, corpo: { insumos?: string[]; ate?: string | null },
  ): Promise<{ demandas: { demanda: number; tipo: string; itens: number }[] }> {
    const { data } = await apiClient.post(`/pdca/cronogramas/${cronogramaId}/suprimentos/gerar-demanda/`, corpo)
    return data
  },
}

export const antecedencias = {
  async listar(obraId: number): Promise<AntecedenciaDeCompra[]> {
    const { data } = await apiClient.get('/pdca/antecedencias/', { params: { obra: obraId, page_size: 500 } })
    return Array.isArray(data) ? data : (data.results ?? [])
  },
  /** Cria, muda ou (com `dias` nulo) apaga — padrão da obra (`item` nulo) ou exceção do insumo. */
  async definir(
    obraId: number, item: number | null, dias: number | null, existente?: AntecedenciaDeCompra,
  ): Promise<void> {
    if (existente && dias == null) {
      await apiClient.delete(`/pdca/antecedencias/${existente.antecedencia_id}/`)
    } else if (existente && dias != null) {
      await apiClient.patch(`/pdca/antecedencias/${existente.antecedencia_id}/`, { dias })
    } else if (dias != null) {
      await apiClient.post('/pdca/antecedencias/', { obra: obraId, item, dias })
    }
  },
}
