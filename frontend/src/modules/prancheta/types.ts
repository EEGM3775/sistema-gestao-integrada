/**
 * Contratos da Prancheta — espelham `backend/moduloprancheta/serializers.py`.
 *
 * Dois pontos que a tela **não** recalcula, e por isso vêm tipados de lá:
 * `conversao.nativo` (se os bytes são para o `<iframe>` do PDF ou para o
 * desenho) e `exige_upgrade` (a única falha que vira botão de compra). Refazer
 * qualquer um dos dois aqui seria manter uma segunda cópia do `formatos.py` em
 * TypeScript, que envelheceria na primeira fatia nova.
 */

export interface Paginado<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type EstadoConversao =
  | 'pronta'
  | 'convertendo'
  | 'erro'
  | 'nativa'
  | 'outro_modulo'
  /** O motor existe e cabe no plano — a conversão é que nunca foi enfileirada (D81). */
  | 'nao_agendada'
  | 'sem_motor'

export type TipoDerivada = 'vetor_2d' | 'modelo_3d' | 'miniatura'

/**
 * A ressalva de uma derivada que ficou **pronta** (D46).
 *
 * Existe porque `pronta` deixou de bastar: a prancha com uma entidade perdida a
 * quilômetros converte, abre e roda a 60 fps mostrando uma tarja preta. O motor
 * enquadra o que consegue; o que ele não alcança chega aqui, **escrito pelo
 * backend**. A tela não monta a frase nem recalcula o critério — é a mesma regra
 * de `exige_upgrade`, e por isso `ocupacao` viaja junto: é o número que sustenta
 * a frase para quem for conferir.
 */
export interface DesenhoNaFolha {
  x: number
  y: number
  w: number
  h: number
  /** Quantos traços caíram neste aglomerado — é o que separa "o outro desenho"
   *  de "um traço esquecido" sem obrigar a abrir os dois. */
  tracos: number
}

/**
 * O que o arquivo tem a declarar depois de abrir.
 *
 * Mudou de natureza na PRA.1c: era um pedido de desculpas com atalhos para dentro
 * de uma folha quilométrica que não devia ter existido. Agora cada desenho tem a
 * própria folha, e o que sobra é informar — quantas são (para ninguém abrir a
 * primeira e concluir que o resto se perdeu) e se o desenho está em coordenada de
 * mundo (que é por que a régua não bate com um template errado).
 */
export interface AvisoDerivada {
  codigo: 'varios_desenhos' | 'georreferenciado' | 'hachura_simplificada'
  titulo: string
  mensagem: string
  georreferenciado: boolean
}

/**
 * Onde este arquivo está na fila da frota de trabalho pesado (D98/PRA.11).
 *
 * **Ausente é resposta**, e a tela precisa tratá-la: conversão que rodou
 * síncrona, job anterior a esta fatia, ou a corrida normal entre o worker
 * terminar e a tela perguntar. Sem a linha, mostra-se o "convertendo" de sempre
 * — nunca uma posição inventada, que é a única coisa pior que não ter posição.
 */
export interface FilaDaConversao {
  situacao: 'aguardando' | 'despachada'
  /** Quantos estão na frente, +1. `0` quando já saiu da fila e está rodando. */
  posicao: number
  /** Quantas vezes este arquivo já voltou ao fim da fila para continuar. */
  voltas: number
  /** Quantos arquivos **da própria empresa** este ultrapassaria ao ser subido.
   *  É o número que sustenta o aviso — sem ele o botão seria o que todo mundo
   *  aperta sempre. */
  na_frente_da_empresa: number
  pode_priorizar: boolean
  priorizada_em: string | null
  tarefa_id: number
  folhas_prontas: number
  folhas_restantes: number
}

