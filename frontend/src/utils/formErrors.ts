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

// ─── Parse de erros da API (axios error → FieldErrors) ───────────────────────

export function parseApiErrors(err: unknown): FieldErrors {
  const data = (err as { response?: { data?: unknown } })?.response?.data

  if (!data) return { _form: 'Não foi possível conectar ao servidor.' }
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
