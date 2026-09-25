export type StatusCronograma = 'rascunho' | 'vigente' | 'substituido'

export type NivelLocal =
  | 'bloco' | 'pavimento' | 'unidade' | 'ambiente'
  | 'frente' | 'trecho' | 'estaca' | 'area'

export type TipoPrecedencia = 'FS' | 'SS' | 'FF' | 'SF'

export type CodigoPosto =
  | 'hoje' | 'semana' | 'plano' | 'medicao' | 'qualidade' | 'seguranca'

export interface StatusModulo {
  modulo: string
  status: string
  fatia: string
  recursos: Record<string, boolean>
}

export interface LocalObra {
  local_id: number
  obra: number
  pai: number | null
  codigo: string
  nome: string
  nivel: NivelLocal
  nivel_rotulo: string
  ordem: number
  profundidade: number
  filhos_count: number
  obra_nome?: string
  unidade_rotulo?: string
  maps_local_rotulo?: string | null
}

export interface ExcecaoCalendario {
  excecao_id: number
  calendario: number
  data: string
  trabalha: boolean
  descricao: string
}

export interface CalendarioTrabalho {
  calendario_id: number
  obra: number | null
  obra_nome?: string
  nome: string
  horas_por_dia: string
  trabalha_segunda: boolean
  trabalha_terca: boolean
  trabalha_quarta: boolean
  trabalha_quinta: boolean
  trabalha_sexta: boolean
  trabalha_sabado: boolean
  trabalha_domingo: boolean
  considera_feriados: boolean
  excecoes: ExcecaoCalendario[]
}

export interface Cronograma {
  cronograma_id: number
  obra: number | null
  obra_nome?: string
  calendario: number | null
  calendario_nome?: string
  versao: number
  status: StatusCronograma
  status_rotulo: string
  descricao: string
  data_inicio: string | null
  termino_calculado: string | null
  calculado_em: string | null
  publicado_em: string | null
  editavel: boolean
  atividades_count: number
  eh_modelo: boolean
  nome_modelo: string | null
  origem: number | null
  base_versao?: number
}

export interface Atividade {
  atividade_id: number
  cronograma: number
  pai: number | null
  codigo: string
  nome: string
  ordem: number
  profundidade: number
  duracao_dias: number
  eh_marco: boolean
  nao_comecar_antes_de: string | null
  inicio_cedo: string | null
  termino_cedo: string | null
  inicio_tarde: string | null
  termino_tarde: string | null
  folga_total: number | null
  folga_livre: number | null
  critica: boolean
  local: number | null
  local_rotulo: string
  etapa: number | null
  etapa_nome?: string
  item_orcado: number | null
  item_orcado_rotulo: string
  responsavel: number | null
  responsavel_nome?: string
  calendario: number | null
  calendario_nome?: string
  tem_filhos: boolean
  peso: string | null
  peso_origem: string
  peso_informado?: string | null
}

export interface Precedencia {
  precedencia_id: number
  origem: number
  destino: number
  tipo: TipoPrecedencia
  atraso_dias: number
}

export interface LinhaDaBase {
  codigo: string
  nome: string
  situacao: 'nova' | 'mantida' | 'atrasada' | 'adiantada'
  base_inicio: string | null
  base_termino: string | null
  inicio: string | null
  termino: string | null
  desvio_dias: number | null
}

export interface ComparacaoComBase {
  tem_base: boolean
  base: { cronograma_id: number; versao: number; termino: string | null } | null
  linhas: LinhaDaBase[]
}

export interface AvancoDaAtividade {
  avanco: number | null
  peso: string | null
  peso_origem: string
  lancamentos: number
}

export interface AvancoDoCronograma {
  por_atividade: Record<string, AvancoDaAtividade>
  fisico: number | null
  financeiro: {
    orcado: string
    realizado: string
    percentual: number | null
    folhas: number
  } | null
}

export interface CoberturaOrcamento {
  [chave: string]: unknown
}

/** O payload do `gantt/` — árvore, setas, linha de base e avanço numa chamada. */
export interface PayloadGantt {
  cronograma: Cronograma
  atividades: Atividade[]
  precedencias: Precedencia[]
  base: ComparacaoComBase
  cobertura_orcamento: CoberturaOrcamento
  avanco: AvancoDoCronograma
}

export interface PontoDeBalanco {
  atividade: number
  codigo: string
  nome: string
  local: number
  local_rotulo: string
  y: number
  inicio: string | null
  fim: string | null
  critica: boolean
}

export interface LinhaDeBalanco {
  servico: number
  codigo: string
  nome: string
  pontos: PontoDeBalanco[]
  dias_por_local: string | null
  locais_por_semana: string | null
}

export interface ConflitoDeEquipe {
  local: number
  local_rotulo: string
  servico_a: string
  servico_b: string
  atividade_a: number
  atividade_b: number
  inicio: string
  fim: string
  dias: number
}

export interface EixoDeBalanco {
  local: number
  codigo: string
  nome: string
  nivel: NivelLocal
  profundidade: number
  y: number
}

export interface PayloadBalanco {
  cronograma: number
  obra: number
  eixo: EixoDeBalanco[]
  linhas: LinhaDeBalanco[]
  /** O **id** do serviço gargalo, e não o objeto — a tela resolve em `linhas`. */
  gargalo: number | null
  conflitos: ConflitoDeEquipe[]
  atividades_sem_local: { atividade: number; codigo: string; nome: string }[]
  locais_alem_do_teto: number
  servicos_alem_do_teto?: number
}

/** O que a paleta de comando e o inspetor manipulam. */
export type Selecao =
  | { tipo: 'atividade'; id: number }
  | { tipo: 'local'; id: number }
  | null

/* --------------------------------------------------------------------------
 * O cockpit — carteira, fila do dia, pulso e busca única
 * ------------------------------------------------------------------------ */

