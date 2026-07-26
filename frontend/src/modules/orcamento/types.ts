// Contrato do `/api/orcamento/` (moduloorcamento). Decimais chegam como string
// do DRF e ficam string até a hora de formatar — converter cedo perde centavo.

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type Fonte = 'sinapi' | 'orse' | 'sicro' | 'seinfra' | 'sedop' | 'tcpo' | 'propria'
export type Regime = 'onerado' | 'desonerado' | 'na'
export type StatusOrcamento = 'rascunho' | 'aprovado' | 'superado' | 'cancelado'
export type TipoLinha = 'sintetico' | 'analitico'
export type TipoReferencia = 'insumo' | 'composicao'
export type ClasseABC = 'A' | 'B' | 'C'

export interface BaseReferencial {
  base_id: number
  fonte: Fonte
  fonte_nome: string
  uf: string
  mes_referencia: string
  regime_encargos: Regime
  regime_nome: string
  rotulo: string
  rotulo_exibicao: string
  total_insumos: number
  total_composicoes: number
  ativa: boolean
  importada_em: string
  importada_por_nome: string
}

/** `/orcamento/bases-resumo/` — contagem VIVA por publicação. Os nomes não são os
 *  do model (`total_insumos`/`total_composicoes`, contadores gravados na
 *  importação): a view anota `Count(...)` na hora, e anotação não pode repetir o
 *  nome de um campo do model. */
export interface BaseResumo {
  base_id: number
  rotulo: string
  fonte: Fonte
  uf: string
  mes_referencia: string
  regime_encargos: Regime
  insumos: number
  composicoes: number
  adotados_no_catalogo: number
}

export interface InsumoReferencia {
  referencia_id: number
  base: number
  base_rotulo: string
  base_fonte: Fonte
  base_mes: string
  codigo: string
  descricao: string
  unidade: string
  tipo: TipoReferencia
  custo_unitario: string
  grupo: string
  adotado_item_id: number | null
}

export interface ComponenteReferencia {
  componente_id: number
  composicao: number
  filho: number
  coeficiente: string
  filho_codigo: string
  filho_descricao: string
  filho_unidade: string
  filho_tipo: TipoReferencia
  filho_custo_unitario: string
  custo_no_item: string
}

/** Envelope de `/referencias/{id}/composicao/`: a composição-pai + a analítica. */
export interface ComposicaoReferenciaResposta {
  composicao: InsumoReferencia
  componentes: ComponenteReferencia[]
}

/** Item do catálogo da empresa criado (ou reaproveitado) por uma adoção. */
export interface ItemAdotado {
  item_id: number
  codigo_interno: string
  descricao: string
}

/** `/referencias/adotar-lote/` — `adotados` é a CONTAGEM, não a lista de ids;
 *  os ids vêm em `itens` (a adoção é idempotente, então reaproveita item já
 *  existente e a ordem não espelha necessariamente a seleção da tela). */
export interface ResultadoAdocaoLote {
  adotados: number
  itens: ItemAdotado[]
}

export interface Orcamento {
  orcamento_id: number
  obra: number
  obra_nome: string
  descricao: string
  versao: number
  orcamento_origem: number | null
  base_referencial: number | null
  base_rotulo: string | null
  data_base: string | null
  regime_encargos: Regime
  encargos_sociais_percentual: string
  bdi_percentual: string
  status: StatusOrcamento
  status_nome: string
  custo_direto_total: string
  valor_total: string
  aprovado_em: string | null
  aprovado_por_nome: string
  observacao: string
  criado_em: string
  atualizado_em: string
  editavel: boolean
  total_itens: number
}

export interface ItemOrcado {
  item_orcado_id: number
  orcamento: number
  pai: number | null
  codigo_eap: string
  ordem: number
  tipo_linha: TipoLinha
  tipo_linha_nome: string
  etapa: number | null
  etapa_nome: string | null
  item: number | null
  item_codigo: string | null
  descricao: string
  unidade: string
  quantidade: string
  custo_unitario: string
  fonte_referencia: Fonte | ''
  codigo_referencia: string
  data_base_preco: string | null
  bdi: number | null
  total_custo_direto: string
  total_com_bdi: string
  observacao: string
}

export interface ArvoreResposta {
  orcamento: Orcamento
  itens: ItemOrcado[]
}

export interface RevisaoOrcamento {
  revisao_id: number
  orcamento: number
  orcamento_anterior: number | null
  orcamento_versao: number
  numero: number
  tipo: string
  tipo_nome: string
  motivo: string
  valor_anterior: string
  valor_novo: string
  delta: string
  criado_por_nome: string
  criado_em: string
}

export interface ComposicaoBDI {
  bdi_id: number
  orcamento: number
  nome: string
  padrao: boolean
  administracao_central: string
  seguro: string
  risco: string
  garantia: string
  despesas_financeiras: string
  lucro: string
  pis: string
  cofins: string
  iss: string
  cprb: string
  tributos: string
  percentual_calculado: string
  observacao: string
}

