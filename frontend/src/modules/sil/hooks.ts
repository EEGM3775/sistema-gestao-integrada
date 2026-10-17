import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import type { Resource } from './api/silApi'
import {
  itens, locais, saldos, movimentacoes, lotes, requisicoes, itensRequisicao,
  transferencias, itensTransferencia, devolucoes, itensDevolucao, inventarios, itensInventario,
  entregasEpi, ferramentas, emprestimos,
  getSilDashboard, getCurvaABC, getAplicado, listObras, listFornecedores, listFuncionarios, listEtapas, temRh,
  registrarMov, definirMinimo, gerarDemanda, aprovarRequisicao, atenderRequisicao,
  executarTransferencia, executarDevolucao, fecharInventario, reabrirInventario,
  devolverEpi, alterarEstadoFerramenta, devolverEmprestimo,
} from './api/silApi'
import { silKeys } from './api/queryKeys'
import type {
  Item, LocalEstoque, SaldoEstoque, MovimentacaoEstoque, Lote, Requisicao, ItemRequisicao,
  Transferencia, ItemTransferencia, Devolucao, ItemDevolucao, Inventario, ItemInventario,
  EntregaEPI, Ferramenta, EmprestimoFerramenta,
} from './types'

type Params = Record<string, unknown>
interface Keys { all: readonly unknown[]; list: (p?: Params) => readonly unknown[]; detail: (id: number) => readonly unknown[] }

function makeHooks<T, P>(res: Resource<T, P>, keys: Keys) {
  return {
    useList(params: Params = {}, enabled = true) {
      return useQuery({ queryKey: keys.list(params), queryFn: () => res.listPaged(params), placeholderData: keepPreviousData, enabled })
    },
    useAll(params: Params = {}, enabled = true) {
      return useQuery({ queryKey: [...keys.list(params), 'all'], queryFn: () => res.listAll(params), enabled })
    },
    useDetail(id: number | undefined) {
      return useQuery({ queryKey: keys.detail(id ?? 0), queryFn: () => res.get(id as number), enabled: id != null })
    },
    useCreate() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (payload: P) => res.create(payload), onSuccess: () => qc.invalidateQueries({ queryKey: silKeys.all }) })
    },
    useUpdate() {
      const qc = useQueryClient()
      return useMutation({ mutationFn: (v: { id: number; payload: Partial<P> }) => res.update(v.id, v.payload), onSuccess: () => qc.invalidateQueries({ queryKey: silKeys.all }) })
    },
  }
}

export const itensHooks = makeHooks<Item, unknown>(itens, silKeys.itens)
export const locaisHooks = makeHooks<LocalEstoque, unknown>(locais, silKeys.locais)
export const saldosHooks = makeHooks<SaldoEstoque, unknown>(saldos, silKeys.saldos)
export const movimentacoesHooks = makeHooks<MovimentacaoEstoque, unknown>(movimentacoes, silKeys.movimentacoes)
export const lotesHooks = makeHooks<Lote, unknown>(lotes, silKeys.lotes)
export const requisicoesHooks = makeHooks<Requisicao, unknown>(requisicoes, silKeys.requisicoes)
export const itensRequisicaoHooks = makeHooks<ItemRequisicao, unknown>(itensRequisicao, silKeys.itensRequisicao)
export const transferenciasHooks = makeHooks<Transferencia, unknown>(transferencias, silKeys.transferencias)
export const itensTransferenciaHooks = makeHooks<ItemTransferencia, unknown>(itensTransferencia, silKeys.itensTransferencia)
export const devolucoesHooks = makeHooks<Devolucao, unknown>(devolucoes, silKeys.devolucoes)
export const itensDevolucaoHooks = makeHooks<ItemDevolucao, unknown>(itensDevolucao, silKeys.itensDevolucao)
export const inventariosHooks = makeHooks<Inventario, unknown>(inventarios, silKeys.inventarios)
export const itensInventarioHooks = makeHooks<ItemInventario, unknown>(itensInventario, silKeys.itensInventario)
export const entregasEpiHooks = makeHooks<EntregaEPI, unknown>(entregasEpi, silKeys.entregasEpi)
export const ferramentasHooks = makeHooks<Ferramenta, unknown>(ferramentas, silKeys.ferramentas)
export const emprestimosHooks = makeHooks<EmprestimoFerramenta, unknown>(emprestimos, silKeys.emprestimos)

export function useObras() {
  return useQuery({ queryKey: silKeys.obras, queryFn: listObras })
}
export function useFornecedores() {
  return useQuery({ queryKey: silKeys.fornecedores, queryFn: listFornecedores })
}
export function useFuncionarios() {
  return useQuery({ queryKey: silKeys.funcionarios, queryFn: listFuncionarios })
}
export function useTemRh() {
  return useQuery({ queryKey: [...silKeys.funcionarios, 'acesso'], queryFn: temRh, staleTime: 5 * 60_000 })
}
export function useEtapas(obra: number | undefined) {
  return useQuery({ queryKey: silKeys.etapas(obra ?? 0), queryFn: () => listEtapas(obra as number), enabled: obra != null })
}
export function useCurvaABC() {
  return useQuery({ queryKey: silKeys.curvaAbc(), queryFn: getCurvaABC, placeholderData: keepPreviousData })
}
export function useAplicado(obra?: number) {
  return useQuery({ queryKey: silKeys.aplicado(obra), queryFn: () => getAplicado(obra), placeholderData: keepPreviousData })
}

function useVerb<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: silKeys.all }) })
}
export const useRegistrarMov = () => useVerb((v: Parameters<typeof registrarMov>[0]) => registrarMov(v))
export const useDefinirMinimo = () => useVerb((v: { saldo: number; ponto: string }) => definirMinimo(v.saldo, v.ponto))
export const useGerarDemanda = () => useVerb((v: { saldo: number; quantidade?: string }) => gerarDemanda(v.saldo, v.quantidade))
export const useAprovarRequisicao = () => useVerb((id: number) => aprovarRequisicao(id))
export const useAtenderRequisicao = () => useVerb((id: number) => atenderRequisicao(id))
export const useExecutarTransferencia = () => useVerb((id: number) => executarTransferencia(id))
export const useExecutarDevolucao = () => useVerb((id: number) => executarDevolucao(id))
export const useFecharInventario = () => useVerb((id: number) => fecharInventario(id))
export const useReabrirInventario = () => useVerb((id: number) => reabrirInventario(id))
export const useDevolverEpi = () => useVerb((id: number) => devolverEpi(id))
export const useAlterarEstadoFerramenta = () => useVerb((v: { id: number; estado: string; proxima_calibracao?: string | null; proxima_manutencao?: string | null }) => alterarEstadoFerramenta(v.id, v))
export const useDevolverEmprestimo = () => useVerb((id: number) => devolverEmprestimo(id))

export function useSilDashboard() {
  return useQuery({ queryKey: silKeys.dashboard(), queryFn: getSilDashboard, placeholderData: keepPreviousData })
}
