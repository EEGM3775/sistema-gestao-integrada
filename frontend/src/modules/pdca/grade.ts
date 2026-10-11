/** As colunas da grade do plano e as medidas que a grade e o Gantt dividem —
 *  as duas metades do split view têm de ter a mesma altura de linha, ou as
 *  barras desalinham dos nomes. */

export const ALTURA_LINHA = 28
export const ALTURA_CABECALHO_GRADE = 40

/** A escala do Gantt é **contínua**: quantos pixels vale um dia. Os atalhos
 *  (dia, semana, mês, trimestre) são só pontos dela; a barra de ferramentas tem
 *  o deslizante, o −/+ e o "caber na tela". */
export type Zoom = number

export const ESCALAS: { rotulo: string; px: Zoom }[] = [
  { rotulo: 'dia', px: 22 },
  { rotulo: 'semana', px: 7 },
  { rotulo: 'mês', px: 2.6 },
  { rotulo: 'trimestre', px: 1 },
]
export const ZOOM_MIN: Zoom = 0.6
export const ZOOM_MAX: Zoom = 48

export type ColunaId =
  | 'codigo' | 'nome' | 'duracao' | 'predecessoras' | 'inicio' | 'termino'
  | 'folga' | 'local' | 'responsavel' | 'peso'

export const COLUNAS: { id: ColunaId; rotulo: string; largura: number; direita?: boolean; fixa?: boolean }[] = [
  { id: 'codigo', rotulo: 'EAP', largura: 70, fixa: true },
  { id: 'nome', rotulo: 'Atividade', largura: 230, fixa: true },
  { id: 'duracao', rotulo: 'Dur.', largura: 48, direita: true },
  { id: 'predecessoras', rotulo: 'Predecessoras', largura: 112 },
  { id: 'inicio', rotulo: 'Início', largura: 82, direita: true },
  { id: 'termino', rotulo: 'Término', largura: 74, direita: true },
  { id: 'folga', rotulo: 'Folga', largura: 46, direita: true },
  { id: 'local', rotulo: 'Local', largura: 110 },
  { id: 'responsavel', rotulo: 'Responsável', largura: 120 },
  { id: 'peso', rotulo: 'Peso', largura: 88, direita: true },
]

export const COLUNAS_PADRAO: ColunaId[] = ['codigo', 'nome', 'duracao', 'predecessoras', 'inicio', 'termino']

export const LARGURA_ALCA = 20
export const LARGURA_ACOES = 46

export function larguraDaGrade(colunas: ColunaId[]): number {
  return LARGURA_ALCA + LARGURA_ACOES
    + COLUNAS.filter((c) => colunas.includes(c.id)).reduce((s, c) => s + c.largura, 0)
}
