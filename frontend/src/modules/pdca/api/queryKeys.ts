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
    fornecedores: (busca: string) => [...pdcaKeys.raiz, 'vinculos', 'fornecedores', busca] as const,
  },
  /** PDCA.3. O saldo é chave **própria**, e não parte do detalhe do contrato:
   *  ele muda a cada medição aprovada, e invalidá-lo junto com o cadastro faria
   *  a tela recarregar a planilha contratual inteira a cada atesto. */
  contratos: {
    lista: (params: Record<string, unknown>) => [...pdcaKeys.raiz, 'contratos', params] as const,
    detalhe: (id: number) => [...pdcaKeys.raiz, 'contrato', id] as const,
    itens: (id: number) => [...pdcaKeys.raiz, 'contrato', id, 'itens'] as const,
    saldo: (id: number) => [...pdcaKeys.raiz, 'contrato', id, 'saldo'] as const,
    retencao: (id: number) => [...pdcaKeys.raiz, 'contrato', id, 'retencao'] as const,
    /** A prévia é cacheada pelo **período**: o gestor compara meses indo e
     *  voltando, e refazer a chamada a cada troca perderia a comparação. */
    proposta: (id: number, inicio: string, fim: string) =>
      [...pdcaKeys.raiz, 'contrato', id, 'proposta', inicio, fim] as const,
    periodo: (id: number) => [...pdcaKeys.raiz, 'contrato', id, 'periodo'] as const,
  },
  medicoes: {
    lista: (params: Record<string, unknown>) => [...pdcaKeys.raiz, 'medicoes', params] as const,
    detalhe: (id: number) => [...pdcaKeys.raiz, 'medicao', id] as const,
    /** A grade do documento. Chave própria porque ela muda a cada gravação da
     *  grade, e o detalhe do documento não precisa recarregar junto. */
    contexto: (id: number) => [...pdcaKeys.raiz, 'medicao', id, 'contexto'] as const,
  },
  aditivos: {
    lista: (params: Record<string, unknown>) => [...pdcaKeys.raiz, 'aditivos', params] as const,
    detalhe: (id: number) => [...pdcaKeys.raiz, 'aditivo', id] as const,
  },
  liberacoes: (params: Record<string, unknown>) =>
    [...pdcaKeys.raiz, 'liberacoes', params] as const,
}
