import { ImageOff } from 'lucide-react'
import { Spinner } from '@/components/malha'
import { abrirEmNovaAba, useArquivoBlob } from '@/lib/arquivo'

/** A foto de evidência — **pela porta única**, nunca por `<img src>` cru.
 *
 *  O token vive em memória e só o `apiClient` o anexa; a URL pendurada direto
 *  chegaria sem `Authorization` e mostraria o ícone de imagem quebrada, que se
 *  lê como "a foto não foi enviada". */
export function FotoProtegida({
  url, alt, altura = 180,
}: { url: string | null; alt: string; altura?: number }) {
  const { objeto, erro, carregando } = useArquivoBlob(url)

  if (!url) return null

  return (
    <button
      type="button"
      onClick={() => { void abrirEmNovaAba(url) }}
      title="Abrir a foto em tamanho real"
      style={{
        display: 'grid', placeItems: 'center', padding: 0, cursor: 'zoom-in',
        width: '100%', maxWidth: 320, height: altura, overflow: 'hidden',
        borderRadius: 'var(--r-sm)', border: '1px solid var(--line)',
        background: 'var(--inset)',
      }}
    >
      {carregando && <Spinner />}
      {erro && (
        <span style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, color: 'var(--ink-3)', padding: 10 }}>
          <ImageOff size={14} />
          {erro}
        </span>
      )}
      {objeto && (
        <img
          src={objeto}
          alt={alt}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      )}
    </button>
  )
}
