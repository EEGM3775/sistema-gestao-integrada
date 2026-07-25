// Chaves de cache do React Query para o SIL. Raiz única `['sil']` — os verbos de
// domínio invalidam a raiz inteira (afetam saldo + ledger + documento).
type Params = Record<string, unknown>

function root(name: string) {
  return {
    all: ['sil', name] as const,
    list: (p: Params = {}) => ['sil', name, 'list', p] as const,
    detail: (id: number) => ['sil', name, 'detail', id] as const,
  }
}

export const silKeys = {
  all: ['sil'] as const,
  dashboard: () => ['sil', 'dashboard'] as const,
  curvaAbc: () => ['sil', 'curva-abc'] as const,
  aplicado: (obra?: number) => ['sil', 'aplicado', obra ?? 'todas'] as const,
  entregasEpi: root('entregas-epi'),
  ferramentas: root('ferramentas'),
  emprestimos: root('emprestimos'),
  funcionarios: ['sil', 'opt', 'funcionarios'] as const,
  etapas: (obra: number) => ['sil', 'opt', 'etapas', obra] as const,
  itens: root('itens'),
  locais: root('locais'),
  saldos: root('saldos'),
  movimentacoes: root('movimentacoes'),
  lotes: root('lotes'),
  requisicoes: root('requisicoes'),
  itensRequisicao: root('itens-requisicao'),
  transferencias: root('transferencias'),
  itensTransferencia: root('itens-transferencia'),
  devolucoes: root('devolucoes'),
  itensDevolucao: root('itens-devolucao'),
  inventarios: root('inventarios'),
  itensInventario: root('itens-inventario'),
  obras: ['sil', 'opt', 'obras'] as const,
  fornecedores: ['sil', 'opt', 'fornecedores'] as const,
}
