import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'

/**
 * Quem mais está vendo esta prancha agora — o **seam**, declarado e inerte.
 *
 * Presença é a única coisa desta tela que o frontend não consegue responder
 * sozinho: saber que **outra pessoa** abriu o mesmo arquivo exige alguém no meio
 * (um heartbeat no servidor). Não há endpoint disso no `moduloprancheta` de
 * hoje, e não há caminho honesto de simular: `localStorage` e `BroadcastChannel`
 * só enxergam o mesmo navegador, então mostrariam "1 pessoa vendo" — você — como
 * se fosse companhia.
 *
 * Então o slot existe na tela com o selo "em breve", e o cliente já está escrito
 * inteiro aqui, **desligado por uma constante**. A fatia de backend que o acende
 * é pequena e reusa o que a plataforma já tem:
 *
 * 1. `POST /api/prancheta/revisoes/<id>/presenca/` como *heartbeat* (a cada 30 s
 *    enquanto a prancha está aberta), gravando `SETEX presenca:<revisao>:<user>`
 *    no Redis com TTL de ~90 s — o mesmo Redis da revogação de sessão (D7) e dos
 *    baldes de rate limit;
 * 2. o `GET` do mesmo caminho devolve quem ainda está no ar, escopado por tenant.
 *
 * TTL em vez de "avisar ao sair" porque o celular do canteiro perde sinal,
 * bloqueia e volta: presença que depende de despedida vive cheia de fantasma.
 */

export interface PessoaPresente {
  nome: string
  /** Iniciais para o avatar — não há foto de usuário na plataforma. */
  iniciais: string
}

export interface Presenca {
  /** `false` enquanto o heartbeat não existir no backend. */
  suportado: boolean
  pessoas: PessoaPresente[]
}

/** O interruptor da fatia. Vira `true` junto com o endpoint, e nada mais muda. */
export const SUPORTE_A_PRESENCA = false

const AUSENTE: Presenca = { suportado: SUPORTE_A_PRESENCA, pessoas: [] }

const buscarPresenca = (revisaoId: number) =>
  apiClient
    .get<{ pessoas: PessoaPresente[] }>(`/prancheta/revisoes/${revisaoId}/presenca/`)
    .then((r) => ({ suportado: true, pessoas: r.data.pessoas }))

export function usePresenca(revisaoId: number | null): Presenca {
  const { data } = useQuery({
    queryKey: ['prancheta', 'presenca', revisaoId],
    queryFn: () => buscarPresenca(revisaoId as number),
    // Desligado hoje pela constante — o `enabled` é o que mantém a chamada
    // inerte sem precisar comentar código.
    enabled: SUPORTE_A_PRESENCA && !!revisaoId,
    // Presença é dado vivo: sem refetch, o avatar de quem saiu fica na tela.
    refetchInterval: 30_000,
    staleTime: 0,
  })
  return data ?? AUSENTE
}
