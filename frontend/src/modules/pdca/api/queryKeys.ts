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

  /** O posto da medição. **Uma raiz só para tudo o que é dinheiro**, e é
   *  deliberado: submeter um boletim muda o saldo do contrato, a fila do
   *  posto, a fila do dia e a carteira. Invalidar só a chave que o verbo tocou
   *  deixaria o saldo velho ao lado do boletim novo — o mesmo motivo do
   *  invalidador único da semana. */
  medicao: {
    raiz: () => [...pdcaKeys.raiz, 'medicao'] as const,
    posto: (obraId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'posto', obraId] as const,
    itensDoContrato: (contratoId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'itens-contrato', contratoId] as const,
    boletins: (contratoId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'boletins', contratoId] as const,
    contexto: (medicaoId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'contexto', medicaoId] as const,
    documento: (medicaoId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'documento', medicaoId] as const,
    aditivos: (contratoId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'aditivos', contratoId] as const,
    liberacoes: (contratoId: number) =>
      [...pdcaKeys.raiz, 'medicao', 'liberacoes', contratoId] as const,
    previa: (contratoId: number, inicio: string, fim: string) =>
      [...pdcaKeys.raiz, 'medicao', 'previa', contratoId, inicio, fim] as const,
  },

  /** O laço da qualidade. Uma raiz só, pelo motivo da medição: responder um
   *  item muda a ficha, a fila do posto, a fila do dia e o painel — e abrir a
   *  NC a partir dele muda a lista de NCs e o cartão da semana. */
  qualidade: {
    raiz: () => [...pdcaKeys.raiz, 'qualidade'] as const,
    posto: (obraId: number) =>
      [...pdcaKeys.raiz, 'qualidade', 'posto', obraId] as const,
    ncs: (obraId: number, status: string) =>
      [...pdcaKeys.raiz, 'qualidade', 'ncs', obraId, status] as const,
    nc: (id: number) => [...pdcaKeys.raiz, 'qualidade', 'nc', id] as const,
    fichas: (obraId: number) =>
      [...pdcaKeys.raiz, 'qualidade', 'fichas', obraId] as const,
    ficha: (id: number) => [...pdcaKeys.raiz, 'qualidade', 'ficha', id] as const,
    itensDaFicha: (id: number) =>
      [...pdcaKeys.raiz, 'qualidade', 'itens-da-ficha', id] as const,
    modelos: (todos: boolean) =>
      [...pdcaKeys.raiz, 'qualidade', 'modelos', todos ? 'todos' : 'ativos'] as const,
    modelo: (id: number) => [...pdcaKeys.raiz, 'qualidade', 'modelo', id] as const,
  },

  /** A SSMA. Investigar abre NC e interditar abre restrição, então os verbos
   *  daqui invalidam também a qualidade e a semana. */
  seguranca: {
    raiz: () => [...pdcaKeys.raiz, 'seguranca'] as const,
    posto: (obraId: number) =>
      [...pdcaKeys.raiz, 'seguranca', 'posto', obraId] as const,
    ocorrencias: (obraId: number) =>
      [...pdcaKeys.raiz, 'seguranca', 'ocorrencias', obraId] as const,
    ocorrencia: (id: number) =>
      [...pdcaKeys.raiz, 'seguranca', 'ocorrencia', id] as const,
    dds: (obraId: number) => [...pdcaKeys.raiz, 'seguranca', 'dds', obraId] as const,
    umDds: (id: number) => [...pdcaKeys.raiz, 'seguranca', 'um-dds', id] as const,
    epi: (obraId: number) => [...pdcaKeys.raiz, 'seguranca', 'epi', obraId] as const,
  },

  carteira: () => [...pdcaKeys.raiz, 'carteira'] as const,
  hoje: (obraId: number) => [...pdcaKeys.raiz, 'hoje', obraId] as const,
  busca: (termo: string, obraId: number | undefined) =>
    [...pdcaKeys.raiz, 'busca', termo, obraId ?? 'todas'] as const,
}