/** Por que um bloco veio vazio, **e a quem pedir**.
 *
 *  O servidor nunca recusa a leitura inteira por falta de uma permissão: o
 *  bloco vem nulo e a razão vem aqui. É a régua omitir × trancar dentro de um
 *  agregado — fila vazia sem explicação é a pior das saídas, porque não parece
 *  falha. */
export interface SemPermissao {
  bloco: string
  o_que: string
  permissao: string
  motivo: string
}

/** A ordem em que uma pendência dói. Vem do servidor para a tela não
 *  reimplementar a régua que decide o que é urgente. */
export type Consequencia =
  | 'prazo_legal' | 'seguranca' | 'dinheiro' | 'compromisso' | 'retrabalho'

/** O assunto de origem. A tela mapeia para o posto que o explica — navegação
 *  é da tela, e por isso o servidor manda a origem e não a rota. */
export type OrigemDaFila =
  | 'seguranca' | 'medicao' | 'programacao' | 'restricao' | 'qualidade'

export type EspecieDoPdca =
  | 'atividade' | 'local' | 'contrato' | 'medicao'
  | 'verificacao' | 'nc' | 'ocorrencia' | 'plano_acao' | 'programacao'
  | 'cronograma' | 'restricao'
  /** As duas do posto da medição: só a fila do dinheiro as produz, e por isso
   *  não estão na busca única nem na fila do dia. */
  | 'liberacao' | 'aditivo'

export interface PrazoDaLinha {
  vence_em: string
  vencido: boolean
  imediata: boolean
  dias_restantes: number
  base_legal: string
}

/** A mesma forma para os onze assuntos — é o que faz onze filas virarem uma. */
export interface LinhaDaFila {
  chave: string
  tipo: EspecieDoPdca
  id: number
  titulo: string
  detalhe: string
  onde: string
  desde: string | null
  dias: number | null
  prazo: PrazoDaLinha | null
  /** Campos próprios de cada assunto (contrato, líquido, gravidade, nc…). */
  [extra: string]: unknown
}

export interface FaixaDaFila {
  codigo: string
  rotulo: string
  consequencia: Consequencia
  /** A frase que vira o botão — fila que não diz o que decidir é contagem. */
  o_que_decidir: string
  origem: OrigemDaFila
  linhas: LinhaDaFila[]
  total: number
  truncada: boolean
}

export interface FilaDoDia {
  obra: number
  hoje: string
  faixas: FaixaDaFila[]
  /** Quantas o servidor varreu — a tela diz "nenhuma das 11 tem alguém
   *  esperando" em vez de abrir em branco. */
  faixas_varridas: number
  total: number
  sem_permissao: SemPermissao[]
}

export interface LeituraDePrazo {
  tem_plano: boolean
  cronograma: number | null
  versao: number | null
  termino: string | null
  base_versao: number | null
  base_termino: string | null
  desvio_dias: number | null
  sem_apuracao_porque: string
}

export interface LeituraDeAvanco {
  fisico: number | null
  financeiro: {
    orcado: string
    realizado: string
    percentual: number | null
    folhas: number
  } | null
  folhas: number
  folhas_apontadas: number
  folhas_sem_peso: number
  ultimo_apontamento: string | null
  sem_apuracao_porque: string
}

export interface PontoDePpc {
  programacao: number
  semana_inicio: string
  comprometidos: number
  cumpridos: number
  ppc: string
  peso_bases: string[]
  vezes_reaberta: number
  encerrada_antes_do_fim: boolean
}

export interface LeituraDePpc {
  ppc: string | null
  semana_inicio: string | null
  comprometidos: number
  cumpridos: number
  peso_bases: string[]
  vezes_reaberta: number
  encerrada_antes_do_fim: boolean
  serie: PontoDePpc[]
  sem_apuracao_porque: string
}

export interface LeituraDeConformidade {
  conformidade: string | null
  conformes: number
  nao_conformes: number
  julgados: number
  sem_apuracao_porque: string
}

export interface LeituraDeSeguranca {
  dias_sem_afastamento: number | null
  ultimo_afastamento: string | null
  ocorrencias_abertas: number
  ocorrencias_registradas: number
  sem_apuracao_porque: string
  /** As duas dividem por homem-hora, que o sistema ainda não apura. Voltam
   *  nulas **com motivo** — zero diria que a obra é segura. */
  taxa_frequencia: null
  taxa_gravidade: null
  taxas_indisponiveis_porque: string
}

export interface PulsoDaObra {
  obra: number
  prazo: LeituraDePrazo | null
  avanco: LeituraDeAvanco | null
  ppc: LeituraDePpc | null
  conformidade: LeituraDeConformidade | null
  seguranca: LeituraDeSeguranca | null
  sem_permissao: SemPermissao[]
}

export interface FatoRecente {
  chave: string
  tipo: EspecieDoPdca
  id: number
  verbo: string
  titulo: string
  quem: string
  quando: string
}

export interface MudancasRecentes {
  obra: number
  dias: number
  desde: string
  fatos: FatoRecente[]
  total: number
  truncada: boolean
  sem_permissao: SemPermissao[]
}

export interface PayloadHoje {
  obra: number
  obra_nome: string
  fila: FilaDoDia
  pulso: PulsoDaObra
  mudancas?: MudancasRecentes
}

export interface Pendencia {
  codigo: string
  rotulo: string
  consequencia: Consequencia
  quantas: number
}

export interface LinhaDaCarteira {
  obra: number
  nome: string
  status_obra: string
  status_rotulo: string
  data_fim_prevista: string | null
  prazo: LeituraDePrazo | null
  avanco: LeituraDeAvanco | null
  ppc: LeituraDePpc | null
  conformidade: LeituraDeConformidade | null
  seguranca: LeituraDeSeguranca | null
  /** **Discriminadas, nunca somadas** — não existe "12 pendências". */
  pendencias: Pendencia[]
  pior_pendencia: Pendencia | null
}