export interface Conversao {
  estado: EstadoConversao
  /** A espera com forma. Ver {@link FilaDaConversao}. */
  fila?: FilaDaConversao | null
  tipo?: TipoDerivada
  /** URL **gateada** (`/api/prancheta/.../arquivo/`) — nunca caminho de mídia. */
  visualizador: string | null
  miniatura?: string | null
  motivo?: string
  detalhe?: string
  /** Dono do dado quando o formato pertence a outro módulo (KMZ → Maps). */
  dono?: string
  /** O browser abre o arquivo original sem conversão (PDF/imagem). */
  nativo: boolean
  /** Limite de **plano** (`motor_insuficiente`), não defeito. */
  exige_upgrade: boolean
  /**
   * O problema está no **arquivo**, não no motor nem no plano — desenho vazio,
   * XREF que não subiu, DWG sem miniatura embutida (PRA.1b). Vem resolvido do
   * backend porque a tela não pode reclassificar sobre a string do motivo; sem
   * ele, "o desenho está vazio" entraria na fila do que consertamos e o canteiro
   * veria trabalho que não existe.
   */
  problema_no_arquivo: boolean
  /** `pronta` **com ressalva** — abre, e mesmo assim há o que dizer. */
  aviso?: AvisoDerivada | null
}

export type SituacaoRevisao = 'rascunho' | 'vigente' | 'superada'

export interface RevisaoResumo {
  revisao_id: number
  revisao: string
  formato: string
  formato_rotulo: string
  situacao: SituacaoRevisao
  tamanho_bytes: number
  data_emissao: string | null
  publicado_em: string | null
  arquivo_url: string | null
  conversao: Conversao
  /**
   * As folhas que este arquivo trouxe, na ordem em que se abrem.
   *
   * Um DWG de construtora não traz "uma prancha": traz a mesma área desenhada na
   * origem e em coordenada UTM, ou o *sheet set* inteiro montado no modelspace.
   * Cada folha tem a própria página, a própria régua e o próprio nome.
   *
   * Vazio para PDF, imagem e modelo 3D, que não têm folha separável — nesses
   * casos a tela abre `conversao.visualizador`, como sempre abriu.
   */
  desenhos: Desenho[]
  /** A régua da prancha viaja no resumo: o visualizador abre a partir do acervo,
   *  e sem ela aqui a primeira medida sairia sem unidade.
   *
   *  **É a régua da PRIMEIRA folha**, não da revisão — a régua mora na folha,
   *  porque é ela que tem largura. Quem abre a segunda lê a dela em `desenhos`. */
  escala_valor: number | null
  escala_unidade: string
  escala_origem: OrigemEscala
}

/**
 * Uma folha da revisão — o que se abre, mede e marca.
 *
 * `rotulo` já vem resolvido pelo servidor (`nome` quando alguém deu um,
 * `Desenho N` quando não, `Traço solto` para o aglomerado de um traço), para a
 * tela não refazer a regra e as duas versões dela divergirem no primeiro ajuste.
 */
export interface Desenho extends Escala {
  desenho_id: number
  revisao: number
  ordem: number
  /** Vazio enquanto ninguém nomeou — é o que distingue o rótulo automático do
   *  nome escolhido, e o que a herança entre revisões usa para não propagar um
   *  rótulo que ninguém pediu. */
  nome: string
  rotulo: string
  tracos: number
  /** Envolvente em unidades de DESENHO. É a identidade que atravessa revisões:
   *  a folha muda quando o projetista mexe no desenho, o lugar no terreno não. */
  caixa: Record<string, number>
  /**
   * A ponte de volta à coordenada que o CAD mostra.
   *
   * ```
   * x_desenho = origem_x + x_folha · por_folha
   * y_desenho = origem_y − y_folha · por_folha        // o SVG cresce para baixo
   * ```
   *
   * **É medida na emissão, não deduzida** (`dxf.py::_mundo_da_folha`) — refazer
   * a conta da página erra de um jeito que cresce com o zoom, que foi metade do
   * D90. `origem` é o canto superior-esquerdo da FOLHA, margem incluída.
   *
   * Vazio (`{}`) para folha convertida antes desta medida existir e para motor
   * que não rende coordenada (PDF, imagem). Vazio é resposta: o leitor mostra as
   * réguas dele e **não** finge coordenada de desenho.
   */
  mundo: { origem_x: number; origem_y: number; por_folha: number } | Record<string, never>
  visualizador: string | null
  /** O índice de snap desta folha (PRA.10), ou `null` quando não há.
   *
   *  São três os motivos de não haver, e a tela não precisa distingui-los para
   *  decidir o que fazer (não há mira): o plano não paga o recurso, o formato
   *  não rende geometria (PDF, imagem) ou a extração falhou. Quem precisa da
   *  diferença lê a memória de conversão da derivada.
   *
   *  `truncado` é o que autoriza a tela a dizer "snap parcial" — sem ele, a
   *  mira que não gruda num canto se lê como defeito, e não como o teto do
   *  plano agindo. */
  snap: { url: string; pontos: number; truncado: boolean } | null
  tem_escala: boolean
}

