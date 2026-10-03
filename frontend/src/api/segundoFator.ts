// Segundo fator (remodelagem da segurança, fase 1 — docs/acesso-e-permissoes.md §10.5).
//
// Duas portas para o mesmo cadastro: o login de quem é obrigado a ter e ainda
// não tem (autorizado pelo `desafio` que a senha certa devolveu) e a tela
// Minha conta › Segurança (autorizada pela sessão). A resposta que abre uma sessão
// nova traz os cookies dela e o relógio de queda — como no login.
import axios from 'axios'
import { attachAuth } from './attachAuth'
import { CABECALHO_ANTI_CSRF, type LoginData } from './session'
import { atualizarRelogio, type CamposSessao } from './sessionClock'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'

const semSessao = axios.create({
  baseURL: iamBaseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json', ...CABECALHO_ANTI_CSRF },
})

const comSessao = axios.create({ baseURL: iamBaseURL })
attachAuth(comSessao)

export type EtapaSegundoFator = 'codigo' | 'cadastro'

export interface DesafioSegundoFator {
  segundo_fator: EtapaSegundoFator
  desafio: string
}

export interface InicioCadastro {
  segredo: string
  uri: string
  qr: string
}

export type SessaoComCodigos = LoginData & { codigos?: string[]; codigos_restantes?: number }

export type MotivoSegundoFator = 'administrador' | 'alcada_financeira' | 'dado_de_saude'

export interface EstadoSegundoFator {
  ativo: boolean
  metodo: string | null
  desde: string | null
  obrigatorio: boolean
  codigos_restantes: number
  motivos: MotivoSegundoFator[]
  bloqueado: boolean
}

export interface SegurancaDaConta {
  segundo_fator: EstadoSegundoFator
  janela_confirmacao: { minutos: number; padrao: number; minimo: number; maximo: number }
}

function guardarSessao<T extends CamposSessao>(data: T): T {
  atualizarRelogio(data)
  return data
}

export async function entrarComCodigo(desafio: string, codigo: string): Promise<SessaoComCodigos> {
  const r = await semSessao.post('login/segundo-fator/', { desafio, codigo })
  return guardarSessao(r.data as SessaoComCodigos)
}

/** Sem `desafio`, o cadastro é da sessão aberta (tela de perfil). */
export async function iniciarCadastro(desafio?: string): Promise<InicioCadastro> {
  const cliente = desafio ? semSessao : comSessao
  const r = await cliente.post('segundo-fator/cadastro/', desafio ? { desafio } : {})
  return r.data as InicioCadastro
}

export async function confirmarCadastro(codigo: string, desafio?: string): Promise<SessaoComCodigos> {
  const cliente = desafio ? semSessao : comSessao
  const r = await cliente.post('segundo-fator/cadastro/confirmar/', desafio ? { codigo, desafio } : { codigo })
  return guardarSessao(r.data as SessaoComCodigos)
}

export async function lerSeguranca(): Promise<SegurancaDaConta> {
  const r = await comSessao.get('conta/seguranca/')
  return r.data as SegurancaDaConta
}

export async function escolherJanela(minutos: number): Promise<SegurancaDaConta> {
  const r = await comSessao.patch('conta/seguranca/', { janela_confirmacao_min: minutos })
  return r.data as SegurancaDaConta
}

export async function desativarSegundoFator(senha: string, codigo: string): Promise<void> {
  await comSessao.post('segundo-fator/desativar/', { senha, codigo })
}

/** Trocar de celular (D241): o aparelho antigo segue valendo até `confirmarTroca`. */
export async function iniciarTroca(senha: string, codigo: string): Promise<InicioCadastro> {
  const r = await comSessao.post('segundo-fator/troca/', { senha, codigo })
  return r.data as InicioCadastro
}

export async function confirmarTroca(codigo: string): Promise<SessaoComCodigos> {
  const r = await comSessao.post('segundo-fator/troca/confirmar/', { codigo })
  return guardarSessao(r.data as SessaoComCodigos)
}

export async function trocarCodigos(codigo: string): Promise<string[]> {
  const r = await comSessao.post('segundo-fator/codigos/', { codigo })
  return r.data.codigos as string[]
}