export interface PayloadCarteira {
  obras: LinhaDaCarteira[]
  total: number
  truncada: boolean
  teto: number
  sem_permissao: SemPermissao[]
}

export interface ResultadoDaBusca {
  chave: string
  id: number
  titulo: string
  subtitulo: string
  obra: number | null
  obra_nome: string
  extra: Record<string, unknown>
}

export interface EspecieDaBusca {
  codigo: EspecieDoPdca
  rotulo: string
  resultados: ResultadoDaBusca[]
  truncada: boolean
}

export interface PayloadBusca {
  termo: string
  curta: boolean
  minimo_de_letras: number
  teto_por_especie: number
  especies: EspecieDaBusca[]
  especies_varridas: number
  total: number
  sem_permissao: SemPermissao[]
  aviso?: string
}

/* --------------------------------------------------------------------------
 * O Last Planner — restrição, quadro da semana, PPC e causas
 * ------------------------------------------------------------------------ */

/** As oito famílias de impedimento do *make-ready*. Lista fechada porque o
 *  ranking por tipo é metade do valor do log: com texto livre, "material" e
 *  "materiais" viram duas famílias e o ranking deixa de somar. */
export type TipoRestricao =
  | 'projeto' | 'material' | 'mao_de_obra' | 'equipamento'
  | 'area' | 'licenca' | 'decisao' | 'clima'

export type StatusRestricao = 'aberta' | 'removida' | 'cancelada'

export interface Restricao {
  restricao_id: number
  atividade: number
  atividade_codigo: string
  atividade_nome: string
  obra: number
  local: number | null
  local_rotulo: string
  tipo: TipoRestricao
  tipo_rotulo: string
  descricao: string
  responsavel: string
  prazo: string | null
  /** Negativo é vencida. `null` quando não há prazo — e a tela mostra "sem
   *  prazo", nunca "vencida há 0 dias". */
  dias_para_o_prazo: number | null
  status: StatusRestricao
  status_rotulo: string
  demanda_scm: number | null
  demanda_scm_status?: string
  criada_por: string
  criada_em: string
  removida_em: string | null
  removida_por: string
  nota_remocao: string
}

export type CategoriaDaCausa =
  | 'planejamento' | 'mao_de_obra' | 'material' | 'equipamento'
  | 'projeto' | 'externo' | 'qualidade'

export interface CausaNaoCumprimento {
  causa_id: number
  codigo: string
  nome: string
  categoria: CategoriaDaCausa
  categoria_rotulo: string
  de_fabrica: boolean
  ativo: boolean
}

export type StatusProgramacao = 'rascunho' | 'comprometida' | 'encerrada'

export interface ProgramacaoSemanal {
  programacao_id: number
  obra: number
  obra_nome?: string
  semana_inicio: string
  semana_fim: string
  status: StatusProgramacao
  status_rotulo: string
  nota: string
  criada_por: string
  criada_em: string
  comprometida_em: string | null
  comprometida_por: string
  encerrada_em: string | null
  encerrada_por: string
  /** String, e não número: o DRF serializa `Decimal` assim, e é assim que a
   *  ação `encerrar/` também o devolve. `null` enquanto a semana não encerra —
   *  a tela mostra "sem apuração", nunca 0%. */
  ppc: string | null
  reaberta_em: string | null
  reaberta_por: string
  motivo_reabertura: string
  vezes_reaberta: number
  encerrada_antes_do_fim: boolean
  motivo_encerramento_antecipado: string
}

export interface ItemProgramacao {
  item_programacao_id: number
  programacao: number
  atividade: number
  atividade_codigo: string
  atividade_nome: string
  local: number | null
  local_rotulo: string
  responsavel: string
  percentual_previsto: string | null
  /** Quanto o campo apontou nesta semana. **Não entra no PPC** — é a prova ao
   *  lado dele. `null` é "ninguém apontou", que é diferente de zero. */
  percentual_apontado: string | null
  cumprido: boolean | null
  causa: number | null
  causa_codigo?: string
  causa_nome?: string
  nota: string
  ordem: number
  restricoes_abertas: number
  ncs_abertas: number
  /** Congelado pelo servidor quando o cartão entra no quadro. É o que o PPC
   *  ponderado divide, e a origem viaja junto para o número ter procedência. */
  peso: string | null
  peso_origem: string
  arrastado_de: number | null
  vezes_arrastado: number
}

/** A área de rascunho: o que o plano diz que é desta semana. Sugestão, nunca
 *  imposição — o Last Planner existe porque o plano de meses atrás não sabe da
 *  obra de hoje. */
export interface CandidatoDaSemana {
  atividade: number
  codigo: string
  nome: string
  inicio_previsto: string | null
  fim_previsto: string | null
  critica: boolean
  restricoes_abertas: number
  ncs_abertas: number
  ja_no_quadro: boolean
}

export interface ResultadoDoArrasto {
  arrastados: number
  ja_no_quadro: number
  sem_espaco: number
  programacao_destino: number | null
  destino_fechado: boolean
}

/** O que `ppc/` de uma semana devolve — e o que `encerrar/` devolve de volta. */
export interface ResumoDoPpc {
  programacao: number
  semana_inicio: string
  semana_fim: string
  status: StatusProgramacao
  comprometidos: number
  cumpridos: number
  nao_cumpridos: number
  por_julgar: number
  ppc: string | null
  apurado: boolean
  vezes_reaberta: number
  motivo_reabertura: string
  encerrada_antes_do_fim: boolean
  motivo_encerramento_antecipado: string
  peso_bases: string[]
  peso_total: string
  peso_cumprido: string
  sem_peso: number
  pontos_previstos: string | null
  pontos_apontados: string | null
  arrastados: number
  arrasto?: ResultadoDoArrasto | null
}

