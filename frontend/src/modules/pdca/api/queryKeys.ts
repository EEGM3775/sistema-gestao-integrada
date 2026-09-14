export const pdcaKeys = {
  raiz: ['pdca'] as const,
  status: () => [...pdcaKeys.raiz, 'status'] as const,
  obras: () => [...pdcaKeys.raiz, 'obras'] as const,
  calendarios: (params: Record<string, unknown>) => [...pdcaKeys.raiz, 'calendarios', params] as const,
  cronogramas: {
    lista: (params: Record<string, unknown>) => [...pdcaKeys.raiz, 'cronogramas', params] as const,
    detalhe: (id: number) => [...pdcaKeys.raiz, 'cronograma', id] as const,
    gantt: (id: number) => [...pdcaKeys.raiz, 'cronograma', id, 'gantt'] as const,
    base: (id: number) => [...pdcaKeys.raiz, 'cronograma', id, 'base'] as const,
    cobertura: (id: number) => [...pdcaKeys.raiz, 'cronograma', id, 'cobertura'] as const,
    modelos: () => [...pdcaKeys.raiz, 'modelos'] as const,
    avanco: (id: number) => [...pdcaKeys.raiz, 'cronograma', id, 'avanco'] as const,
    curva: (id: number, granularidade: string) =>
      [...pdcaKeys.raiz, 'cronograma', id, 'curva', granularidade] as const,
  },
  /** O histórico de apontamentos é **do plano**, e não da atividade: a pergunta
   *  que se faz olhando a tela é "o que foi apontado nesta obra esta semana". */
  apontamentos: (params: Record<string, unknown>) =>
    [...pdcaKeys.raiz, 'apontamentos', params] as const,
  expediente: {
    lista: () => [...pdcaKeys.raiz, 'expediente'] as const,
    detalhe: (id: number) => [...pdcaKeys.raiz, 'expediente', id] as const,
    excecoes: (id: number) => [...pdcaKeys.raiz, 'expediente', id, 'excecoes'] as const,
    diasUteis: (id: number, inicio: string, fim: string) =>
      [...pdcaKeys.raiz, 'expediente', id, 'dias-uteis', inicio, fim] as const,
  },
  /** Os vínculos vivem sob a **obra**, não sob o cronograma: replanejar troca o
   *  cronograma e não muda nem a árvore de locais nem as etapas da obra. */
  vinculos: {
    locais: (obra: number) => [...pdcaKeys.raiz, 'vinculos', 'locais', obra] as const,
    etapas: (obra: number) => [...pdcaKeys.raiz, 'vinculos', 'etapas', obra] as const,
    orcamentos: (obra: number) => [...pdcaKeys.raiz, 'vinculos', 'orcamentos', obra] as const,
    itens: (orcamento: number, busca: string) =>
      [...pdcaKeys.raiz, 'vinculos', 'itens', orcamento, busca] as const,
    responsaveis: (busca: string) => [...pdcaKeys.raiz, 'vinculos', 'responsaveis', busca] as const,
  },
}
