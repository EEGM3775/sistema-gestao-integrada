// Contrato do `/api/orcamento/` (moduloorcamento). Decimais chegam como string
// do DRF e ficam string até a hora de formatar — converter cedo perde centavo.

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type Fonte = 'sinapi' | 'orse' | 'sicro' | 'seinfra' | 'sedop' | 'tcpo' | 'embasa' | 'propria'
/** ORC.8 — `sem` são as abas ISE/CSE do arquivo nacional: preço sem encargos
 *  sociais, que é a base legítima para aplicar o quadro analítico do ORC.7 (usar
 *  preço que já embute encargo da Caixa contaria duas vezes). */
export type Regime = 'onerado' | 'desonerado' | 'sem' | 'na'
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
  /** Quarto eixo de identidade, e vazio em quase toda publicação. A EMBASA
   *  publica, para o mesmo semestre e o mesmo regime, uma tabela por escopo ×
   *  convenção coletiva (`expansao-sintracom`, `operacao-agua-un-fixa-…`) — os
   *  mesmos códigos com preços diferentes. Sem ele, o seletor chegaria ao
   *  último passo com duas linhas de nome igual. */
  variante: string
  insumos: number
  composicoes: number
  /** Quantos insumos da publicação trazem a coluna `Classificação` preenchida.
   *  Preenchida ≠ legível: ver `classes_desconhecidas`. */
  insumos_classificados: number
  /** Classes que a publicação usa e que o sistema não sabe traduzir em natureza
   *  (vocabulário próprio de ORSE/SICRO/prefeitura). Texto literal, para alguém
   *  decidir se vira mapeamento ou `--de-para`. */
  classes_desconhecidas: string[]
  /** `false` = a classificação **não chega até a natureza**, e todo insumo cai no
   *  plano B da unidade — o que não é hora/mês vira material, e o que é hora vira
   *  mão de obra (leva encargo social). Duas causas: publicação anterior a
   *  01/2025, que não traz a coluna (D111), ou vocabulário que não sabemos ler. */
  classifica_insumo: boolean
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

/** O item do catálogo achado pelo código **não é** o item que a publicação
 *  descreve (D110): a fonte reaproveitou o número entre edições. A adoção não
 *  sobrescreve — devolve os dois lados para quem está na tela decidir. */
export interface DivergenciaAdocao {
  codigo: string
  item_id: number
  codigo_interno: string
  /** "descrição" · "unidade" · "descrição e unidade" */
  motivo: string
  descricao_catalogo: string
  descricao_publicacao: string
  unidade_catalogo: string
  unidade_publicacao: string
  semelhanca: number
}

/** `/referencias/adotar-lote/` — `adotados` é a CONTAGEM, não a lista de ids;
 *  os ids vêm em `itens` (a adoção é idempotente, então reaproveita item já
 *  existente e a ordem não espelha necessariamente a seleção da tela).
 *  `divergentes` são os que ficaram de FORA por não conferirem (D110). */