export type CategoriaInsumo = 'material' | 'mao_de_obra' | 'equipamento' | 'outro'

export interface ItemOrcadoInsumo {
  insumo_id: number
  item: number | null
  descricao: string
  unidade: string
  categoria: CategoriaInsumo
  coeficiente: string
  custo_unitario: string
  custo_no_item: string
  peso_pct: string
}

export interface MemoriaCalculo {
  item_orcado: number
  descricao: string
  unidade: string
  custo_unitario: string
  total_composicao: string
  insumos: ItemOrcadoInsumo[]
  por_categoria: Record<string, { valor: string; pct: string }>
}

export interface CustoPorCategoria {
  orcamento: number
  total: string
  custo_direto_do_orcamento: string
  cobertura_pct: string
  categorias: { categoria: CategoriaInsumo; rotulo: string; valor: string; pct: string }[]
}

export interface CurvaABCLinha {
  item_orcado: number
  item: number | null
  codigo_eap: string
  descricao: string
  unidade: string
  quantidade: string
  valor: string
  pct: string
  pct_acumulado: string
  classe: ClasseABC
}

export interface CurvaABC {
  orcamento: number
  total: string
  resumo: Record<ClasseABC, { itens: number; valor: string; pct: string }>
  itens: CurvaABCLinha[]
}

export interface PrecoReal {
  item: number
  scm: {
    preco_medio: string | null
    ultimo_preco: string | null
    ultima_compra: string | null
    quantidade_comprada: string
  }
  sil: {
    custo_medio: string | null
    quantidade_em_estoque: string
  }
}

export interface ControleLinha {
  obra: number
  obra_nome: string
  orcamento: number | null
  orcamento_versao: number | null
  orcado: string | null
  orcado_com_bdi: string | null
  comprometido: string
  aplicado: string
  realizado: string
  saldo: string | null
  consumido_pct: string | null
  estourado: boolean
  realizado_cobertura: string
  /** Vem do envelope da resposta (ver `ControleResposta`), não da linha: o
   *  cliente a replica em cada linha para a tela ler de um lugar só. */
  nota_realizado?: string
}

/** Envelope de `/orcamento/controle/`. A nota é da RESPOSTA, não da obra — a tela
 *  precisa dela para não apresentar um realizado parcial como total. */
export interface ControleResposta {
  obras: ControleLinha[]
  nota_realizado: string
}

export interface ParcelaEtapa {
  parcela_id: number
  orcamento: number
  etapa: number | null
  etapa_nome: string | null
  competencia: string
  percentual: string
  valor_previsto: string
  observacao: string
}

export interface ParcelaCelula {
  parcela_id: number
  percentual: string
  valor_previsto: string
}

export interface CronogramaLinha {
  etapa: number | null
  etapa_nome: string
  parcelas: Record<string, ParcelaCelula>
  total: string
}

export interface CronogramaValidacao {
  consistente: boolean
  problemas: { etapa: number | null; soma_percentual: string; diferenca: string }[]
}

export interface Cronograma {
  orcamento: number
  competencias: string[]
  linhas: CronogramaLinha[]
  total: string
  validacao: CronogramaValidacao
}

export interface CurvaSPonto {
  competencia: string
  previsto: string
  previsto_acumulado: string
  previsto_pct_acumulado: string | null
  realizado: string
  realizado_acumulado: string
  realizado_pct_acumulado: string | null
  desvio_acumulado: string
}

export interface CurvaS {
  orcamento: number
  obra: number
  total_previsto: string
  total_realizado: string
  fonte_realizado: string
  serie: CurvaSPonto[]
}

export interface ParametroObra {
  parametro_id: number
  obra: number
  obra_nome: string
  descricao: string
  projeto_padrao: string
  projeto_padrao_nome: string
  cub_m2: string
  cub_uf: string
  cub_mes: string | null
  area_real: string
  area_equivalente: string
  percentual_adicionais: string
  valor_adicionais: string
  custo_estimado: string
  observacao: string
  criado_em: string
}

export interface PavimentoObra {
  pavimento_id: number
  obra: number
  nome: string
  ordem: number
  area_coberta_padrao: string
  area_coberta_diferente: string
  coeficiente_coberta_diferente: string
  area_descoberta: string
  coeficiente_descoberta: string
  area_real: string
  area_equivalente: string
}

export interface UnidadeAutonoma {
  unidade_id: number
  obra: number
  pavimento: number | null
  pavimento_nome: string | null
  designacao: string
  tipo: string
  area_privativa_padrao: string
  area_privativa_diferente: string
  coeficiente_privativa_diferente: string
  area_uso_comum: string
  area_real_privativa: string
  area_equivalente_privativa: string
  fracao_ideal: string
  coeficiente_proporcionalidade: string
  custo_estimado: string
}

