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
    contrato: boolean
    medicao: boolean
    retencao: boolean
    /** Verdadeiro desde a PDCA.4: com aditivo, a trava do acumulado passou a
     *  ser contra o contratado **atual** (original + deltas aprovados). */
    aditivo: boolean
    deducoes: boolean
    material_estocado: boolean
    /** O que a fatia **não** fecha, dito na própria capacidade — para a tela
     *  não oferecer botão que não foi feito. */
    importar_planilha_do_empreiteiro: boolean
    anexo_por_linha: boolean
  }
  /** Os tetos que a **tela** precisa respeitar antes de mandar a requisição.
   *  Vêm do servidor de propósito: quem decide o número é o dono, e o cliente
   *  lê o que vale hoje em vez de carregar uma cópia que envelhece no bundle. */
  tetos: {
    linhas_por_lote: number
    atividades_por_cronograma: number
    profundidade_wbs: number
    apontamentos_por_lote: number
    itens_por_contrato: number
    linhas_por_medicao: number
    itens_por_aditivo: number
    aditivos_abertos_por_contrato: number
    deducoes_por_medicao: number
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

// ---------------------------------------------------------------------------
// PDCA.3 — contrato, medição e retenção
// ---------------------------------------------------------------------------
//
// **Todo dinheiro é `string`, e nunca `number`.** O `float` do JSON tem 53 bits
// de mantissa e não representa centavo exatamente: R$ 1.234,57 chegaria como
// 1234.5699999999999. O backend serializa `Decimal` como string por isso, e o
// tipo aqui acompanha — converter para `number` na borda reintroduziria o erro
// que a escolha do backend evitou.

export type RegimeContrato = 'unitario' | 'global' | 'administracao'
export type NaturezaRetencao = 'nenhuma' | 'caucao' | 'garantia' | 'tecnica'
export type StatusContrato = 'rascunho' | 'vigente' | 'suspenso' | 'encerrado' | 'cancelado'
export type StatusMedicao =
  | 'rascunho' | 'em_aprovacao' | 'aprovada' | 'reprovada' | 'cancelada'

export interface Contrato {
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
  retencao_natureza: NaturezaRetencao
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
  /** **A regra de quando a planilha ainda aceita edição, vinda do servidor.**
   *  Ela fecha quando alguém já mediu contra ela — não quando o contrato sai do
   *  rascunho. Reimplementá-la aqui foi o que fez a tela dizer "não se edita
   *  mais" enquanto a API aceitava a edição. */
  planilha_editavel: boolean
  planilha_fechada_porque: string
}

export interface ItemDeContrato {
  item_contrato_id: number
  contrato: number
  item_orcado: number | null
  item_orcado_descricao: string | null
  atividade: number | null
  atividade_nome: string | null
  codigo: string
  descricao: string
  unidade: string
  ordem: number
  quantidade_contratada: string
  preco_unitario: string
  valor_contratado: string
  /** Sem isto a tela não consegue explicar por que uma linha não recebeu
   *  proposta — e "sem vínculo" é um estado que o gestor precisa ver no
   *  cadastro, não descobrir na hora de medir. */
  tem_vinculo_de_avanco: boolean
  observacao: string
  /** **O que vale hoje** — original + aditivos aprovados. Vem resolvido do
   *  servidor: `quantidade_contratada` é o do dia da assinatura, e num contrato
   *  aditado ele deixou de ser o limite. */
  quantidade_atual: string
  quantidade_aditivada: string
}

export interface RetencaoDoContrato {
  retido: string
  liberado: string
  disponivel: string
  natureza: NaturezaRetencao
  condicao: string
}

export interface SaldoDoContrato {
  contrato_id: number
  regime: RegimeContrato
  valor_contratado: string
  medido_aprovado: string
  medido_em_aprovacao: string
  /** Fica **fora** do saldo e aparece à parte: rascunho é intenção, e somá-lo
   *  faria o saldo encolher quando o gestor abre uma medição para estudar. */
  medido_rascunho: string
  saldo: string
  retencao: RetencaoDoContrato
  itens: number
  itens_fechados: number
  medicoes: number
  /** PDCA.4 — o contratado em três números, porque o do dia da assinatura
   *  deixou de ser o limite no instante do primeiro aditivo. */
  valor_original: string
  valor_aditivado: string
  deducoes_aprovadas: string
  material_estocado: string
  aditivos: number
  aditivos_abertos: number
  periodo_sugerido: PeriodoSugerido
}

/** Por que a linha não recebeu proposta automática. `sem_vinculo` é diferente
 *  de zero: zero é "não andou", sem vínculo é "ninguém mediu isto pelo avanço". */
export type CriterioDaProposta = 'direto' | 'ponderado' | 'media_simples' | 'sem_vinculo'


export interface PropostaDeMedicao {
  contrato_id: number
  regime: RegimeContrato
  periodo: { inicio: string; fim: string }
  linhas: LinhaDaGrade[]
  /** O denominador da honestidade, na régua do `cobertura_do_orcamento`. */
  cobertura: { itens: number; sem_vinculo: number; codigos_sem_vinculo: string[] }
}

export interface ItemDeMedicao {
  item_medicao_id: number
  medicao: number
  item_contrato: number
  codigo: string
  descricao: string
  unidade: string
  quantidade: string
  /** **Saldo** de material posto na obra e ainda não aplicado — a coluna E da
   *  G703. O que se paga de material nesta medição é a diferença contra o que
   *  a anterior declarava. */
  quantidade_estocada: string
  quantidade_proposta: string | null
  preco_unitario: string
  percentual_avanco_periodo: string | null
  origem: 'avanco' | 'manual'
  origem_rotulo: string
  valor: string
  /** Quanto o gestor mexeu na proposta. É o que torna o ajuste auditável. */
  ajuste: string | null
  observacao: string
}

export interface TotaisDaMedicao {
  /** `Σ quantidade × preço` — o serviço executado no período. */
  executado: string
  /** O que **entrou** em estoque no período (negativo quando foi aplicado). */
  material_estocado: string
  bruto: string
  retencao: string
  retencao_percentual: string
  deducoes: {
    deducao_id: number
    tipo: TipoDeducao
    tipo_rotulo: string
    descricao: string
    percentual: string | null
    base_calculo: string | null
    valor: string
  }[]
  total_deducoes: string
  liquido: string
}

/** O degrau em que a medição está parada — para a tela dizer *de quem* se
 *  espera a decisão, em vez de um "em aprovação" que não ajuda ninguém. */
export interface EscadaDaMedicao {
  pedido_id: number
  estado: string
  nivel: string | null
  permissao_exigida: string | null
  solicitante: string
  /** As assinaturas: quem decidiu cada degrau, quando e com que autoridade. */
  atestos: {
    atesto_id: number
    nivel_ordem: number
    nivel_nome: string
    decisao: 'aprovado' | 'reprovado'
    autor: string
    permissao_conferida: string
    decidido_em: string
    observacao: string
  }[]
}

export interface Medicao {
  medicao_id: number
  contrato: number
  contrato_numero: string
  fornecedor_nome: string
  obra_nome: string
  /** O id da obra — a fila de decisão monta com ele o endereço
   *  `/app/pdca/obra/:id/contratos/:id`, sem uma consulta por linha. */
  contrato_obra: number
  regime: RegimeContrato
  numero: number
  periodo_inicio: string
  periodo_fim: string
  status: StatusMedicao
  status_rotulo: string
  retifica: number | null
  retencao_percentual_aplicado: string
  custo_reembolsavel: string | null
  taxa_administracao_aplicada: string | null
  custo_origem: 'informado' | 'apropriado'
  custo_origem_rotulo: string
  /** O id da `ContaPagar` no ERP. Seam frouxo, sem FK — o PDCA não paga (§7). */
  conta_pagar_ref: number | null
  apurada_por: string
  apurada_em: string
  congelada_em: string | null
  observacao: string
  itens: ItemDeMedicao[]
  deducoes: Deducao[]
  totais: TotaisDaMedicao
  escada: EscadaDaMedicao | null
}

export interface ResultadoDaSubmissao {
  estado: 'aprovada' | 'em_aprovacao'
  escada: number | null
  /** Ressalvas que não impedem — a principal é o custo de administração
   *  digitado, que a régua de dado honesto manda declarar em vez de esconder. */
  avisos: string[]
  medicao: Medicao
}

export interface LiberacaoDeRetencao {
  liberacao_id: number
  contrato: number
  contrato_numero: string
  fornecedor_nome: string
  valor: string
  data: string
  condicao_atendida: string
  status: StatusMedicao
  status_rotulo: string
  conta_pagar_ref: number | null
  solicitada_por: string
}

// ---------------------------------------------------------------------------
// PDCA.4 — aditivo, deduções e a grade no padrão G703
// ---------------------------------------------------------------------------

export type AcaoAditivo = 'acrescimo' | 'supressao' | 'preco' | 'inclusao'
export type StatusAditivo =
  | 'rascunho' | 'em_aprovacao' | 'aprovado' | 'reprovado' | 'cancelado'

export type TipoDeducao =
  | 'inss' | 'iss' | 'irrf' | 'adiantamento' | 'material' | 'multa' | 'outros'

export interface Deducao {
  deducao_id: number
  medicao: number
  tipo: TipoDeducao
  tipo_rotulo: string
  descricao: string
  base_calculo: string | null
  percentual: string | null
  valor: string | null
  /** O que esta linha efetivamente tira — derivado do bruto no servidor. */
  valor_aplicado: string
}

/** A entrada da reescrita: percentual **ou** valor, nunca os dois. */
export interface LinhaDeDeducao {
  tipo: TipoDeducao
  descricao?: string
  base_calculo?: string | null
  percentual?: string | null
  valor?: string | null
}

export interface ItemDeAditivo {
  item_aditivo_id: number
  aditivo: number
  item_contrato: number | null
  acao: AcaoAditivo
  acao_rotulo: string
  quantidade_delta: string
  preco_unitario: string | null
  preco_unitario_anterior: string | null
  codigo: string
  descricao: string
  unidade: string
  /** A quantidade que a linha tem hoje — o denominador do delta. `null` na
   *  inclusão, porque a linha ainda não existe. */
  quantidade_atual: string | null
  observacao: string
}

export interface ResumoDoAditivo {
  acrescimo: string
  supressao: string
  revisao_de_preco: string
  liquido: string
  contratado_original: string
  percentual_sobre_original: string | null
  itens: number
}

export interface Aditivo {
  aditivo_id: number
  contrato: number
  contrato_numero: string
  contrato_obra: number
  fornecedor_nome: string
  numero: number
  objeto: string
  justificativa: string
  data_assinatura: string | null
  nova_data_fim: string | null
  status: StatusAditivo
  status_rotulo: string
  criado_por: string
  criado_em: string
  aplicado_em: string | null
  itens: ItemDeAditivo[]
  resumo: ResumoDoAditivo
  escada: EscadaDaMedicao | null
}

export interface LinhaDeAditivo {
  acao: AcaoAditivo
  item_contrato_id?: number | null
  quantidade_delta?: string
  preco_unitario?: string | null
  codigo_novo?: string
  descricao_nova?: string
  unidade_nova?: string
  observacao?: string
}

/** De quando a próxima medição deveria falar — encadeada na anterior. */
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

/**
 * Uma linha da grade, **inteira, como o servidor a calculou**.
 *
 * As dez colunas da G703 estão todas aqui, e nenhuma é derivada no navegador —
 * é o contrato desta tela desde que abrir uma medição pelo link direto passou a
 * mostrar "já medido" negativo e saldo acima do contratado (a página montava a
 * conta a partir de uma prévia que nem sempre existia).
 */
export interface LinhaDaGrade {
  item_contrato_id: number
  codigo: string
  descricao: string
  unidade: string
  /** O que vale **hoje**: original + aditivos aprovados. */
  quantidade_contratada: string
  quantidade_original: string
  quantidade_aditivada: string
  nasceu_de_aditivo: boolean
  quantidade_ja_medida: string
  saldo: string
  quantidade_proposta: string
  percentual_avanco_periodo: string | null
  criterio: CriterioDaProposta
  limitada_pelo_saldo: boolean
  preco_unitario: string
  atividades: number[]
  /** **De onde saiu a proposta** — uma entrada por atividade, com o avanço que
   *  ela apontou no período e o peso que teve na média. Vem junto da linha
   *  porque sai da mesma consulta do servidor. */
  memoria: {
    atividade_id: number
    codigo: string
    nome: string
    percentual: string
    peso: string | null
    origem_do_peso: string
  }[]
  /** O que está gravado no documento aberto (zero fora dele). */
  quantidade_medida: string
  /** **Saldo** de material posto na obra, não delta. */
  quantidade_estocada: string
  estocado_anterior: string
  origem: 'avanco' | 'manual' | null
  observacao: string
}

/** A grade de uma medição que existe — uma chamada, uma verdade. */
export interface ContextoDeMedicao {
  medicao_id: number
  numero: number
  status: StatusMedicao
  editavel: boolean
  contrato_id: number
  regime: RegimeContrato
  periodo: { inicio: string; fim: string }
  linhas: LinhaDaGrade[]
  cobertura: { itens: number; sem_vinculo: number; codigos_sem_vinculo: string[] }
  totais: TotaisDaMedicao
  escada: EscadaDaMedicao | null
}

/** O que a tela manda de volta por linha. */
export interface LinhaParaApi {
  item_contrato_id: number
  quantidade: string
  quantidade_estocada?: string
  observacao?: string
}
