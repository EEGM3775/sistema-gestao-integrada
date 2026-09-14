export interface Paginated<T> { count: number; next: string | null; previous: string | null; results: T[] }

export type StatusCronograma = 'rascunho' | 'vigente' | 'substituido'
export type TipoPrecedencia = 'FS' | 'SS' | 'FF' | 'SF'
export type OrigemPeso = 'orcado' | 'informado' | ''

export interface StatusModulo {
  modulo: string
  status: string
  fatia: string
  recursos: {
    locais: boolean
    calendario: boolean
    cronograma: boolean
    modelo: boolean
    avanco: boolean
    medicao: boolean
  }
  /** Os tetos que a **tela** precisa respeitar antes de mandar a requisição.
   *  Vêm do servidor de propósito: quem decide o número é o dono, e o cliente
   *  lê o que vale hoje em vez de carregar uma cópia que envelhece no bundle. */
  tetos: {
    linhas_por_lote: number
    atividades_por_cronograma: number
    profundidade_wbs: number
    apontamentos_por_lote: number
  }
}

export interface Cronograma {
  cronograma_id: number
  obra: number
  obra_nome: string
  descricao: string
  versao: number
  status: StatusCronograma
  status_rotulo: string
  editavel: boolean
  data_inicio: string
  calendario: number | null
  calendario_nome: string | null
  origem: number | null
  base_versao: number | null
  motivo_replanejamento: string
  publicado_em: string | null
  publicado_por: string
  calculado_em: string | null
  termino_calculado: string | null
  atividades_count: number
  /** PDCA.1b — o plano promovido a padrão da empresa, reaplicável em obra nova. */
  eh_modelo: boolean
  nome_modelo: string
}

export interface Atividade {
  atividade_id: number
  cronograma: number
  pai: number | null
  codigo: string
  nome: string
  ordem: number
  profundidade: number
  duracao_dias: number | null
  eh_marco: boolean
  nao_comecar_antes_de: string | null
  calendario: number | null
  calendario_nome: string | null
  local: number | null
  local_rotulo: string
  etapa: number | null
  etapa_nome: string | null
  item_orcado: number | null
  item_orcado_rotulo: string
  responsavel: number | null
  responsavel_nome: string | null
  peso: string | null
  peso_origem: OrigemPeso
  /** O peso que o planejador digita — o campo **gravável**. Havendo vínculo com
   *  o orçamento ele é ignorado, e a grade diz isso em vez de escondê-lo. */
  peso_informado: string | null
  tem_filhos: boolean
  inicio_cedo: string | null
  termino_cedo: string | null
  inicio_tarde: string | null
  termino_tarde: string | null
  folga_total: number | null
  folga_livre: number | null
  critica: boolean
  observacao: string
}

export interface Precedencia {
  precedencia_id: number
  origem: number
  destino: number
  origem_codigo: string
  destino_codigo: string
  tipo: TipoPrecedencia
  tipo_rotulo: string
  atraso_dias: number
}

export type SituacaoNaBase = 'mantida' | 'atrasada' | 'adiantada' | 'nova' | 'removida'

export interface LinhaDaBase {
  codigo: string
  nome: string
  situacao: SituacaoNaBase
  base_inicio: string | null
  base_termino: string | null
  inicio: string | null
  termino: string | null
  desvio_dias: number | null
}

export interface ComparacaoBase {
  tem_base: boolean
  base: { cronograma_id: number; versao: number; termino: string | null } | null
  linhas: LinhaDaBase[]
}

export interface CoberturaOrcamento {
  folhas: number
  com_item_orcado: number
  com_peso_informado: number
  sem_peso: number
  valor_orcado_vinculado: string
  cobertura: number | null
}

export interface ResultadoCpm {
  atividades: number
  folhas: number
  precedencias: number
  inicio: string
  termino: string
  duracao_dias_uteis: number | null
  criticas: number[]
  caminho_critico: string[]
  segundos: number
  feriados_sincronizados: boolean
}

export interface PayloadGantt {
  cronograma: Cronograma
  atividades: Atividade[]
  precedencias: Precedencia[]
  base: ComparacaoBase
  cobertura_orcamento: CoberturaOrcamento
  /** PDCA.2 — o avanço viaja junto das datas, pelo mesmo motivo que elas: a
   *  barra mostra o executado dentro do previsto, e uma segunda chamada faria a
   *  grade desenhar duas vezes. */
  avanco: AvancoDoCronograma
}

export interface ObraOpt { obra_id: number; nome_obra: string }

// ---------------------------------------------------------------------------
// A grade da WBS — a planilha que o planejador opera o dia inteiro
// ---------------------------------------------------------------------------

