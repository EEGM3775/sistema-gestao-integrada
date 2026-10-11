import apiClient from '@/api/apiClient'

/** O posto **Controle** (decisão do dono, 10/10/2026): o custo e o material
 *  da obra contra o plano. Valores chegam como string decimal, nulos quando
 *  não há régua — nunca zero inventado. */

export interface ValorAgregado {
  previsto_pct?: number | null
  realizado_pct?: number | null
  vp: string | null
  va: string | null
  cr: string | null
  idc: string | null
  idp: string | null
  a_incorrer: string | null
  ent: string | null
  vnt: string | null
}

export interface EtapaDoControle extends ValorAgregado {
  etapa: number
  etapa_nome: string
  orcado: string
  aplicado: string
  medido: string
}

export interface ContratoComprometido {
  contrato: number
  numero: string
  fornecedor: string
  status: string
  valor: string
  /** O contrato com pedido de serviço já está contado no pedido. */
  conta: boolean
}

export interface CustoDaObra {
  obra: number
  orcamento: number | null
  orcamento_versao: number | null
  plano: number | null
  plano_status: string | null
  colunas: {
    orcado: string | null
    orcado_com_bdi: string | null
    comprometido: string
    comprometido_pedidos: string
    comprometido_contratos: string
    aplicado: string
    medido: string
    realizado: string
    incorrido: string
    saldo: string | null
    estourado: boolean
  }
  valor_agregado: ValorAgregado
  etapas: EtapaDoControle[]
  sem_etapa: string
  contratos: ContratoComprometido[]
  nota: string
}

export interface InsumoDaObra {
  item: number | null
  descricao: string
  unidade: string
  categoria: string
  orcado_qtd: string
  orcado_valor: string
  aplicado_qtd: string
  aplicado_valor: string
  consumido_pct: string | null
  esperado_qtd: string | null
  desvio_qtd: string | null
  desvio_pct: string | null
  fora_do_orcamento: boolean
}

export interface MateriaisDaObra {
  obra: number
  orcamento: number | null
  realizado_pct: number | null
  insumos: InsumoDaObra[]
  totais: { orcado: string; aplicado: string }
}

export const controle = {
  async custo(obraId: number): Promise<CustoDaObra> {
    const { data } = await apiClient.get('/pdca/controle/custo/', { params: { obra: obraId } })
    return data
  },
  async materiais(obraId: number): Promise<MateriaisDaObra> {
    const { data } = await apiClient.get('/pdca/controle/materiais/', { params: { obra: obraId } })
    return data
  },
}