/**
 * De onde saiu o metro desta prancha (PRA.3b).
 *
 * `'desenho'` — o DXF/DWG declarou a unidade (`$INSUNITS`) e o motor a extraiu na
 * conversão; é a mesma informação que faz o AutoCAD responder em metro, e chega
 * sem ninguém calibrar nada. `'calibrada'` — uma pessoa traçou sobre uma cota
 * conhecida, e essa régua é **soberana**: nenhuma reconversão a sobrescreve.
 * `''` — a prancha não tem escala (PDF, foto, desenho sem unidade declarada), e a
 * medida sai em fração da largura, dizendo isso.
 */
export type OrigemEscala = 'desenho' | 'calibrada' | ''

/**
 * A escala calibrada da prancha (PRA.3).
 *
 * `escala_valor` é **quantas unidades reais cabem na largura inteira** do
 * desenho — a grandeza que as coordenadas normalizadas exigem. `null` é estado
 * normal e visível: a tela mede assim mesmo e mostra o resultado em fração da
 * largura, dizendo que não há escala. O que ela não faz é escrever "3,50 m" sem
 * alguém ter dito de onde saiu o metro.
 */
export interface Escala {
  escala_valor: number | null
  escala_unidade: string
  escala_referencia: Record<string, unknown>
  escala_calibrada_em: string | null
  escala_origem: OrigemEscala
}

export interface Derivada {
  derivada_id: number
  revisao: number
  tipo: TipoDerivada
  tipo_rotulo: string
  motor: string
  motor_versao: string
  estado: 'pendente' | 'lendo' | 'convertendo' | 'pronto' | 'erro'
  estado_rotulo: string
  arquivo_url: string | null
  tamanho_bytes: number
  erro_motivo: string
  erro_motivo_rotulo: string
  erro_detalhe: string
  exige_upgrade: boolean
  problema_no_arquivo: boolean
  aviso: AvisoDerivada | null
  hash_origem: string
  memoria: Record<string, unknown>
  criado_em: string
  concluido_em: string | null
}

export interface Revisao extends Escala {
  revisao_id: number
  documento: number
  documento_codigo: string
  revisao: string
  arquivo_url: string | null
  nome_original: string
  formato: string
  formato_rotulo: string
  tamanho_bytes: number
  hash_sha256: string
  situacao: SituacaoRevisao
  situacao_rotulo: string
  data_emissao: string | null
  observacao: string
  enviado_por_nome: string | null
  enviado_em: string
  publicado_por_nome: string | null
  publicado_em: string | null
  derivadas: Derivada[]
  /**
   * O que dizer **na hora** do upload sobre um arquivo que passou e não vai
   * abrir — hoje só o teto de peso do DWG (D47). `null` é o caso normal, e a
   * tela não mostra nada.
   */
  aviso: string | null
}

export interface Documento {
  documento_id: number
  obra: number
  obra_nome: string
  etapa: number | null
  etapa_nome: string | null
  codigo: string
  titulo: string
  /** A **principal** — a primeira da lista. Sustenta ordenação e cor de destaque. */
  disciplina: string
  disciplina_rotulo: string
  /** Resolvida pelo servidor (tabela do tenant → embutida → derivada estável). */
  disciplina_cor: string
  /**
   * Todas as disciplinas da prancha, **principal primeiro**, já resolvidas.
   *
   * Vem resolvida e não como lista de códigos porque o cartão pinta os pontos a
   * partir daqui: cruzar com o catálogo no cliente erraria a cor de uma
   * disciplina apagada no meio da sessão.
   */
  disciplinas: { codigo: string; nome: string; cor: string }[]
  descricao: string
  projetista: string
  ativo: boolean
  vigente: RevisaoResumo | null
  /**
   * O rascunho mais recente **quando não há vigente** — o que torna o cartão
   * capaz de resolver o próprio estado. `null` quando já existe uma publicada:
   * trocar o desenho que o campo executa é decisão com motivo, não botão de
   * cartão.
   */
  pendente: RevisaoResumo | null
  total_revisoes: number
  criado_em: string
}