export interface LinhaDoRanking {
  causa: number | null
  codigo: string
  nome: string
  categoria: CategoriaDaCausa | null
  ocorrencias: number
  percentual: string
}

export interface LinhaDaCategoria {
  categoria: string
  rotulo: string
  ocorrencias: number
  percentual: string
}

export interface RankingDeCausas {
  total_falhas: number
  causas: LinhaDoRanking[]
  categorias: LinhaDaCategoria[]
}

export interface JulgamentoDeItem {
  item: number
  cumprido: boolean | null
  causa?: number | null
  nota?: string
}

/* --------------------------------------------------------------------------
 * B5 — a frente de quem está no canteiro
 * ------------------------------------------------------------------------ */

export interface BlocoDaFrente<T> {
  codigo: string
  rotulo: string
  /** O verbo que fecha o bloco. Lista que diz o que existe e não diz o que
   *  fazer é inventário. */
  o_que_fazer: string
  linhas: T[]
  total: number
  truncada: boolean
  /** Bloco vazio **com razão**: no celular, lista em branco é indistinguível
   *  de lista que não carregou. */
  vazio_porque: string
}

export interface CompromissoDaFrente {
  item: number
  programacao: number
  obra: number
  obra_nome: string
  atividade: number
  codigo: string
  nome: string
  local: number | null
  local_rotulo: string
  previsto: string | null
  apontado: string | null
  apontou: boolean
  restricoes_abertas: number
  ncs_abertas: number
  vezes_arrastado: number
  cumprido: boolean | null
  status_da_semana: StatusProgramacao
  semana_aberta: boolean
}

export interface TravaDaFrente {
  restricao: number
  obra: number
  atividade: number
  codigo: string
  nome: string
  local_rotulo: string
  tipo: TipoRestricao
  tipo_rotulo: string
  descricao: string
  desde: string | null
  dias: number | null
  prazo: PrazoDaLinha | null
  demanda_scm: number | null
}

export interface ConsertoDaFrente {
  acao: number
  nc: number
  obra: number
  o_que: string
  onde: string
  como: string
  status: string
  status_rotulo: string
  gravidade: string
  gravidade_rotulo: string
  defeito: string
  prazo: PrazoDaLinha | null
}

export interface FichaDaFrente {
  verificacao: number
  obra: number
  modelo_codigo: string
  modelo_nome: string
  onde: string
  desde: string
  dias: number
  por_responder: number
}

export interface PayloadMinhasFrentes {
  quem: string
  obra: number | null
  hoje: string
  semana_inicio: string
  semana_fim: string
  compromissos: BlocoDaFrente<CompromissoDaFrente> | null
  restricoes: BlocoDaFrente<TravaDaFrente> | null
  acoes: BlocoDaFrente<ConsertoDaFrente> | null
  fichas: BlocoDaFrente<FichaDaFrente> | null
  total: number
  blocos_varridos: number
  teto: number
  sem_permissao: SemPermissao[]
  /** Sem nome não há frente, e a frase diz o que fazer a respeito. */
  sem_nome_porque: string
}

export interface ApontamentoAvanco {
  apontamento_id: number
  atividade: number
  atividade_codigo?: string
  atividade_nome?: string
  local: number | null
  local_rotulo?: string
  data: string
  percentual: string
  origem: string
  origem_rotulo?: string
  observacao: string
  foto: string | null
  estorna: number | null
  estornado?: boolean
  apontado_por: string
  registrado_em: string
}

/* --------------------------------------------------------------------------
 * MEDIÇÃO — o contrato, o boletim e o dinheiro (F.4)
 *
 * **Todo valor monetário viaja como string**, e não como `number`: o `float`
 * do JSON tem 53 bits de mantissa e não representa centavo exatamente. É por
 * isso que o DRF serializa decimal como string, e é por isso que aqui o tipo é
 * `string` — quem formata é o `money.ts`, nunca um `parseFloat`.
 * ------------------------------------------------------------------------ */

export type RegimeContrato = 'unitario' | 'global' | 'administracao'

export type StatusContrato =
  | 'rascunho' | 'vigente' | 'suspenso' | 'encerrado' | 'cancelado'

/** O que o dinheiro retido **é** — e isto governa quando ele volta e quem
 *  libera. Guardar só o percentual deixaria a devolução sem o que declarar. */
export type NaturezaRetencao = 'nenhuma' | 'caucao' | 'garantia' | 'tecnica'

export type StatusMedicao =
  | 'rascunho' | 'em_aprovacao' | 'aprovada' | 'reprovada' | 'cancelada'

export type StatusAditivo =
  | 'rascunho' | 'em_aprovacao' | 'aprovado' | 'reprovado' | 'cancelado'

export type TipoDeducao =
  | 'imposto' | 'adiantamento' | 'multa' | 'material' | 'outro'

/** Retido − liberado, e as três parcelas juntas.
 *
 *  As parcelas viajam, e não só o saldo, porque a tela precisa poder explicar
 *  o número: "R$ 12.400 retidos, R$ 4.000 já liberados" é uma frase que o
 *  gestor confere contra o extrato. */
export interface RetencaoDoContrato {
  retido: string
  liberado: string
  disponivel: string
  natureza: string
  condicao: string
}

/** De quando a **próxima** medição deveria falar.
 *
 *  Medição de obra é uma corrente: o período começa no dia seguinte ao fim do
 *  anterior. A tela não calcula isso — um "primeiro do mês → hoje" montado no
 *  navegador produz sobreposição no mês medido quinzenalmente e buraco no mês
 *  em que a medição atrasou. */