export interface MemorialNBR {
  memorial_id: number
  obra: number
  quadro: string
  quadro_nome: string
  ordem: number
  dependencia: string
  descricao: string
}

/** Opções vindas de `obras`/`etapas-obras` (apps-base). A PK dos modelos do
 *  projeto é nomeada, não `id` — declarar `id` aqui fazia `<option value={o.id}>`
 *  sair sem atributo `value`, e o select devolvia o texto visível em vez do
 *  número (a obra chegava `null` no POST). */
export interface ObraOpt {
  obra_id: number
  nome_obra: string
}

export interface EtapaOpt {
  etapa_id: number
  nome_etapa: string
  obra: number
}

export interface CatalogoItem {
  item_id: number
  codigo_interno: string
  descricao: string
  unidade: string
  categoria: string
  tipo: string
  compravel: boolean
  estocavel: boolean
  fonte_referencia: Fonte | ''
  codigo_referencia: string
  ativo: boolean
}

export interface StatusModulo {
  modulo: string
  status: string
  bases_referenciais: number
}

// --- ORC.5b: bancos da empresa, importação e reprecificação ---

export type OrigemBanco = 'importada' | 'propria'
export type SituacaoLinha = 'nova' | 'duplicada' | 'invalida'
export type StatusImportacao = 'conferindo' | 'aplicada' | 'descartada' | 'erro'
export type OrigemImportacao = 'planilha' | 'api' | 'pdf'
export type DestinoImportacao = 'banco' | 'base_mae'
export type StatusReprecificacao = 'previa' | 'aplicada' | 'desfeita'

export interface BancoPreco {
  banco_id: number
  nome: string
  rotulo: string
  descricao: string
  fonte: Fonte
  fonte_nome: string
  uf: string
  mes_referencia: string | null
  regime_encargos: Regime
  obra: number | null
  obra_nome: string | null
  origem: OrigemBanco
  origem_nome: string
  travado: boolean
  travado_em: string | null
  travado_por_nome: string
  total_itens: number
  total_pastas: number
  ativo: boolean
  editavel: boolean
  criado_em: string
}

export interface BancoResumo {
  banco_id: number
  nome: string
  rotulo: string
  fonte: Fonte
  uf: string
  mes_referencia: string | null
  regime_encargos: Regime
  obra: number | null
  obra_nome: string | null
  origem: OrigemBanco
  travado: boolean
  travado_em: string | null
  travado_por_nome: string
  total_itens: number
  pastas: number
}

export interface PastaComposicao {
  pasta_id: number
  banco: number
  nome: string
  obra: number | null
  obra_nome: string | null
  ordem: number
  total_itens: number
}

export interface ItemBancoPreco {
  item_banco_id: number
  banco: number
  banco_nome: string
  pasta: number | null
  pasta_nome: string | null
  codigo: string
  descricao: string
  unidade: string
  tipo: TipoReferencia
  tipo_nome: string
  custo_unitario: string
  grupo: string
  observacao: string
  adotado_item_id: number | null
}

export interface ComponenteBancoPreco {
  componente_id: number
  composicao: number
  filho: number
  coeficiente: string
  filho_codigo: string
  filho_descricao: string
  filho_unidade: string
  filho_custo_unitario: string
  custo_no_item: string
}

// `ImportacaoPreco`, `ResumoImportacao` e `LinhaImportacao` saíram no IE.1:
// os tipos do motor vivem em `@/components/malha/impexp/api` e servem
// todo módulo, não só este.

export interface Reprecificacao {
  reprecificacao_id: number
  orcamento: number
  orcamento_descricao: string
  base_destino: number | null
  banco_destino: number | null
  destino_rotulo: string | null
  data_base_destino: string | null
  somente_ate: string | null
  status: StatusReprecificacao
  status_nome: string
  total_antes: string
  total_depois: string
  delta: string
  linhas_afetadas: number
  motivo: string
  criado_em: string
  aplicada_em: string | null
  desfeita_em: string | null
  criado_por_nome: string
}

export interface LinhaPrevia {
  linha: number
  item_orcado: number
  codigo_eap: string
  descricao: string
  unidade: string
  quantidade: string
  codigo_referencia: string
  custo_antes: string
  custo_depois: string
  delta_unitario: string
  delta_pct: string | null
  delta_total: string
  data_base_antes: string | null
  data_base_depois: string | null
  selecionada: boolean
  aplicada: boolean
}

export interface PreviaReprecificacao {
  reprecificacao: number
  orcamento: number
  status: StatusReprecificacao
  destino: string | null
  data_base_destino: string | null
  somente_ate: string | null
  total_antes: string
  total_depois: string
  delta: string
  delta_pct: string | null
  linhas_afetadas: number
  linhas: LinhaPrevia[]
}

export interface ResumoDuplicata {
  orcamento: number
  obra: number
  versao: number
  descricao: string
  total_itens: number
  valor_total: string
  linhas_sem_etapa: number
  aviso_etapa: string
}
