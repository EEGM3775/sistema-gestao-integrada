import type { ReactNode } from 'react'
import { Btn, Card, Pill } from '@/components/malha'
import { dataHora, emDias } from '../formato'
import type { useNcs, useOcorrencias } from '../hooks'
import { TOM_DA_GRAVIDADE, TOM_DO_STATUS_DA_NC, TOM_DO_STATUS_DA_OCORRENCIA } from '../vocabulario'

type Ocorrencia = NonNullable<ReturnType<typeof useOcorrencias>['data']>[number]
type Nc = NonNullable<ReturnType<typeof useNcs>['data']>[number]

/** **O que está em aberto no posto, dentro da fila dele** (achado do dono, 17/10/2026).
 *
 *  A fila só mostra o que está *parado* — a ocorrência que já tem investigação
 *  aberta, o defeito que já tem plano, saem dela. Com isso o posto dizia "nada
 *  parado" enquanto havia ocorrência correndo, e parecia que ela não existia.
 *  Enquanto estiver em aberto, ela aparece aqui. Cada posto com a sua: Segurança
 *  lista ocorrências, Qualidade lista defeitos. */
function Bloco({ titulo, total, aoVerTodas, children }: {
  titulo: string; total: number; aoVerTodas: () => void; children: ReactNode
}) {
  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px' }}>
        <strong style={{ fontSize: 13.5, color: 'var(--ink)', flex: 1 }}>
          {titulo} <span style={{ color: 'var(--ink-3)', fontWeight: 500 }}>· {total}</span>
        </strong>
        <Btn onClick={aoVerTodas}>Ver todas</Btn>
      </div>
      {children}
    </Card>
  )
}

const linha = {
  display: 'flex', alignItems: 'flex-start', gap: 12, width: '100%', padding: '10px 14px',
  border: 'none', borderTop: '1px solid var(--line-2)', background: 'transparent',
  cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
} as const
const uma = { fontSize: 13, color: 'var(--ink)', marginTop: 5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const
const sub = { fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 } as const

export const ocorrenciaEmAberto = (o: Ocorrencia) => o.status === 'aberta' || o.status === 'em_investigacao'
export const ncEmAberto = (nc: Nc) => nc.status === 'aberta' || nc.status === 'em_tratamento'

export function OcorrenciasEmAberto({ itens, aoAbrir, aoVerTodas }: {
  itens: Ocorrencia[]; aoAbrir: (id: number) => void; aoVerTodas: () => void
}) {
  return (
    <Bloco titulo="Ocorrências em aberto" total={itens.length} aoVerTodas={aoVerTodas}>
      {itens.map((o) => (
        <button key={o.ocorrencia_id} type="button" onClick={() => aoAbrir(o.ocorrencia_id)} style={linha}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <Pill kind={o.exige_cat ? 'danger' : 'slate'}>{o.tipo_rotulo.split(' (')[0]}</Pill>
              <Pill kind={TOM_DO_STATUS_DA_OCORRENCIA[o.status]}>
                {o.status === 'em_investigacao' ? 'Em investigação' : 'Aberta'}
              </Pill>
              {o.exige_cat && !o.cat_emitida_em && <Pill kind="danger">CAT pendente</Pill>}
            </div>
            <div style={uma}>{o.descricao}</div>
            <div style={sub}>{dataHora(o.ocorrido_em)}{o.local_rotulo && ` · ${o.local_rotulo}`}</div>
          </div>
        </button>
      ))}
    </Bloco>
  )
}

export function NcsEmAberto({ itens, aoAbrir, aoVerTodas }: {
  itens: Nc[]; aoAbrir: (id: number) => void; aoVerTodas: () => void
}) {
  return (
    <Bloco titulo="Defeitos em aberto" total={itens.length} aoVerTodas={aoVerTodas}>
      {itens.map((nc) => {
        const dias = Math.floor((Date.now() - new Date(nc.aberta_em).getTime()) / 86_400_000)
        return (
          <button key={nc.nc_id} type="button" onClick={() => aoAbrir(nc.nc_id)} style={linha}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <Pill kind={TOM_DA_GRAVIDADE[nc.gravidade]}>{nc.gravidade_rotulo.split(' — ')[0]}</Pill>
                <Pill kind={TOM_DO_STATUS_DA_NC[nc.status]}>{nc.status_rotulo}</Pill>
              </div>
              <div style={uma}>{nc.descricao}</div>
              <div style={sub}>
                {[nc.local_rotulo, nc.atividade_nome].filter(Boolean).join(' · ') || 'sem local'}
                {nc.estado.falta && <> · falta {nc.estado.falta}</>}
              </div>
            </div>
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)', flexShrink: 0 }}>
              {dias <= 0 ? 'hoje' : `há ${emDias(dias)}`}
            </span>
          </button>
        )
      })}
    </Bloco>
  )
}