export interface PeriodoSugerido {
  inicio: string
  fim: string
  ultima_medicao: {
    medicao_id: number
    numero: number
    periodo_fim: string
    status: StatusMedicao
  } | null
  lacuna_dias: number
}

/** Contratado × medido × saldo × retenção — derivado inteiro no servidor. */
export interface SaldoDoContrato {
  contrato_id: number
  regime: RegimeContrato
  valor_contratado: string
  valor_original: string
  valor_aditivado: string
  medido_aprovado: string
  medido_em_aprovacao: string
  medido_rascunho: string
  deducoes_aprovadas: string
  material_estocado: string
  saldo: string
  retencao: RetencaoDoContrato
  itens: number
  itens_fechados: number
  medicoes: number
  aditivos: number
  aditivos_abertos: number
  periodo_sugerido: PeriodoSugerido
}

export interface LinhaDeContrato {
  contrato: number
  numero: string
  objeto: string
  fornecedor: number
  fornecedor_nome: string
  regime: RegimeContrato
  regime_rotulo: string
  status: StatusContrato
  status_rotulo: string
  data_inicio: string
  data_fim: string | null
  regime_publico: boolean
  /** A trava da planilha vem resolvida do servidor — a tela lê a resposta em
   *  vez de reimplementar a condição (convenções §11). */
  planilha_editavel: boolean
  planilha_fechada_porque: string
  saldo: SaldoDoContrato
}

export interface CarteiraDeContratos {
  linhas: LinhaDeContrato[]
  total: number
  truncada: boolean
  teto: number
  sem_permissao: SemPermissao[]
}

/** B3 — o que espera alguém no caminho do dinheiro.
 *
 *  Quatro blocos, e **todos são documento parado**: nenhum é contagem, e não
 *  existe faixa de "contrato sem medir há N dias" — de quanto em quanto tempo
 *  se mede é cláusula combinada com cada empreiteiro, e o contrato não guarda
 *  esse campo. */
export interface FilaDaMedicao {
  obra: number
  medicoes_em_rascunho: LinhaDaFila[]
  medicoes_a_atestar: LinhaDaFila[]
  retencoes_a_liberar: LinhaDaFila[]
  aditivos_a_decidir: LinhaDaFila[]
  /** Os totais **ao lado** das listas, porque as listas vêm cortadas pelo
   *  teto: contar `linhas.length` na tela daria o número errado, e número
   *  errado numa fila de dinheiro é pior que número nenhum. */
  totais: {
    medicoes_em_rascunho: number
    medicoes_a_atestar: number
    retencoes_a_liberar: number
    aditivos_a_decidir: number
  }
  total: number
  sem_permissao: SemPermissao[]
}

export interface PayloadPostoMedicao {
  obra: number
  obra_nome: string
  contratos: CarteiraDeContratos
  fila: FilaDaMedicao
}

export interface ContratoObra {
  contrato_id: number
  obra: number
  obra_nome: string
  fornecedor: number
  fornecedor_nome: string
  numero: string
  objeto: string
  regime: RegimeContrato
  regime_rotulo: string
  valor_global: string | null
  taxa_administracao: string | null
  data_inicio: string
  data_fim: string | null
  garantia_meses: number
  retencao_percentual: string
  retencao_natureza: string
  retencao_natureza_rotulo: string
  retencao_condicao_liberacao: string
  regime_publico: boolean
  limite_acrescimo_percentual: string | null
  prazo_pagamento_dias: number
  status: StatusContrato
  status_rotulo: string
  observacao: string
  itens_count: number
  medicoes_count: number
  planilha_editavel: boolean
  planilha_fechada_porque: string
}

export interface ItemContrato {
  item_id: number
  contrato: number
  codigo: string
  descricao: string
  unidade: string
  quantidade_contratada: string
  preco_unitario: string
  valor_contratado: string
  ordem: number
  atividade: number | null
  atividade_nome: string | null
  item_orcado: number | null
  item_orcado_descricao: string | null
  /** "Sem vínculo" é estado que o gestor precisa **ver** no cadastro do item,
   *  e não descobrir na hora de medir, quando a linha não recebe proposta. */
  tem_vinculo_de_avanco: boolean
  /** O que vale **hoje** — original + aditivos aprovados. Num contrato aditado
   *  a `quantidade_contratada` é o do dia da assinatura e já não governa. */
  quantidade_atual: string
  quantidade_aditivada: string
  aditivo_origem: number | null
}

/** Uma assinatura da escada — quem decidiu, quando e com que autoridade. */
export interface AtestoDaEscada {
  atesto_id: number
  nivel_ordem: number
  nivel_nome: string
  decisao: string
  autor: string
  permissao_conferida: string
  decidido_em: string
  observacao: string
}

/** O degrau em que o documento está parado — para a tela dizer **de quem** se
 *  espera a decisão, em vez de um "em aprovação" que não ajuda ninguém. */
export interface EscadaDoDocumento {
  pedido_id: number
  estado: string
  nivel: string | null
  permissao_exigida: string | null
  solicitante: string
  atestos: AtestoDaEscada[]
}

export interface TotaisDaMedicao {
  executado: string
  material_estocado: string
  bruto: string
  retencao: string
  retencao_percentual: string
  total_deducoes: string
  liquido: string
  deducoes: {
    deducao_id: number
    tipo: TipoDeducao
    tipo_rotulo: string
    descricao: string
    percentual: string | null
    base_calculo: string | null
    valor: string
  }[]
}

export interface DeducaoMedicao {
  deducao_id: number
  medicao: number
  tipo: TipoDeducao
  tipo_rotulo: string
  descricao: string
  base_calculo: string | null
  percentual: string | null
  valor: string | null
  valor_aplicado: string
}

