import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// `mediaUrl` foi removida no D70 (09/08/2026). Ela resolvia caminhos de
// `/media/`, e `/media/` passou a ser 404 no gateway: todo arquivo sai pela
// porta única, com token. Quem precisa de um arquivo usa `@/lib/arquivo`
// (`baixarArquivo`, `baixarParaDisco`, `abrirEmNovaAba`, `useArquivoBlob`).
//
// Removida e não mantida como no-op de propósito: uma função que devolve uma
// URL que sempre dá 404 é mais difícil de achar do que um erro de compilação.
