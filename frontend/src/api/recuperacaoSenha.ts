// Recuperação de senha e confirmação de troca de e-mail (D11).
//
// Endpoints PÚBLICOS da IAM: quem esqueceu a senha, por definição, não consegue
// se autenticar. Por isso este cliente é "cru" — sem os interceptors de refresh
// do `attachAuth`, que tentariam renovar uma sessão que não existe e disparariam
// redirecionamento para o login no meio do fluxo.
import axios from 'axios'

const iamBaseURL = (import.meta.env.VITE_IAM_BASE_URL as string | undefined) ?? '/auth'

const raw = axios.create({
  baseURL: iamBaseURL,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * Pede o link de recuperação. A resposta é sempre a mesma, exista a conta ou
 * não — o servidor não revela quem está cadastrado, e a UI não deve tentar
 * inferir nada dela. Trate como "pedido registrado", não como "e-mail enviado".
 */
export async function solicitarRecuperacao(identificador: string): Promise<string> {
  const r = await raw.post('senha/esqueci/', { identificador })
  return r.data.detail as string
}

/** Consome o token do e-mail e aplica a senha nova. */
export async function redefinirComToken(token: string, novaSenha: string): Promise<string> {
  const r = await raw.post('senha/redefinir/', { token, nova_senha: novaSenha })
  return r.data.detail as string
}

/**
 * Confirma (ou cancela) uma troca de e-mail. O link chega no endereço ANTIGO —
 * é isso que impede que trocar o e-mail de alguém seja um atalho para assumir a
 * conta dessa pessoa.
 */
export async function resolverTrocaEmail(
  token: string,
  cancelar = false,
): Promise<{ detail: string; email?: string }> {
  const r = await raw.post('email/confirmar/', { token, cancelar })
  return r.data
}

/**
 * Extrai `detail` do erro da IAM, com fallback legível.
 *
 * O 429 é tratado à parte por dois motivos. O texto do DRF é imprestável para o
 * usuário final ("Pedido foi suprimido. Espera-se que esteja diponível em 3600
 * segundos." — em segundos, e com o erro de digitação que vem da tradução do
 * próprio framework). E, principalmente, é preciso deixar claro que o bloqueio é
 * da CONEXÃO, não da conta: sem isso a pessoa entende "minha conta foi
 * bloqueada" e liga para o suporte.
 *
 * O que este texto NÃO pode fazer é dizer qualquer coisa sobre a conta existir
 * ou não — é o mesmo motivo pelo qual o teto por conta (5/h) é silencioso e
 * devolve 200 genérico. Aqui só se fala de origem/tentativas.
 */
export function mensagemDeErro(err: unknown, padrao: string): string {
  const resposta = (err as {
    response?: { status?: number; data?: { detail?: string }; headers?: Record<string, string> }
  })?.response

  if (resposta?.status === 429) {
    const segundos = Number(resposta.headers?.['retry-after'])
    const minutos = Number.isFinite(segundos) && segundos > 0 ? Math.ceil(segundos / 60) : null
    return minutos
      ? `Muitas tentativas a partir desta conexão. Tente novamente em ${minutos} min.`
      : 'Muitas tentativas a partir desta conexão. Aguarde alguns minutos e tente novamente.'
  }

  return resposta?.data?.detail ?? padrao
}