/**
 * A fila de decisão do cockpit. As duas últimas contagens são **separadas** de
 * propósito (planta §9): uma o cliente resolve comprando, a outra nós
 * resolvemos consertando. Somá-las mandaria o canteiro abrir chamado por upsell.
 */
export interface RequerDecisao {
  documentos_sem_revisao_vigente: string[]
  revisoes_em_rascunho: number
  conversoes_com_erro: number
  conversoes_que_exigem_upgrade: number
  /** PRA.1b — quem **enviou** resolve: falta o XREF que carrega a geometria. */
  conversoes_aguardando_anexo: number
  /** PRA.1b — **ninguém** resolve. Existe para ser subtraído do total acima. */
  conversoes_sem_desenho: number
  /** PRA.3 — a linha que a PRA.0 declarou e deixou por preencher. */
  marcacoes_abertas: number
  marcacoes_atribuidas_a_mim: number
  /** Ninguém resolveu e o desenho mudou embaixo. A resposta é humana. */
  marcacoes_em_revisao_superada: number
}

// ---------------------------------------------------------------------------
// PRA.3 — marcar e medir
// ---------------------------------------------------------------------------

/**
 * Coordenada na folha, **normalizada pela largura** do desenho: `x` em [0,1] e
 * `y` em [0, altura/largura].
 *
 * Normalizar os dois eixos por eixos diferentes (o óbvio) distorceria o aspecto
 * e faria a mesma diagonal medir diferente conforme a folha. Dividir os dois
 * pela largura preserva a proporção — e é o mesmo contrato do backend, que
 * calcula o valor da medida a partir destes números.
 */
export interface Ponto {
  x: number
  y: number
}

/** `TopicType` do BCF — o valor é o do padrão, o rótulo vem do servidor. */
export type TipoMarcacao = 'Issue' | 'Request' | 'Comment' | 'Clash' | 'Inquiry'
/** `TopicStatus` do BCF. `Open`/`In Progress` são as abertas. */
export type SituacaoMarcacao = 'Open' | 'In Progress' | 'Resolved' | 'Closed'
export type PrioridadeMarcacao = 'Low' | 'Normal' | 'High' | 'Critical'

export interface ComentarioMarcacao {
  comentario_id: number
  guid: string
  marcacao: number
  texto: string
  autor: number | null
  /** Preenchido em qualquer caso — username de quem tem login, nome do BCF
   * para quem não tem. Nunca em branco, senão a conversa pareceria anônima
   * justamente do lado de fora. */
  autor_nome: string
  ponto_de_vista: number | null
  criado_em: string
}

export interface PontoDeVista {
  ponto_de_vista_id: number
  guid: string
  /** Bloco 3D do BCF, preservado como veio. Vazio na marcação 2D. */
  camera: Record<string, unknown>
  snapshot_url: string | null
  criado_em: string
}

export interface Medicao {
  medicao_id: number
  revisao: number
  marcacao: number | null
  tipo: 'distancia' | 'area'
  tipo_rotulo: string
  pontos: Ponto[]
  /** Na unidade real quando há escala; em fração da largura quando não há. */
  valor: number
  unidade: string
  /** `null` = medida sem escala. Distingue os dois casos acima. */
  escala_aplicada: number | null
  /** A prancha foi recalibrada depois desta medida. Não é erro: é o aviso de
   * que ela veio de outra régua. */
  desatualizada: boolean
  rotulo: string
  criado_por_nome: string | null
  criado_em: string
}

