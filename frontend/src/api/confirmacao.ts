// Confirmação de identidade antes do ato grave — o step-up (docs/acesso-e-permissoes.md
// §10.5, fase 6). Pagar, atestar, mudar papel ou exportar dado pessoal respondem 401
// com `codigo: confirmacao_necessaria` quando a última prova passou da janela da
// pessoa; o interceptor pede a confirmação à tela e refaz o pedido.
import axios from 'axios'
import { CABECALHO_ANTI_CSRF } from './session'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'

const cliente = axios.create({
  baseURL: iamBaseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json', ...CABECALHO_ANTI_CSRF },
})

export interface EstadoConfirmacao {
  metodo: 'codigo' | 'senha'
  janela_s: number
  valida_ate: number | null
}

export async function lerEstadoConfirmacao(): Promise<EstadoConfirmacao> {
  const r = await cliente.get('confirmar/')
  return r.data as EstadoConfirmacao
}

export async function confirmarIdentidade(prova: { codigo?: string; senha?: string }): Promise<EstadoConfirmacao> {
  const r = await cliente.post('confirmar/', prova)
  return r.data as EstadoConfirmacao
}

export function exigeConfirmacao(erro: unknown): boolean {
  if (!axios.isAxiosError(erro)) return false
  const corpo = erro.response?.data as { codigo?: string } | undefined
  return erro.response?.status === 401 && corpo?.codigo === 'confirmacao_necessaria'
}

type Confirmador = () => Promise<boolean>

let confirmador: Confirmador | null = null
let emAndamento: Promise<boolean> | null = null

export function registrarConfirmador(fn: Confirmador | null): void {
  confirmador = fn
}

export function pedirConfirmacao(): Promise<boolean> {
  if (!confirmador) return Promise.resolve(false)
  if (!emAndamento) {
    emAndamento = confirmador().finally(() => {
      emAndamento = null
    })
  }
  return emAndamento
}
