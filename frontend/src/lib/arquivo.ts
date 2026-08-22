/**
 * Download autenticado de arquivo — a ponta de cliente da porta única (D70).
 *
 * **Por que não dá para pendurar a URL num `<a href>` ou `<img src>`.** O access
 * token vive em memória (F1) e só é anexado pelo interceptor do `apiClient`; a
 * navegação direta do browser chegaria sem `Authorization` e levaria 401. Então
 * o arquivo é buscado por XHR e vira um object URL local — o mesmo caminho que a
 * Prancheta usa desde a PRA.2, agora valendo para os nove prefixos que saíram de
 * `/media/`.
 *
 * Efeito colateral bom: o blob entra como origem opaca, onde script não roda —
 * o que importa para SVG e para qualquer coisa que o cliente tenha enviado.
 *
 * Isto vive em `lib/` e não dentro de um módulo porque nenhum dos dois lados é
 * de domínio: quem baixa é RH, cliente, obra, diário, ERP e Prancheta.
 */
import { useEffect, useState } from 'react'

import apiClient from '@/api/apiClient'

/**
 * O `baseURL` do axios já é `/api`, e o backend devolve o caminho **completo**
 * (`/api/impexp/...`) porque é ele que funciona contra o gateway sem o cliente
 * remontar prefixo. Emendar os dois daria `/api/api/…` — então a ponte entre as
 * duas verdades mora aqui, numa linha.
 */
const semPrefixoDaApi = (url: string) => url.replace(/^\/api(?=\/)/, '')

/** Baixa o arquivo autenticado e devolve o blob. */
export async function baixarArquivo(url: string): Promise<Blob> {
  const resposta = await apiClient.get(semPrefixoDaApi(url), { responseType: 'blob' })
  return resposta.data as Blob
}

/** Salva o arquivo no dispositivo, com nome saneado. */
export async function baixarParaDisco(url: string, nome: string) {
  const blob = await baixarArquivo(url)
  const objeto = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objeto
  link.download = nome.replace(/[^\w.-]+/g, '_')
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objeto)
}

/**
 * Abre o arquivo numa aba nova — o gesto que os `<a target="_blank">` das telas
 * de RH, cliente e obra faziam antes de o arquivo ganhar gate.
 *
 * O object URL é revogado depois de um minuto, e não no `click`: revogar na hora
 * fecharia a aba que acabou de abrir. Um minuto é folgado para o browser ler o
 * blob e curto para não vazar memória numa sessão longa.
 */
export async function abrirEmNovaAba(url: string) {
  const blob = await baixarArquivo(url)
  const objeto = URL.createObjectURL(blob)
  window.open(objeto, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(objeto), 60_000)
}

/**
 * O arquivo como object URL, pronto para `<img src>` — com limpeza no unmount.
 *
 * Promovido dos hooks da Prancheta no D70: a linha do tempo do diário precisa do
 * mesmo comportamento, e duas cópias de um efeito que revoga object URL é como
 * se vaza memória em uma delas.
 */
export function useArquivoBlob(url: string | null) {
  const [objeto, setObjeto] = useState<string | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(false)

  useEffect(() => {
    if (!url) {
      setObjeto(null)
      return
    }
    let vivo = true
    let criado: string | null = null
    setCarregando(true)
    setErro(null)

    baixarArquivo(url)
      .then((blob) => {
        if (!vivo) return
        criado = URL.createObjectURL(blob)
        setObjeto(criado)
      })
      .catch((e: { response?: { status?: number } }) => {
        if (!vivo) return
        // 404 aqui é o registro sem bytes (arquivo fora do armazenamento) e 403
        // é falta de permissão — a tela não deve confundir os dois.
        setErro(
          e?.response?.status === 403
            ? 'Você não tem permissão para abrir este arquivo.'
            : e?.response?.status === 404
              ? 'O arquivo não está disponível no servidor.'
              : 'Não foi possível carregar o arquivo agora.',
        )
      })
      .finally(() => vivo && setCarregando(false))

    return () => {
      vivo = false
      if (criado) URL.revokeObjectURL(criado)
    }
  }, [url])

  return { objeto, erro, carregando }
}
