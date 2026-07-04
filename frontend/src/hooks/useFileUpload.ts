import { useState, useCallback, useEffect } from 'react'
import {
  uploadFile, downloadFile, validateFile, buildAcceptAttr,
  DEFAULT_UPLOAD_CONFIG,
  type UploadConfig, type UploadResult,
} from '@/utils/fileUpload'
import apiClient from '@/api/apiClient'

// ─── Configuração via API (cache em memória por sessão) ───────────────────────

let _configCache: UploadConfig | null = null

/** Busca configuração de upload do backend. Cai de volta nos padrões se falhar. */
export async function fetchUploadConfig(): Promise<UploadConfig> {
  if (_configCache) return _configCache
  try {
    const res = await apiClient.get('/configuracoes/upload/')
    _configCache = {
      maxTamanhoMB: res.data.max_tamanho_mb ?? DEFAULT_UPLOAD_CONFIG.maxTamanhoMB,
      tiposAceitos: res.data.tipos_aceitos?.length
        ? res.data.tipos_aceitos
        : DEFAULT_UPLOAD_CONFIG.tiposAceitos,
    }
    return _configCache
  } catch {
    return DEFAULT_UPLOAD_CONFIG
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

interface UseFileUploadOptions {
  /** Substitui a config da API por uma config local fixa. */
  config?: UploadConfig
  /** false = não busca config da API, usa DEFAULT. Default: true */
  fetchFromAPI?: boolean
}

export function useFileUpload(options: UseFileUploadOptions = {}) {
  const [config, setConfig]   = useState<UploadConfig>(options.config ?? DEFAULT_UPLOAD_CONFIG)
  const [progress, setProgress] = useState(0)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [result, setResult]     = useState<UploadResult | null>(null)

  useEffect(() => {
    if (options.config) { setConfig(options.config); return }
    if (options.fetchFromAPI === false) return
    fetchUploadConfig().then(setConfig)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const upload = useCallback(async (
    url: string,
    fieldName: string,
    file: File,
    extraData?: Record<string, string | number | boolean>,
  ): Promise<UploadResult | null> => {
    setError(null); setProgress(0); setLoading(true); setResult(null)
    try {
      const res = await uploadFile(url, fieldName, file, extraData, setProgress, config)
      setResult(res); setProgress(100)
      return res
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro ao enviar arquivo.')
      return null
    } finally {
      setLoading(false)
    }
  }, [config])

  const download = useCallback(async (url: string, filename: string) => {
    setError(null); setLoading(true)
    try { await downloadFile(url, filename) }
    catch { setError('Erro ao baixar arquivo.') }
    finally { setLoading(false) }
  }, [])

  const validate = useCallback(
    (file: File): string | null => validateFile(file, config),
    [config],
  )

  return {
    upload, download, validate,
    progress, loading, error, result,
    config,
    acceptAttr: buildAcceptAttr(config.tiposAceitos),
  }
}