export interface ItemMedicao {
  item_medicao_id: number
  medicao: number
  item_contrato: number
  codigo: string
  descricao: string
  unidade: string
  quantidade: string
  quantidade_proposta: string | null
  quantidade_estocada: string
  preco_unitario: string
  valor: string
  percentual_avanco_periodo: string | null
  origem: string | null
  origem_rotulo: string | null
  observacao: string
  /** A diferença entre o que o sistema propôs e o que o gestor confirmou — é
   *  o que torna o ajuste auditável na tela. */
  ajuste: string | null
}

/** O estado do título no ERP, visto de dentro do PDCA.
 *
 *  Existe para o botão "Cancelar" saber o que vai acontecer **antes** de
 *  alguém clicar: com o título aberto ele cancela os dois; com baixa em cima,
 *  a medição só se conserta por retificadora. */
export interface TituloDoErp {
  conta_pagar: number
  status: string
  status_rotulo: string
  valor: string
  valor_pago: string
  saldo_aberto: string
  data_vencimento: string
  /** A pergunta que decide o botão: cancelar a medição leva o título junto, ou
   *  o dinheiro já saiu e só a retificadora conserta. */
  pode_cancelar: boolean
}

export interface Medicao {
  medicao_id: number
  contrato: number
  contrato_numero: string
  contrato_obra: number
  fornecedor_nome: string
  obra_nome: string
  regime: RegimeContrato
  numero: number
  periodo_inicio: string
  periodo_fim: string
  status: StatusMedicao
  status_rotulo: string
  apurada_em: string | null
  apurada_por: string
  congelada_em: string | null
  custo_reembolsavel: string | null
  custo_origem: string | null
  custo_origem_rotulo: string | null
  retencao_percentual_aplicado: string
  taxa_administracao_aplicada: string | null
  observacao: string
  retifica: number | null
  totais: TotaisDaMedicao
  escada: EscadaDoDocumento | null
  /** Só no documento aberto: a lista não paga uma consulta por linha. */
  itens?: ItemMedicao[]
  deducoes?: DeducaoMedicao[]
  titulo_erp?: TituloDoErp | null
}

/** De onde saiu a proposta de uma linha, atividade por atividade.
 *
 *  Vem junto da grade porque sai da mesma consulta — pedi-la depois seria uma
 *  chamada por linha clicada. É o que torna a apuração automática conferível
 *  em vez de caixa preta. */
export interface MemoriaDaLinha {
  atividade: number
  codigo: string
  nome: string
  peso: string | null
  percentual: string | null
  [extra: string]: unknown
}

/** Uma linha da grade da medição — as dez colunas da G703, **já calculadas**.
 *
 *  A tela não recalcula nenhuma delas. A primeira escrita desta página montava
 *  `saldo = contratado − já medido` no navegador, e quem entrasse pelo link
 *  direto de uma medição via "já medido" negativo e saldo acima do contratado. */
export interface LinhaDaGradeDeMedicao {
  item_contrato_id: number
  codigo: string
  descricao: string
  unidade: string
  quantidade_contratada: string
  quantidade_original: string
  quantidade_aditivada: string
  nasceu_de_aditivo: boolean
  quantidade_ja_medida: string
  saldo: string
  quantidade_proposta: string
  percentual_avanco_periodo: string | null
  criterio: string
  limitada_pelo_saldo: boolean
  preco_unitario: string
  atividades: number[]
  memoria: MemoriaDaLinha[]
  quantidade_medida: string
  quantidade_estocada: string
  estocado_anterior: string
  origem: string | null
  observacao: string
}

/** O denominador da honestidade: quanto da proposta o sistema **não**
 *  conseguiu calcular. Sem isto, zeros de "sem vínculo" ficam
 *  indistinguíveis de zeros de "não andou". */
export interface CoberturaDaProposta {
  itens: number
  sem_vinculo: number
  codigos_sem_vinculo: string[]
}

export interface PropostaDeMedicao {
  contrato_id: number
  regime: RegimeContrato
  periodo: { inicio: string; fim: string }
  linhas: LinhaDaGradeDeMedicao[]
  cobertura: CoberturaDaProposta
}

/** A grade de um documento que **existe** — a prévia amarrada ao período e ao
 *  estado do boletim, com os totais congelados e o degrau da escada. */
export interface ContextoDeMedicao extends PropostaDeMedicao {
  medicao_id: number
  numero: number
  status: StatusMedicao
  /** **A trava vem do servidor.** A tela lê `editavel` em vez de comparar o
   *  status por conta própria: prop de interface não protege a API. */
  editavel: boolean
  totais: TotaisDaMedicao
  escada: EscadaDoDocumento | null
}

export interface ItemAditivo {
  item_aditivo_id: number
  aditivo: number
  item_contrato: number | null
  item_contrato_codigo: string | null
  acao: string
  acao_rotulo: string
  codigo: string
  descricao: string
  unidade: string
  quantidade: string
  preco_unitario: string
  valor: string
}

export interface AditivoContrato {
  aditivo_id: number
  contrato: number
  contrato_numero: string
  numero: number
  objeto: string
  justificativa: string
  data_assinatura: string | null
  nova_data_fim: string | null
  status: StatusAditivo
  status_rotulo: string
  valor_total: string
  percentual_sobre_original: string | null
  criado_por: string
  criado_em: string
  aplicado_em: string | null
  escada: EscadaDoDocumento | null
  itens?: ItemAditivo[]
}

export interface LiberacaoRetencao {
  liberacao_id: number
  contrato: number
  valor: string
  data: string
  condicao_atendida: string
  status: StatusMedicao
  status_rotulo: string
  solicitada_por: string
  criado_em: string
  escada: EscadaDoDocumento | null
}

/* --------------------------------------------------------------------------
 * Os postos da qualidade e da segurança (B8, B9)
 * ------------------------------------------------------------------------ */

