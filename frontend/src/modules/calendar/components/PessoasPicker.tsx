import { X } from 'lucide-react'
import { SelectComBusca } from '@/components/malha'
import type { Pessoa, RsvpStatus } from '../types'
import { inputStyle } from '../formStyles'

export interface PessoaEscolhida {
  id: number
  nome: string
  /** Resposta ao convite, quando a lista é de convidados. */
  status?: RsvpStatus
}

const STATUS: Record<RsvpStatus, { rotulo: string; cor: string; fundo: string }> = {
  pendente: { rotulo: 'aguardando', cor: '#92400e', fundo: '#fef3c7' },
  aceito: { rotulo: 'vai', cor: '#166534', fundo: '#dcfce7' },
  recusado: { rotulo: 'não vai', cor: '#991b1b', fundo: '#fee2e2' },
}

interface Props {
  valor: PessoaEscolhida[]
  aoMudar: (pessoas: PessoaEscolhida[]) => void
  /** Quem não entra na lista (o dono do evento ou da agenda). */
  excluir?: number[]
  placeholder?: string
  disabled?: boolean
  'aria-label'?: string
}

/**
 * Escolher **várias** pessoas da empresa — convidados de um evento ou membros de
 * uma agenda de equipe (Fatia D). A busca é no servidor (`/calendar/pessoas/`,
 * pelo `SelectComBusca`): a empresa pode ter centenas de usuários e ninguém
 * precisa rolar uma lista inteira para achar um colega.
 */
export function PessoasPicker({ valor, aoMudar, excluir = [], placeholder, disabled, ...aria }: Props) {
  const ja = new Set([...valor.map(p => p.id), ...excluir])

  return (
    <div className="flex flex-col gap-2">
      {valor.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Pessoas escolhidas">
          {valor.map(p => {
            const st = p.status ? STATUS[p.status] : null
            return (
              <li key={p.id} className="inline-flex items-center gap-1.5 rounded-full pl-2.5 pr-1 py-0.5 text-xs"
                style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                {p.nome}
                {st && (
                  <span className="rounded-full px-1.5 text-[0.68rem] font-semibold" style={{ background: st.fundo, color: st.cor }}>
                    {st.rotulo}
                  </span>
                )}
                {!disabled && (
                  <button type="button" aria-label={`Tirar ${p.nome}`} title="Tirar"
                    onClick={() => aoMudar(valor.filter(x => x.id !== p.id))}
                    className="p-0.5 rounded-full" style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}>
                    <X size={12} />
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {!disabled && (
        <SelectComBusca<Pessoa>
          recurso="/calendar/pessoas/"
          idDe={p => p.id}
          rotuloDe={p => (ja.has(p.id) ? `${p.nome} ✓` : p.nome)}
          detalheDe={p => (p.nome !== p.username ? p.username : null)}
          valor={null}
          aoMudar={(id, item) => {
            if (id == null || !item || ja.has(id)) return
            aoMudar([...valor, { id, nome: item.nome }])
          }}
          placeholder={placeholder ?? 'Busque pelo nome para adicionar…'}
          vazio="Ninguém além de você nesta empresa."
          aria-label={aria['aria-label']}
          style={inputStyle}
        />
      )}
    </div>
  )
}