export interface Marcacao {
  marcacao_id: number
  /** A identidade FORA daqui: é por ele que a ida e volta com o BCF reencontra
   * o mesmo tópico em vez de duplicá-lo. */
  guid: string
  revisao: number
  revisao_rotulo: string
  revisao_superada: boolean
  documento: number
  documento_codigo: string
  documento_titulo: string
  obra: number
  titulo: string
  descricao: string
  tipo: TipoMarcacao
  tipo_rotulo: string
  situacao: SituacaoMarcacao
  situacao_rotulo: string
  aberta: boolean
  prioridade: PrioridadeMarcacao
  prioridade_rotulo: string
  rotulos: string[]
  prazo: string | null
  responsavel: number | null
  responsavel_nome: string
  responsavel_email: string
  criado_por: number | null
  criado_por_nome: string
  autor_nome: string
  criado_em: string
  atualizado_em: string
  resolvido_por_nome: string | null
  resolvido_em: string | null
  origem: 'sistema' | 'bcf'
  /** Onde na folha. Vazia quando a marcação veio de um BCF de modelo 3D, ou
   * quando a prancha é PDF (o leitor do browser não aceita sobreposição). */
  ancora: Ponto | Record<string, never>
  comentarios: ComentarioMarcacao[]
  pontos_de_vista: PontoDeVista[]
  medicoes: Medicao[]
}

export interface ResumoImportacaoBcf {
  criadas: number
  atualizadas: number
  comentarios: number
  pontos_de_vista: number
  total: number
}

/**
 * Uma disciplina do vocabulário — as 13 embutidas e as que o cliente criou.
 *
 * `padrao` diz se ela é do piso (não some do catálogo, e apagar a linha do tenant
 * só devolve o rótulo original); `cor` já vem resolvida do servidor, inclusive a
 * derivada de quem não escolheu — a tela **não** deriva cor, senão a disciplina
 * nova apareceria de uma cor no filtro e de outra no cartão.
 */
export interface DisciplinaCatalogo {
  codigo: string
  nome: string
  cor: string
  ordem: number
  padrao: boolean
  ativa: boolean
  /** Só existe quando há linha do tenant — é o que permite editar e apagar. */
  disciplina_id?: number
}

export interface Acervo {
  obra: number
  total_documentos: number
  disciplinas: {
    disciplina: string
    /** Rótulo e cor no GRUPO: a fileira de filtro os desenha sem abrir documento. */
    rotulo: string
    cor: string
    documentos: Documento[]
  }[]
  /** O vocabulário inteiro, inclusive o que ainda não tem prancha nesta obra. */
  catalogo_disciplinas: DisciplinaCatalogo[]
  requer_decisao: RequerDecisao
}

export interface FormatoDeclarado {
  codigo: string
  nome: string
  familia: string
  extensoes: string[]
  max_mb: number
  /**
   * Acima disto o arquivo **entra** e a prancha não sai — medido, não arbitrado
   * (D47: 0 de 10 DWGs acima de 40 MB abriram). `0` = sem teto conhecido.
   */
  motor_livre_max_mb: number
  contratado: boolean
  /**
   * Formato que NÃO é desenho e não entra pelo acervo — hoje só o BCF, que
   * carrega marcações sobre uma prancha que já está aqui. Não tem motor porque
   * não há o que converter, e por isso os dois campos abaixo vêm resolvidos do
   * servidor: sem eles a tela mostraria "exige alta fidelidade" para quem já
   * contratou o formato.
   */
  interop: boolean
  /** O cadeado é do MOTOR, não do formato — é o que faz o upsell fazer sentido. */
  exige_motor_premium: boolean
  motor_disponivel: boolean
}

export interface MotorDeclarado {
  codigo: string
  nome: string
  tier: 'livre' | 'premium'
  licenca: string
  custo_por_traducao: boolean
  /** O **plano** vende. */
  habilitado: boolean
  /** O **código** tem adaptador. */
  implementado: boolean
  /** Esta **imagem** tem a dependência instalada. */
  disponivel: boolean
  versao: string
}

export interface StatusPrancheta {
  modulo: string
  status: string
  plano: string | null
  formatos: FormatoDeclarado[]
  motores: MotorDeclarado[]
  teto_upload_direto_mb: number
  conversao_disponivel: boolean
}