export type DominioVerificacao = 'qualidade' | 'seguranca' | 'ambiental' | 'entrega'
export type ResultadoItem = 'pendente' | 'conforme' | 'nao_conforme' | 'nao_aplicavel'
export type GravidadeNc = 'menor' | 'maior' | 'critica'
export type StatusNc = 'aberta' | 'em_tratamento' | 'encerrada' | 'cancelada'
export type StatusVerificacao = 'em_andamento' | 'concluida'
export type TipoPlanoAcao = 'corretiva' | 'preventiva'
export type StatusPlanoAcao = 'planejada' | 'em_execucao' | 'concluida' | 'cancelada'

export interface ConformidadePorDominio {
  dominio: DominioVerificacao
  rotulo: string
  conformes: number
  nao_conformes: number
  conformidade: string
}

/** A pergunta que mais reprova — **cumulativa**, e partida pela situação de
 *  hoje: sem a partição, uma reprova tratada semana passada se lê como
 *  problema de agora. */
export interface ItemQueMaisReprova {
  item_modelo: number
  texto: string
  modelo_codigo: string
  reprovas: number
  em_aberto: number
  encerradas: number
  sem_nc: number
  percentual: string
}

export interface NcsPorGravidade {
  gravidade: GravidadeNc
  rotulo: string
  abertas: number
  encerradas: number
}

export interface PainelDeConformidade {
  obra: number
  fichas_concluidas: number
  por_dominio: ConformidadePorDominio[]
  itens_que_mais_reprovam: ItemQueMaisReprova[]
  reprovas_sem_modelo: number
  ncs_por_gravidade: NcsPorGravidade[]
  ncs_encerradas: number
  ncs_abertas: number
}

export interface PayloadPostoQualidade {
  obra: number
  obra_nome: string
  fila: FilaDoDia
  painel: PainelDeConformidade | null
  sem_permissao: SemPermissao[]
}

export interface IndicadoresDeSsma {
  por_tipo: Partial<Record<TipoOcorrencia, number>>
  acidentes: number
  quase_acidentes: number
  com_afastamento: number
  sem_afastamento: number
  obitos: number
  nao_classificadas: number
  dias_perdidos: number
  dias_debitados: number
  dds_encerrados: number
  avisos_por_acidente: number | null
  /** Dividem por homem-hora, que o sistema não apura: nulas **com motivo**. */
  taxa_frequencia: null
  taxa_gravidade: null
  taxas_indisponiveis_porque: string
}

export interface FrenteInterditada {
  ocorrencia: number
  restricao: number
  tipo_rotulo: string
  descricao: string
  atividade_nome: string
  local_rotulo: string
  desde: string | null
}

export interface PayloadPostoSeguranca {
  obra: number
  obra_nome: string
  fila: FilaDoDia
  indicadores: IndicadoresDeSsma | null
  frentes_interditadas: FrenteInterditada[]
  sem_permissao: SemPermissao[]
}

/* --- a máquina de verificação --- */

export interface ItemModeloVerificacao {
  item_modelo_id: number
  modelo: number
  ordem: number
  texto: string
  criterio: string
  obrigatorio: boolean
  exige_foto: boolean
}

export interface ModeloVerificacao {
  modelo_id: number
  codigo: string
  nome: string
  dominio: DominioVerificacao
  dominio_rotulo: string
  descricao: string
  ativo: boolean
  criado_por: string
  criado_em: string
  itens_count: number
  /** Quantas fichas já saíram dele — é o que decide se ele se apaga ou se
   *  desativa. */
  aplicacoes: number
  itens?: ItemModeloVerificacao[]
}

/** As contagens e a conformidade — **derivadas**, e nulas enquanto nada foi
 *  julgado: "sem apuração", nunca 0%. */
export interface ResultadoDaVerificacao {
  verificacao: number
  status: StatusVerificacao
  total: number
  conformes: number
  nao_conformes: number
  nao_aplicaveis: number
  pendentes: number
  conformidade: string | null
  apurada: boolean
}

export interface Verificacao {
  verificacao_id: number
  modelo: number
  modelo_codigo: string
  modelo_nome: string
  dominio: DominioVerificacao
  dominio_rotulo: string
  obra: number
  obra_nome: string
  local: number | null
  local_rotulo: string | null
  atividade: number | null
  atividade_codigo: string | null
  atividade_nome: string | null
  inspetor: string
  data: string
  status: StatusVerificacao
  status_rotulo: string
  nota: string
  criada_por: string
  criada_em: string
  concluida_em: string | null
  concluida_por: string
  resultado: ResultadoDaVerificacao | null
}

/** Uma resposta. A pergunta e o critério vêm **congelados**: mudar o modelo
 *  depois não reescreve a inspeção. */
export interface ItemVerificacao {
  item_verificacao_id: number
  verificacao: number
  item_modelo: number | null
  ordem: number
  texto: string
  criterio: string
  obrigatorio: boolean
  exige_foto: boolean
  resultado: ResultadoItem
  resultado_rotulo: string
  observacao: string
  gravidade: GravidadeNc | null
  gravidade_rotulo: string
  foto: string | null
  respondido_em: string | null
  respondido_por: string
  /** A NC que este item gerou — o laço visível na própria ficha. */
  nc: number | null
}

export interface ReprovadoSemNc {
  item_verificacao_id: number
  ordem: number
  texto: string
  observacao: string
  gravidade: GravidadeNc | null
  gravidade_rotulo: string
}

export interface ConclusaoDaVerificacao {
  resultado: ResultadoDaVerificacao
  reprovados_sem_nc: ReprovadoSemNc[]
  verificacao_dados: Verificacao
}

/* --- a não-conformidade e o laço --- */

