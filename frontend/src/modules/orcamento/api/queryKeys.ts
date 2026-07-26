type Params = Record<string, unknown>

const raiz = ['orcamento'] as const

function familia(nome: string) {
  return {
    all: [...raiz, nome] as const,
    list: (p: Params = {}) => [...raiz, nome, 'list', p] as const,
    detail: (id: number) => [...raiz, nome, 'detail', id] as const,
  }
}

export const orcKeys = {
  all: raiz,
  status: () => [...raiz, 'status'] as const,
  orcamentos: familia('orcamentos'),
  itens: familia('itens'),
  revisoes: familia('revisoes'),
  bdis: familia('bdi'),
  parcelas: familia('parcelas'),
  parametricos: familia('parametricos'),
  pavimentos: familia('pavimentos'),
  unidades: familia('unidades'),
  memoriais: familia('memoriais'),
  bases: familia('bases'),
  referencias: familia('referencias'),
  basesResumo: () => [...raiz, 'bases-resumo'] as const,
  composicaoRef: (id: number) => [...raiz, 'composicao-ref', id] as const,
  arvore: (id: number) => [...raiz, 'arvore', id] as const,
  curvaAbc: (id: number) => [...raiz, 'curva-abc', id] as const,
  porCategoria: (id: number) => [...raiz, 'por-categoria', id] as const,
  cronograma: (id: number) => [...raiz, 'cronograma', id] as const,
  curvaS: (id: number) => [...raiz, 'curva-s', id] as const,
  memoria: (id: number) => [...raiz, 'memoria', id] as const,
  precoReal: (id: number) => [...raiz, 'preco-real', id] as const,
  controle: (obra?: number) => [...raiz, 'controle', obra ?? 'todas'] as const,
  nbr: (obra: number) => [...raiz, 'nbr', obra] as const,
  obras: [...raiz, 'obras'] as const,
  etapas: (obra: number) => [...raiz, 'etapas', obra] as const,
  catalogo: (busca: string) => [...raiz, 'catalogo', busca] as const,
  bancos: familia('bancos'),
  pastas: familia('pastas'),
  itensBanco: familia('itens-banco'),
  componentesBanco: familia('componentes-banco'),
  importacoes: familia('importacoes'),
  reprecificacoes: familia('reprecificacoes'),
  bancosResumo: () => [...raiz, 'bancos-resumo'] as const,
  composicaoBanco: (id: number) => [...raiz, 'composicao-banco', id] as const,
  linhasImportacao: (id: number, p: Params = {}) => [...raiz, 'linhas-importacao', id, p] as const,
  historicoRepre: (id: number) => [...raiz, 'historico-repre', id] as const,
}