export interface ResultadoAdocaoLote {
  adotados: number
  itens: ItemAdotado[]
  divergentes: DivergenciaAdocao[]
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

export type CategoriaInsumo =
  | 'material' | 'mao_de_obra' | 'equipamento' | 'encargos_complementares' | 'outro'

/** A natureza do item no catálogo — a classificação que a SINAPI publica.
 *  É ela que decide conta: encargo social só incide sobre `mao_de_obra`. */
export type NaturezaItem =
  | 'material' | 'mao_de_obra' | 'equipamento' | 'encargos_complementares'
  | 'servico' | 'epi' | 'ativo' | 'composicao'

/** Flags de domínio de um tipo — o que cada módulo faz com o item. */
export interface FlagsTipoItem {
  leva_encargo_social: boolean
  compravel: boolean
  estocavel: boolean
  vendavel: boolean
  consumivel: boolean
  rastreavel: boolean
}

/** O tipo de item **que a empresa cria**, por cima de uma natureza da SINAPI. */
export interface TipoItemProprio extends FlagsTipoItem {
  tipo_item_id: number
  codigo: string
  nome: string
  descricao: string
  natureza: NaturezaItem
  natureza_nome: string
  ativo: boolean
  itens_com_este_tipo: number
}

/** `/catalogo/tipos-item/naturezas/` — as naturezas com o padrão de flags de
 *  cada uma. O de-para vive no backend: a tela que o repetisse divergiria dele
 *  na primeira mudança de regra. */
export interface NaturezaComPadroes {
  valor: NaturezaItem
  rotulo: string
  padroes: FlagsTipoItem
}

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

/** `/orcamentos/{id}/analitica/` — a composição de **cada** linha da planilha,
 *  indexada pelo `item_orcado_id` em texto (chave de JSON é sempre string).
 *  É o que a grade desenha embaixo do serviço no modo analítico. */
export type AnaliticaOrcamento = Record<string, ItemOrcadoInsumo[]>

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
  /** De qual EDIÇÃO o item foi adotado ("SINAPI BA 10/2024 desonerada"). */
  publicacao_referencia?: string
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
  /** A linha **não tem preço** na publicação de destino. Não é erro e não é
   *  "preço igual": não há valor novo para aplicar, então ela mantém o preço e a
   *  `data_base_antes` enquanto o cabeçalho do orçamento anda para a data nova.
   *  Nunca é selecionável — o backend a recusa mesmo se vier marcada. */
  descontinuado: boolean
  /** Por que não tem preço, em uma frase: item aposentado pela fonte, ou sem
   *  pesquisa de preço naquela UF (e, neste caso, em que UFs ele existe). */
  motivo: string
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
  /** Quantas linhas ficaram sem preço novo. Não entram em `linhas_afetadas`,
   *  porque não mudam preço nenhum. */
  linhas_descontinuadas: number
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

// --- ORC.7: encargos analíticos, memória do quantitativo e reajuste ---

export type GrupoEncargos = 'A' | 'B' | 'C' | 'D'
export type TipoMaoDeObra = 'horista' | 'mensalista'
export type RegimeEncargos = 'onerado' | 'desonerado'

export interface RubricaEncargos {
  rubrica_id: number
  composicao: number
  grupo: GrupoEncargos
  grupo_nome: string
  codigo: string
  descricao: string
  percentual: string
  base_calculo: 'direta' | 'a_sobre_b' | 'fgts_sobre_aviso'
  derivada: boolean
  e_fgts: boolean
  e_aviso_previo: boolean
  ordem: number
}

export interface ComposicaoEncargos {
  encargos_id: number
  orcamento: number
  nome: string
  tipo_mao_de_obra: TipoMaoDeObra
  tipo_nome: string
  regime: RegimeEncargos
  regime_nome: string
  padrao: boolean
  data_base: string | null
  total_grupo_a: string
  total_grupo_b: string
  total_grupo_c: string
  total_grupo_d: string
  percentual_calculado: string
  observacao: string
  rubricas: RubricaEncargos[]
}

/** O quadro pronto para a tela — com a conta ao lado de cada derivada. */
export interface QuadroEncargos {
  encargos: number
  orcamento: number
  nome: string
  tipo_mao_de_obra: TipoMaoDeObra
  regime: RegimeEncargos
  padrao: boolean
  data_base: string | null
  total: string
  grupos: {
    grupo: GrupoEncargos
    rotulo: string
    subtotal: string
    rubricas: {
      rubrica: number
      codigo: string
      descricao: string
      percentual: string
      derivada: boolean
      conta: string
      e_fgts: boolean
      e_aviso_previo: boolean
    }[]
  }[]
}

export interface LinhaMedicao {
  medicao_id: number
  item_orcado: number
  ordem: number
  descricao: string
  sinal: 1 | -1
  sinal_nome: string
  repeticoes: string
  comprimento: string | null
  largura: string | null
  altura: string | null
  formula: string
  total: string
  referencia_projeto: string
}

export interface MemoriaQuantitativo {
  item_orcado: number
  descricao: string
  unidade: string
  quantidade: string
  derivada: boolean
  total_somado: string
  total_subtraido: string
  total: string
  confere: boolean
  linhas: {
    medicao: number
    ordem: number
    descricao: string
    sinal: 1 | -1
    repeticoes: string
    comprimento: string | null
    largura: string | null
    altura: string | null
    formula: string
    total: string
    referencia_projeto: string
  }[]
}

export interface CoberturaMedicao {
  orcamento: number
  custo_direto_total: string
  custo_com_memoria: string
  cobertura_pct: string
  linhas_totais: number
  linhas_com_memoria: number
}

/** Campos de cobertura que toda resposta de insumo carrega — a honestidade do número. */
export interface Cobertura {
  custo_direto_total: string
  custo_direto_explodido: string
  cobertura_pct: string
  linhas_analiticas: number
  linhas_explodidas: number
  linhas_sem_composicao: number
}

export interface InsumoConsolidado {
  item: number | null
  codigo_referencia: string
  fonte_referencia: string
  descricao: string
  unidade: string
  categoria: string
  rotulo_categoria?: string
  quantidade: string
  custo_unitario_medio: string
  valor: string
  pct: string
  servicos: number
}

export interface RelacaoInsumos extends Cobertura {
  orcamento: number
  filtro_categoria: string
  total: string
  itens: InsumoConsolidado[]
}

export interface CurvaABCInsumos extends Cobertura {
  orcamento: number
  total: string
  resumo: Record<ClasseABC, { itens: number; valor: string; pct: string }>
  itens: (InsumoConsolidado & { pct_acumulado: string; classe: ClasseABC })[]
}

export interface ComposicaoPorNatureza {
  item_orcado: number
  codigo_eap: string
  descricao: string
  unidade: string
  quantidade: string
  custo_unitario: string
  total_composicao: string
  confere_com_a_linha: boolean
  grupos: {
    categoria: string
    rotulo: string
    subtotal: string
    pct: string
    insumos: {
      insumo: number
      item: number | null
      descricao: string
      unidade: string
      coeficiente: string
      custo_unitario: string
      custo_no_item: string
      pct: string
    }[]
  }[]
}

export interface DesembolsoInsumo {
  item: number | null
  descricao: string
  unidade: string
  categoria: string
  quantidade_total: string
  valor_total: string
  meses: Record<string, { quantidade: string; valor: string }>
}

export interface DesembolsoPorInsumo {
  orcamento: number
  filtro_categoria: string
  competencias: string[]
  insumos: DesembolsoInsumo[]
  sem_distribuicao: DesembolsoInsumo[]
  nota_sem_distribuicao: string
}

export interface IndiceEconomico {
  indice_id: number
  codigo: string
  nome: string
  fonte: string
  uf: string
  ativo: boolean
}

export interface ValorIndice {
  valor_id: number
  indice: number
  indice_codigo: string
  competencia: string
  numero_indice: string
  variacao_percentual: string | null
}

export interface ParcelaFormulaReajuste {
  parcela_id: number
  formula: number
  indice: number
  indice_codigo: string
  indice_nome: string
  peso: string
  rotulo: string
}

export interface FormulaReajuste {
  formula_id: number
  orcamento: number
  nome: string
  data_base: string
  parcela_fixa: string
  observacao: string
  parcelas: ParcelaFormulaReajuste[]
  soma_pesos: string
  fecha: boolean
}

export interface MemoriaFator {
  formula: number
  nome: string
  data_base: string
  competencia: string
  parcela_fixa: string
  fator: string
  variacao_pct: string
  parcelas: {
    parcela: number
    indice: string
    nome_indice: string
    rotulo: string
    peso: string
    indice_base: string
    indice_reajuste: string
    razao: string
    variacao_pct: string
    contribuicao: string
  }[]
}

export interface PreviaReajuste {
  orcamento: number
  status_orcamento: StatusOrcamento
  exige_revisao: boolean
  memoria: MemoriaFator
  total_antes: string
  total_depois: string
  delta: string
  itens: {
    item_orcado: number
    codigo_eap: string
    descricao: string
    unidade: string
    quantidade: string
    custo_antes: string
    custo_depois: string
    valor_antes: string
    valor_depois: string
    delta: string
  }[]
}

export interface ResultadoReajuste {
  orcamento: number
  versao: number
  gerou_revisao: boolean
  revisao: number | null
  memoria: MemoriaFator
  linhas_reajustadas: number
  valor_anterior: string
  valor_novo: string
}

export interface DemandaGerada {
  demanda: number
  tipo: string
  status: string
  itens: number
  orcamento: number
  valor_orcado_dos_itens: string
  cobertura_pct: string
  nota_cobertura: string
}


// ---------------------------------------------------------------------------
// ORC.8 — a carga da base oficial
// ---------------------------------------------------------------------------

export type EstadoCarga =
  | 'pendente' | 'baixando' | 'lendo' | 'gravando'
  | 'aguardando' | 'concluida' | 'falhou'

export interface FonteOficial {
  fonte_id: number
  fonte: Fonte
  fonte_nome: string
  /** Aceita {ano}, {mes}, {ano_mes}, {uf} e {regime}. Editável de propósito: a
   *  URL da Caixa já mudou uma vez, e o conserto tem de ser uma caixa de texto. */
  template_url: string
  pagina_referencia: string
  ativa: boolean
  /** 0 = sem agendamento; só o botão. */
  dia_do_mes: number
  defasagem_meses: number
  observacao: string
  competencia_sugerida: string
  /** O motor sabe ler o arquivo desta fonte sozinho? Hoje SINAPI e EMBASA. */
  carga_automatica: boolean
  /** A fonte publica um **menu** em vez de um arquivo do mês? Na SINAPI o certo
   *  é um botão "carregar 07/2026"; na EMBASA, que põe 65 tabelas por semestre
   *  no ar, um botão só esconderia a pergunta que importa — qual delas. */
  exige_documento: boolean
}

/** Um artefato anunciado pela fonte — o que a tela lista antes do botão.
 *
 *  É **menu**, não verdade: espécie e rótulo vêm do nome do arquivo. Quem
 *  decide onde o preço entra é o cabeçalho do PDF, na leitura. */
export interface DocumentoDaFonte {
  url: string
  rotulo: string
  slug: string
  /** `insumos` · `servicos` · `encargos` · `outro` · `pacote`. */
  especie: string
  /** Estar na lista é honesto (é o que a página publica); oferecer o botão não
   *  é. O quadro de Encargos Sociais da EMBASA é da ORC.7, não base de preço. */
  carregavel: boolean
}

export interface DocumentosDaFonte {
  fonte?: Fonte
  documentos: DocumentoDaFonte[]
  /** A fonte fora do ar não é erro do pedido, é o estado do mundo — e a tela
   *  precisa do motivo para oferecer o plano B em vez de uma lista vazia que
   *  parece "não há nada publicado". */
  erro: string
  motivo: string
}

export interface PublicacaoDoResumo {
  uf: string
  regime: Regime
  insumos: number
  composicoes: number
}

export interface ResumoDaCarga {
  /** O nome do artefato lido — planilha na SINAPI, PDF na EMBASA. */
  planilha?: string
  aba_analitica?: string
  /** ORC.8b — o nome que a **fonte** deu à tabela, quando ela publica várias.
   *  É a conferência de que veio o documento certo: traz escopo, convenção
   *  coletiva e a leis sociais do cabeçalho do arquivo. */
  rotulo?: string
  variante?: string
  /** A data-base que o artefato declara, quando ele a declara — a EMBASA
   *  publica por semestre, e a competência pedida é palpite. */
  competencia_lida?: string
  publicacoes?: PublicacaoDoResumo[]
  total_publicacoes?: number
  linhas_analiticas?: number
  itens_sem_preco_em_nenhuma_uf?: number
  avisos?: string[]
  classes_desconhecidas?: string[]
  publicacoes_criadas?: number
  publicacoes_atualizadas?: number
  analitica_gravada?: number
  motivo?: string
}

export interface CargaBase {
  carga_id: number
  fonte: Fonte
  fonte_nome: string
  competencia: string
  origem: 'download' | 'upload'
  origem_nome: string
  estado: EstadoCarga
  estado_nome: string
  /** O que a corrida faz agora, em uma frase — é o que a tela mostra enquanto roda. */
  etapa: string
  url_origem: string
  arquivo_nome: string
  mb_lidos: number
  somente_resumo: boolean
  aceitar_sem_classe: boolean
  resumo: ResumoDaCarga
  erro: string
  total_publicacoes: number
  total_insumos: number
  total_composicoes: number
  total_analitica: number
  solicitada_por_nome: string
  criada_em: string
  concluida_em: string | null
  em_andamento: boolean
}

export interface EstadoDaCarga {
  fontes: FonteOficial[]
  fontes_com_motor: Fonte[]
  em_andamento: CargaBase | null
  ultima_por_fonte: Record<string, CargaBase>
  teto_mb: number
}
