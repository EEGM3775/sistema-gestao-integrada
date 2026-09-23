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
