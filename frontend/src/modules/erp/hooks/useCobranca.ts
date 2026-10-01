import { useEffect, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { erpKeys } from '../api/queryKeys'
import {
  baixarRemessa, enviarRetorno, estornarBaixaPagar, estornarBaixaReceber, fetchAndamentoLote, fetchBancosCnab,
  fetchCarteiras, fetchMiniaturaBoleto, fetchPdfBoleto, fetchPreviaCobranca, fetchRemessas, fetchRetornos,
  emitirLoteNfse, gerarCobranca, gerarLote, previaLote, previaLoteNfse, salvarCarteira, type EscolhaDoLote,
} from '../api/endpoints/cobranca'
import type { CarteiraCobranca, ContaPagar, ContaReceber, RemessaCnab } from '../types'

const COBRANCA = ['erp', 'cobranca'] as const

/** Tudo o que uma mudança de cobrança pode ter mexido: contas, boletos, grade e hub. */
function useInvalidarFinanceiro() {
  const qc = useQueryClient()
  return () => {
    for (const chave of [erpKeys.contasAReceber.all, erpKeys.contasAPagar.all, erpKeys.boletos.all, erpKeys.grade.all, erpKeys.dashboard.all, COBRANCA]) {
      qc.invalidateQueries({ queryKey: chave })
    }
  }
}

/** Item 55 — a prévia refeita a cada data que a pessoa escolhe. */
export function usePreviaCobranca(contaId: number | undefined, vencimento: string | undefined, ativo: boolean) {
  return useQuery({
    queryKey: [...COBRANCA, 'previa', contaId, vencimento ?? null],
    queryFn: () => fetchPreviaCobranca(contaId as number, vencimento),
    enabled: ativo && contaId != null,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useGerarCobranca() {
  const invalidar = useInvalidarFinanceiro()
  return useMutation({
    mutationFn: ({ contaId, vencimento }: { contaId: number; vencimento?: string }) => gerarCobranca(contaId, vencimento),
    onSuccess: invalidar,
  })
}

/** Item 57 — estornar a baixa (pagar ou receber). */
export function useEstornarBaixa(lado: 'pagar' | 'receber') {
  const invalidar = useInvalidarFinanceiro()
  return useMutation<ContaPagar | ContaReceber, unknown, { id: number; motivo: string }>({
    mutationFn: ({ id, motivo }) =>
      lado === 'pagar' ? estornarBaixaPagar(id, motivo) : estornarBaixaReceber(id, motivo),
    onSuccess: invalidar,
  })
}

/** Item 52 — prévia e emissão do lote. */
export function usePreviaLote() {
  return useMutation({ mutationFn: (e: EscolhaDoLote) => previaLote(e) })
}

export function useGerarLote() {
  const invalidar = useInvalidarFinanceiro()
  return useMutation({
    mutationFn: ({ escolha, canal, carteira }: { escolha: EscolhaDoLote; canal: 'asaas' | 'cnab'; carteira?: number }) =>
      gerarLote(escolha, canal, carteira),
    onSuccess: invalidar,
  })
}

/** NFS-e em lote (pedido do dono, 01/10/2026) — prévia e emissão. */
export function usePreviaLoteNfse() {
  return useMutation({ mutationFn: (e: EscolhaDoLote) => previaLoteNfse(e) })
}

export function useEmitirLoteNfse() {
  const invalidar = useInvalidarFinanceiro()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (e: EscolhaDoLote) => emitirLoteNfse(e),
    onSuccess: () => { invalidar(); qc.invalidateQueries({ queryKey: erpKeys.notasFiscaisServico.all }) },
  })
}

/** O andamento do lote, consultado até não haver mais nada na fila. */
export function useAndamentoLote(loteId: number | undefined) {
  const invalidar = useInvalidarFinanceiro()
  const consulta = useQuery({
    queryKey: [...COBRANCA, 'lote', loteId],
    queryFn: () => fetchAndamentoLote(loteId as number),
    enabled: loteId != null,
    refetchInterval: q => ((q.state.data?.pendentes ?? 1) > 0 ? 2000 : false),
  })
  const terminou = consulta.data != null && consulta.data.pendentes === 0
  useEffect(() => { if (terminou) invalidar() }, [terminou]) // eslint-disable-line react-hooks/exhaustive-deps
  return consulta
}

/** Item 56 — a miniatura do boleto como URL do navegador (liberada ao sair). */
export function useMiniaturaBoleto(boletoId: number | undefined) {
  const consulta = useQuery({
    queryKey: [...COBRANCA, 'miniatura', boletoId],
    queryFn: () => fetchMiniaturaBoleto(boletoId as number),
    enabled: boletoId != null,
    staleTime: 10 * 60_000,
    retry: false,
  })
  const url = useUrlDeBlob(consulta.data)
  return { url, carregando: consulta.isLoading, erro: consulta.isError }
}

export function usePdfBoleto(boletoId: number | undefined) {
  const consulta = useQuery({
    queryKey: [...COBRANCA, 'pdf', boletoId],
    queryFn: () => fetchPdfBoleto(boletoId as number),
    enabled: boletoId != null,
    staleTime: 10 * 60_000,
    retry: false,
  })
  const url = useUrlDeBlob(consulta.data)
  return { url, carregando: consulta.isLoading, erro: consulta.error }
}

function useUrlDeBlob(blob: Blob | undefined) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!blob) { setUrl(null); return }
    const u = URL.createObjectURL(blob)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [blob])
  return url
}

/** CNAB — carteiras, remessas e retornos. */
export function useCarteiras() {
  return useQuery({ queryKey: [...COBRANCA, 'carteiras'], queryFn: fetchCarteiras })
}

export function useBancosCnab() {
  return useQuery({ queryKey: [...COBRANCA, 'bancos'], queryFn: fetchBancosCnab, staleTime: Infinity })
}

export function useSalvarCarteira() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (c: Partial<CarteiraCobranca>) => salvarCarteira(c),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...COBRANCA, 'carteiras'] }),
  })
}

export function useRemessas() {
  return useQuery({ queryKey: [...COBRANCA, 'remessas'], queryFn: fetchRemessas })
}

export function useBaixarRemessa() {
  return useMutation({ mutationFn: (r: RemessaCnab) => baixarRemessa(r) })
}

export function useRetornos() {
  return useQuery({ queryKey: [...COBRANCA, 'retornos'], queryFn: fetchRetornos })
}

export function useEnviarRetorno() {
  const invalidar = useInvalidarFinanceiro()
  return useMutation({
    mutationFn: ({ carteira, arquivo }: { carteira: number; arquivo: File }) => enviarRetorno(carteira, arquivo),
    onSuccess: invalidar,
  })
}
