import apiClient from '@/api/apiClient'

// ─── Tipos ────────────────────────────────────────────────────────────────────

export interface UploadConfig {
  maxTamanhoMB: number
  tiposAceitos: string[]  // MIME types, ex: ['application/pdf', 'image/jpeg']
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type UploadResult = Record<string, any>

export const DEFAULT_UPLOAD_CONFIG: UploadConfig = {
  maxTamanhoMB: 10,
  tiposAceitos: [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  ],
}

const MIME_LABELS: Record<string, string> = {
  'application/pdf': 'PDF',
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'image/webp': 'WEBP',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'application/msword': 'DOC',
}

const MIME_TO_EXT: Record<string, string> = {
  'application/pdf': '.pdf',
  'image/jpeg': '.jpg,.jpeg',
  'image/png': '.png',
  'image/webp': '.webp',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
  'application/msword': '.doc',
}

// ─── Validação local ──────────────────────────────────────────────────────────

export function validateFile(file: File, config: UploadConfig = DEFAULT_UPLOAD_CONFIG): string | null {
  const maxBytes = config.maxTamanhoMB * 1024 * 1024
  if (file.size > maxBytes) {
    return `Arquivo muito grande. Máximo: ${config.maxTamanhoMB} MB (recebido: ${(file.size / 1024 / 1024).toFixed(1)} MB).`
  }
  if (config.tiposAceitos.length > 0 && !config.tiposAceitos.includes(file.type)) {
    const allowed = config.tiposAceitos.map(t => MIME_LABELS[t] ?? t).join(', ')
    return `Tipo não permitido. Aceitos: ${allowed}.`
  }
  return null
}

/** Gera string para o atributo `accept` do input[type=file] */
export function buildAcceptAttr(tiposAceitos: string[]): string {
  return tiposAceitos.map(t => MIME_TO_EXT[t] ?? t).join(',')
}

// ─── Upload com progresso ─────────────────────────────────────────────────────

/**
 * Envia um arquivo para `url` como multipart/form-data.
 * @param fieldName  Nome do campo no formulário (backend espera esse nome)
 * @param extraData  Campos adicionais de texto a enviar junto
 * @param onProgress Callback com percentual 0–100
 */
export async function uploadFile(
  url: string,
  fieldName: string,
  file: File,
  extraData?: Record<string, string | number | boolean>,
  onProgress?: (percent: number) => void,
  config: UploadConfig = DEFAULT_UPLOAD_CONFIG,
): Promise<UploadResult> {
  const err = validateFile(file, config)
  if (err) throw new Error(err)

  const formData = new FormData()
  formData.append(fieldName, file)
  if (extraData) {
    for (const [k, v] of Object.entries(extraData)) formData.append(k, String(v))
  }

  const res = await apiClient.post(url, formData, {
    onUploadProgress: e => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total))
    },
  })
  return res.data as UploadResult
}

// ─── Download autenticado ─────────────────────────────────────────────────────

/** Faz GET autenticado (token JWT via apiClient) e força download no browser. */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await apiClient.get(url, { responseType: 'blob' })
  const blobUrl = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(blobUrl)
}