/** As colunas **graváveis** da grade. A ordem aqui é a ordem em que Tab anda. */
export type CampoEditavel =
  | 'codigo' | 'nome' | 'duracao_dias' | 'nao_comecar_antes_de'
  | 'predecessoras' | 'peso_informado' | 'observacao'

/** Toda coluna que a grade sabe desenhar — graváveis e derivadas. Quem escolhe
 *  quais aparecem é o usuário, e a escolha vive no navegador dele. */
export type ChaveColuna =
  | CampoEditavel
  | 'inicio_cedo' | 'termino_cedo' | 'inicio_tarde' | 'termino_tarde'
  | 'folga_total' | 'folga_livre' | 'peso' | 'local' | 'etapa'
  | 'item_orcado' | 'responsavel' | 'calendario'

export interface ColunaGrade {
  chave: ChaveColuna
  rotulo: string
  /** Cabeçalho curto, para a coluna estreita não quebrar o alinhamento. */
  curto?: string
  largura: number
  alinhamento: 'left' | 'right' | 'center'
  editavel: boolean
  /** Coluna que só faz sentido depois do CPM — some com o aviso certo. */
  derivada?: boolean
}

/** Uma célula colada (ou digitada) antes de virar chamada de API. */
export interface EdicaoCelula {
  atividade: Atividade
  campo: CampoEditavel
  valor: string
}

// ---------------------------------------------------------------------------
// Leitura derivada — o que a tela calcula a partir do plano já calculado
// ---------------------------------------------------------------------------

export interface EstatisticasPlano {
  atividades: number
  folhas: number
  sinteticas: number
  marcos: number
  criticas: number
  precedencias: number
  /** Precedências por folha: rede frouxa (< 1) é cronograma de barras
   *  disfarçado de CPM, e o planejador precisa saber disso. */
  densidade: number | null
  folhasSemLigacao: number
  inicio: string | null
  termino: string | null
  duracaoDiasCorridos: number | null
  /** Folga total média das folhas não críticas. */
  folgaMedia: number | null
  comRestricaoDeData: number
}

// ---------------------------------------------------------------------------
// Desfazer/refazer — a rede de segurança de quem arrasta barra
// ---------------------------------------------------------------------------

/** Um passo desfazível. `fazer` e `desfazer` são as **duas chamadas inversas**
 *  já prontas: a pilha não sabe o que é uma atividade, só como refazer e como
 *  voltar. Quem monta o par é quem conhece o gesto. */
export interface Comando {
  rotulo: string
  fazer: () => Promise<void>
  desfazer: () => Promise<void>
}

// ---------------------------------------------------------------------------
// Vínculos com outros módulos — o id sempre viaja com o rótulo resolvido
// ---------------------------------------------------------------------------

export interface LocalOpt { local_id: number; codigo: string; nome: string; nivel: string; profundidade: number }
export interface EtapaOpt { etapa_id: number; nome_etapa: string }
export interface OrcamentoOpt { orcamento_id: number; descricao: string; versao: number; status: string }
export interface ItemOrcadoOpt {
  item_orcado_id: number
  codigo_eap: string
  descricao: string
  unidade: string
  total_com_bdi: string
  tipo_linha: string
}
export interface ResponsavelOpt { funcionario_id: number; nome_completo: string }

// ---------------------------------------------------------------------------
// Plano modelo, escrita em lote e expediente
// ---------------------------------------------------------------------------

export interface AplicacaoDeModelo {
  obra: number
  data_inicio: string
  descricao?: string
  calendario?: number | null
}

export interface EdicaoEmLote {
  atividade: number
  campos: Record<string, unknown>
}

export interface ResultadoDoLote {
  atividades: number
  renomeadas: number
  teto: number
}

export interface ResultadoDaRenumeracao {
  mudancas: number
  aplicadas: number
  simulado: boolean
}

export interface Calendario {
  calendario_id: number
  nome: string
  obra: number | null
  obra_nome: string | null
  padrao: boolean
  ativo: boolean
  horas_por_dia: string
  considera_feriados: boolean
  uf: string
  ibge: string
  trabalha_segunda: boolean
  trabalha_terca: boolean
  trabalha_quarta: boolean
  trabalha_quinta: boolean
  trabalha_sexta: boolean
  trabalha_sabado: boolean
  trabalha_domingo: boolean
  excecoes: ExcecaoCalendario[]
}

export interface ExcecaoCalendario {
  excecao_id: number
  calendario: number
  data: string
  trabalha: boolean
  motivo: string
}

