export const pdcaKeys = {
  raiz: ['pdca'] as const,
  status: () => [...pdcaKeys.raiz, 'status'] as const,

  obras: () => [...pdcaKeys.raiz, 'obras'] as const,

  cronogramas: {
    raiz: () => [...pdcaKeys.raiz, 'cronogramas'] as const,
    daObra: (obraId: number) => [...pdcaKeys.cronogramas.raiz(), 'obra', obraId] as const,
    detalhe: (id: number) => [...pdcaKeys.cronogramas.raiz(), id] as const,
    gantt: (id: number) => [...pdcaKeys.cronogramas.raiz(), id, 'gantt'] as const,
    balanco: (id: number) => [...pdcaKeys.cronogramas.raiz(), id, 'balanco'] as const,
    curvaS: (id: number, granularidade: string) =>
      [...pdcaKeys.cronogramas.raiz(), id, 'curva-s', granularidade] as const,
  },

  locais: (obraId: number) => [...pdcaKeys.raiz, 'locais', obraId] as const,
  calendarios: (obraId: number) => [...pdcaKeys.raiz, 'calendarios', obraId] as const,

  semana: {
    raiz: () => [...pdcaKeys.raiz, 'semana'] as const,
    daObra: (obraId: number, inicio: string) =>
      [...pdcaKeys.raiz, 'semana', obraId, inicio] as const,
    itens: (programacaoId: number) =>
      [...pdcaKeys.raiz, 'semana', 'itens', programacaoId] as const,
    candidatos: (programacaoId: number) =>
      [...pdcaKeys.raiz, 'semana', 'candidatos', programacaoId] as const,
    ppc: (obraId: number) => [...pdcaKeys.raiz, 'semana', 'ppc', obraId] as const,
    causas: (obraId: number) =>
      [...pdcaKeys.raiz, 'semana', 'ranking', obraId] as const,
  },
  restricoes: (obraId: number, status: string) =>
    [...pdcaKeys.raiz, 'restricoes', obraId, status] as const,
  catalogoDeCausas: () => [...pdcaKeys.raiz, 'catalogo-causas'] as const,

  minhasFrentes: (quem: string, obraId: number | undefined) =>
    [...pdcaKeys.raiz, 'minhas-frentes', quem, obraId ?? 'todas'] as const,

  carteira: () => [...pdcaKeys.raiz, 'carteira'] as const,
  hoje: (obraId: number) => [...pdcaKeys.raiz, 'hoje', obraId] as const,
  busca: (termo: string, obraId: number | undefined) =>
    [...pdcaKeys.raiz, 'busca', termo, obraId ?? 'todas'] as const,
}