export interface PlanoAcao {
  plano_id: number
  nao_conformidade: number
  tipo: TipoPlanoAcao
  tipo_rotulo: string
  o_que: string
  por_que: string
  onde: string
  quando: string | null
  quem: string
  como: string
  quanto: string
  status: StatusPlanoAcao
  status_rotulo: string
  /** Negativo = vencido; nulo = sem prazo ou já fechado. */
  dias_para_o_prazo: number | null
  concluida_em: string | null
  concluida_por: string
  criada_por: string
  criada_em: string
}

export interface VerificacaoEficacia {
  eficacia_id: number
  nao_conformidade: number
  data: string
  eficaz: boolean
  evidencia: string
  foto: string | null
  verificada_por: string
  verificada_em: string
}

/** O que falta na NC, decidido pelo servidor — a tela não reimplementa a
 *  regra do encerramento. */
export interface EstadoDaNc {
  acoes: number
  acoes_concluidas: number
  acoes_vencidas: number
  tem_preventiva: boolean
  eficacia_verificada: boolean
  eficaz: boolean | null
  pode_encerrar: boolean
  falta: string
}

export interface NaoConformidade {
  nc_id: number
  obra: number
  obra_nome: string
  local: number | null
  local_rotulo: string | null
  atividade: number | null
  atividade_codigo: string | null
  atividade_nome: string | null
  item_verificacao: number | null
  verificacao: number | null
  gravidade: GravidadeNc
  gravidade_rotulo: string
  descricao: string
  foto: string | null
  marcacao_prancheta: number | null
  marcacao_guid: string | null
  restricao: number | null
  restricao_status: string | null
  status: StatusNc
  status_rotulo: string
  aberta_por: string
  aberta_em: string
  encerrada_em: string | null
  encerrada_por: string
  nota_encerramento: string
  estado: EstadoDaNc
  acoes?: PlanoAcao[]
  eficacias?: VerificacaoEficacia[]
}

/* --- a SSMA --- */

export type TipoOcorrencia =
  | 'quase_acidente' | 'incidente' | 'acidente_tipico'
  | 'acidente_trajeto' | 'doenca_ocupacional'
export type ClassificacaoOcorrencia =
  | 'pendente' | 'sem_afastamento' | 'com_afastamento' | 'obito'
export type StatusOcorrencia = 'aberta' | 'em_investigacao' | 'encerrada' | 'cancelada'
export type TipoCat = 'inicial' | 'reabertura' | 'obito'
export type EspecieAnexo = 'cena' | 'atestado' | 'boletim' | 'lista_presenca' | 'outro'

export interface ParticipanteDds {
  participante_id: number
  dds: number
  funcionario: number | null
  funcionario_nome: string | null
  nome: string
  presente: boolean
  assinou: boolean
}

export interface DialogoSeguranca {
  dds_id: number
  obra: number
  obra_nome: string
  local: number | null
  local_rotulo: string | null
  atividade: number | null
  data: string
  tema: string
  assunto: string
  duracao_min: number | null
  responsavel: number | null
  responsavel_nome: string
  responsavel_label: string
  status: 'rascunho' | 'encerrado'
  status_rotulo: string
  encerrado_em: string | null
  encerrado_por: string
  /** A entrada do Diário de Obra que o encerramento escreveu. */
  diario: number | null
  registrado_por: string
  criado_em: string
  participantes: ParticipanteDds[]
  presentes: number
}

/** O prazo da CAT, **decidido pelo servidor** — e o que ele não sabe
 *  (`feriados_carregados`) vem declarado. */
export type PrazoDaCat =
  | { exige: false; motivo: string }
  | {
      exige: true
      imediata: boolean
      vence_em: string
      emitida: boolean
      vencido: boolean
      feriados_carregados: boolean
      base_legal: string
    }

export interface AnexoOcorrencia {
  anexo_id: number
  ocorrencia: number
  arquivo: string | null
  especie: EspecieAnexo
  especie_rotulo: string
  descricao: string
  enviado_por: string
  enviado_em: string
}

export interface OcorrenciaResumo {
  ocorrencia_id: number
  obra: number
  local: number | null
  local_rotulo: string | null
  atividade: number | null
  ocorrido_em: string
  tipo: TipoOcorrencia
  tipo_rotulo: string
  descricao: string
  classificacao: ClassificacaoOcorrencia
  classificacao_rotulo: string
  status: StatusOcorrencia
  cat_emitida_em: string | null
  restricao: number | null
  nao_conformidade: number | null
  exige_cat: boolean
}

export interface Ocorrencia extends OcorrenciaResumo {
  obra_nome: string
  atividade_codigo: string | null
  agente_causador: string
  situacao_geradora: string
  houve_registro_policial: boolean
  horas_trabalhadas_antes: string | null
  ultimo_dia_trabalhado: string | null
  acidentado: number | null
  acidentado_nome: string
  acidentado_label: string
  parte_do_corpo: string
  lateralidade: string
  /** O bloco clínico: vem mascarado para quem não tem o verbo clínico. */
  natureza_lesao: string | null
  cid10: string | null
  houve_internacao: boolean
  atestado_dias: number | string | null
  dias_perdidos: number | null
  dias_debitados: number | null
  classificada_em: string | null
  classificada_por: string
  cat_tipo: TipoCat | ''
  cat_protocolo: string
  cat_registrada_por: string
  restricao_status: string | null
  nc_status: StatusNc | null
  status_rotulo: string
  registrada_por: string
  registrada_em: string
  encerrada_em: string | null
  encerrada_por: string
  nota_encerramento: string
  anexos: AnexoOcorrencia[]
  prazo_cat: PrazoDaCat
}

export interface EpiVencido {
  disponivel: boolean
  motivo?: string
  vencidos: {
    entrega: number
    colaborador: string
    item: string
    ca_numero: string
    ca_validade: string | null
    troca_prevista: string | null
  }[]
  total?: number
  observacao?: string
}