export interface ContagemDeDiasUteis {
  calendario: number
  inicio: string
  fim: string
  dias_uteis: number
  dias_corridos: number
  feriados: { data: string; nome: string }[]
  /** A tabela de feriados é global e nasce vazia. Sem este campo, um calendário
   *  que promete considerá-los devolve a conta sem eles e ninguém fica sabendo. */
  feriados_sincronizados: boolean
}

/** Os recortes que o planejador usa para achar o que está errado no próprio
 *  plano. Não são "filtros de tabela": cada um responde a uma pergunta que se
 *  faz olhando um cronograma grande e desconfiando dele. */
export type Filtro =
  | 'criticas'      // o que não tem folga
  | 'atrasadas'     // o que escorregou contra a linha de base
  | 'sem_rede'      // folha sem predecessora nem sucessora — quase sempre esquecimento
  | 'sem_peso'      // folha que não pondera o avanço de ninguém
  | 'com_restricao' // o que está ancorado por data, e não pela rede
  | 'marcos'        // os instantes que se cobra em reunião

export const ROTULOS_DE_FILTRO: Record<Filtro, { curto: string; ajuda: string }> = {
  criticas: { curto: 'Críticas', ajuda: 'Sem folga: atrasou, atrasou a obra' },
  atrasadas: { curto: 'Atrasadas', ajuda: 'Escorregaram contra a linha de base' },
  sem_rede: { curto: 'Sem ligação', ajuda: 'Folhas soltas — flutuam no plano' },
  sem_peso: { curto: 'Sem peso', ajuda: 'Não ponderam o avanço de ninguém' },
  com_restricao: { curto: 'Com restrição', ajuda: 'Ancoradas por data, não pela rede' },
  marcos: { curto: 'Marcos', ajuda: 'Os instantes que se cobra em reunião' },
}

// ---------------------------------------------------------------------------
// PDCA.2 — o avanço apontado
// ---------------------------------------------------------------------------

export type OrigemApontamento = 'web' | 'whatsapp' | 'app'

/** Uma linha do livro-razão do avanço. **Não tem verbo de edição** de propósito:
 *  a API não expõe `PATCH` nem `DELETE`, e corrigir é estornar. */
export interface Apontamento {
  apontamento_id: number
  atividade: number
  atividade_codigo: string
  atividade_nome: string
  local: number | null
  local_rotulo: string
  data: string
  /** O **delta** em pontos percentuais, negativo no estorno. */
  percentual: string
  origem: OrigemApontamento
  origem_rotulo: string
  observacao: string
  foto: string | null
  estorna: number | null
  estornado: boolean
  apontado_por: string
  registrado_em: string
}

/** O avanço de uma atividade — e o peso com que ela pondera o pai.
 *  `avanco: null` é "sem apuração", que é diferente de zero. */
export interface AvancoDaAtividade {
  avanco: number | null
  peso: string | null
  peso_origem: 'orcado' | 'informado' | 'derivado' | ''
  lancamentos: number
}

export interface AvancoDoCronograma {
  por_atividade: Record<string, AvancoDaAtividade>
  /** O percentual físico da obra, ponderado pelo peso. `null` quando nenhuma
   *  folha tem peso — e `null` não é zero. */
  fisico: number | null
  financeiro: {
    orcado: string
    realizado: string
    percentual: number | null
    folhas: number
  } | null
  folhas: number
  folhas_sem_peso: number
  folhas_apontadas: number
  ultimo_apontamento: string | null
}

export type Granularidade = 'dia' | 'semana' | 'mes'

/** Um ponto da curva S. O **realizado é `null`** depois do último apontamento:
 *  linha reta até o fim do plano seria lida como "em dia", e o que aconteceu foi
 *  que ninguém apontou. */
export interface PontoCurvaS {
  iso: string
  rotulo: string
  previsto: number
  realizado: number | null
  previsto_periodo: number
  realizado_periodo: number | null
  previsto_reais: string | null
  realizado_reais: string | null
}

export interface CurvaS {
  granularidade: Granularidade
  /** O que a tela pediu. Diferente de `granularidade` quando o servidor
   *  engrossou por causa do teto de pontos — e é por isso que os dois viajam. */
  granularidade_pedida: Granularidade
  pontos: PontoCurvaS[]
  base_fisica: string
  base_financeira: string | null
  folhas: number
  folhas_sem_peso: number
  folhas_sem_data: number
  ultimo_apontamento: string | null
  motivo_vazio: string
}

/** Uma linha da grade da semana, antes de virar chamada. */
export interface LinhaDeApontamento {
  atividade: number
  data: string
  percentual: string
  local?: number | null
  observacao?: string
}

export interface ResultadoDoApontamentoEmLote {
  apontamentos: number
  etapas_sincronizadas: number
  teto: number
}
