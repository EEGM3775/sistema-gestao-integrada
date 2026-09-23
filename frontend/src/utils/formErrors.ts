import React from 'react'

export type FieldErrors = Record<string, string>

// ─── Traduções comuns DRF → PT-BR ────────────────────────────────────────────

const MSG_MAP: [RegExp, string][] = [
  [/este campo não pode ser nulo/i,            'Campo obrigatório.'],
  [/este campo não pode ser em branco/i,       'Campo obrigatório.'],
  [/este campo é obrigatório/i,                'Campo obrigatório.'],
  [/this field may not be null/i,              'Campo obrigatório.'],
  [/this field may not be blank/i,             'Campo obrigatório.'],
  [/this field is required/i,                  'Campo obrigatório.'],
  [/a valid number is required/i,              'Digite um número válido.'],
  [/a valid integer is required/i,             'Digite um número inteiro válido.'],
  [/enter a valid email address/i,             'E-mail inválido.'],
  [/enter a valid url/i,                       'URL inválida.'],
  [/ensure this value is greater than/i,       'Valor abaixo do mínimo permitido.'],
  [/ensure this value is less than/i,          'Valor acima do máximo permitido.'],
  [/ensure this field has no more than/i,      'Valor excede o limite máximo de caracteres.'],
  [/formato de data inválido/i,                'Data inválida — use DD/MM/AAAA.'],
  [/invalid date format/i,                     'Data inválida — use DD/MM/AAAA.'],
]

function translateMsg(msg: string): string {
  for (const [re, pt] of MSG_MAP) {
    if (re.test(msg)) return pt
  }
  return msg
}

// ─── Quando a resposta NÃO é da API ──────────────────────────────────────────
//
// **Erro sem escrita não é erro** *(decisão do dono, 16/09/2026, depois de ver a
// página de 502 do nginx inteira dentro de um diálogo: "ninguém sabe o que é
// isso")*. Um `<html><head><title>502 Bad Gateway</title>…` é uma **string**, e
// o `String(data)` abaixo a despejava na tela como se fosse a mensagem do
// servidor. Não era mensagem nenhuma: era a encanação vazando na cara de quem
// estava trabalhando.
//
// O que uma pessoa precisa saber quando isso acontece são duas coisas, e as duas
// são frases:
//
//   1. **de quem é o problema** — dela, da rede ou nosso. Ela não vai clicar de
//      novo se achar que digitou algo errado;
//   2. **se o que ela escreveu se perdeu.** É a parte acionável: num 502 a
//      requisição não chegou a ser processada, então nada foi gravado e o certo
//      é tentar de novo. Sem essa frase a pessoa não sabe se o conserto que ela
//      acabou de registrar existe ou não.
//
// O `status` é o que separa os casos, e não o corpo — corpo de erro de
// infraestrutura é HTML de servidor, texto de balanceador ou nada.

/** O corpo veio em HTML? Então não é a API falando — é nginx, o Django em modo
 *  de depuração, ou um proxy no caminho. */
function pareceHtml(data: unknown): boolean {
  return typeof data === 'string' && /^\s*<(!doctype|html)/i.test(data)
}

function erroDeInfra(status: number | undefined, semResposta: boolean): string | null {
  if (semResposta) {
    return 'Não foi possível falar com o servidor. Verifique sua conexão e '
      + 'tente de novo — nada do que você digitou foi gravado.'
  }
  if (status === 502 || status === 503 || status === 504) {
    return 'O servidor está fora do ar ou reiniciando. Espere alguns segundos e '
      + 'tente de novo — nada do que você digitou foi gravado.'
  }
  if (status === 413) {
    return 'O arquivo é grande demais para o seu plano.'
  }
  if (status === 429) {
    return 'Muitas tentativas seguidas. Espere um instante e tente de novo.'
  }
  if (status && status >= 500) {
    return 'O servidor encontrou um erro inesperado ao processar isto. Nada foi '
      + 'gravado. Se acontecer de novo, avise o suporte com o que você estava '
      + 'fazendo.'
  }
  return null
}

// ─── Parse de erros da API (axios error → FieldErrors) ───────────────────────

export function parseApiErrors(err: unknown): FieldErrors {
  const resposta = (err as { response?: { data?: unknown; status?: number } })?.response
  const data = resposta?.data
  const status = resposta?.status

  // Infraestrutura primeiro: sem resposta, 5xx, ou corpo que não é da API.
  const infra = erroDeInfra(status, !resposta)
  if (infra) return { _form: infra }
  if (!data || pareceHtml(data)) {
    return {
      _form: 'O servidor respondeu de um jeito que esta tela não entende. '
        + 'Tente de novo; se persistir, avise o suporte.',
    }
  }

  // Corpo de texto simples da API (raro, mas legítimo — é uma frase).
  if (typeof data !== 'object' || Array.isArray(data)) return { _form: String(data) }

  const out: FieldErrors = {}
  for (const [field, msgs] of Object.entries(data as Record<string, unknown>)) {
    const raw = Array.isArray(msgs) ? msgs[0] : String(msgs)
    const msg = translateMsg(raw)
    if (field === 'non_field_errors' || field === 'detail') {
      out._form = msg
    } else {
      out[field] = msg
    }
  }
  // **O último caso de erro sem escrita**: um corpo `{}` (ou `[]`) sairia daqui
  // sem uma única frase, e a tela mostraria um espaço em branco onde deveria
  // estar a explicação. Um erro que não diz nada é pior que nenhum erro: ele
  // deixa a pessoa sem saber se o que ela fez valeu.
  if (!Object.keys(out).length) {
    out._form = 'A operação foi recusada, mas o servidor não disse por quê. '
      + 'Tente de novo; se persistir, avise o suporte.'
  }
  return out
}

// ─── Componente FieldError ────────────────────────────────────────────────────

export const FieldError: React.FC<{ msg?: string }> = ({ msg }) => {
  if (!msg) return null
  return React.createElement('p', {
    style: {
      fontSize: '0.7rem',
      color: '#dc2626',
      fontFamily: 'var(--font-body)',
      marginTop: '3px',
      lineHeight: 1.3,
    },
  }, `⚠ ${msg}`)
}

// ─── Banner de erro geral (non_field_errors / _form) ─────────────────────────

export const FormErrorBanner: React.FC<{ errors: FieldErrors }> = ({ errors }) => {
  const msg = errors._form
  if (!msg) return null
  return React.createElement('div', {
    style: {
      padding: '10px 14px',
      borderRadius: '8px',
      background: '#fff5f5',
      border: '1px solid #fed7d7',
      color: '#c53030',
      fontSize: '0.875rem',
      fontFamily: 'var(--font-body)',
    },
  }, `⚠ ${msg}`)
}
