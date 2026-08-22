/**
 * `<img>` de um arquivo que exige token (D70).
 *
 * A URL da porta única não pode ir direto num `src`: o access token vive em
 * memória e o browser buscaria a imagem sem `Authorization`. Este componente
 * embrulha o `useArquivoBlob` — baixa por XHR, mostra o object URL, e cai num
 * ícone quando não há imagem, não há permissão ou o arquivo sumiu do
 * armazenamento.
 *
 * Componente e não hook solto porque o caso é sempre o mesmo: uma miniatura
 * dentro de um `.map`, onde chamar hook por item exige um componente de todo
 * jeito.
 */
import React from 'react'
import { ImageOff } from 'lucide-react'

import { useArquivoBlob } from '@/lib/arquivo'

interface Props {
  url: string | null
  alt?: string
  className?: string
  /** Cor do ícone de ausência — cada tela tem o seu fundo. */
  corDoVazio?: string
  tamanhoDoVazio?: number
}

export const ImagemDoArquivo: React.FC<Props> = ({
  url,
  alt = '',
  className = 'w-full h-full object-cover',
  corDoVazio = '#94a3b8',
  tamanhoDoVazio = 24,
}) => {
  const { objeto, erro } = useArquivoBlob(url)

  if (!url || erro || !objeto) {
    return (
      <span className="flex items-center justify-center w-full h-full" style={{ color: corDoVazio }}
            title={erro ?? undefined}>
        <ImageOff size={tamanhoDoVazio} />
      </span>
    )
  }
  return <img src={objeto} alt={alt} className={className} />
}

export default ImagemDoArquivo
