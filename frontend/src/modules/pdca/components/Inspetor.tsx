import { Link } from 'react-router-dom'
import { ArrowUpRight, X } from 'lucide-react'
import { Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { usePdca } from '../contexto'
import { useGantt, usePlanoCorrente } from '../hooks'
import type { Atividade, PayloadGantt } from '../types'

/** O painel que absorve os verbos e o detalhe sem trocar de rota.
 *  Master-detail in-place é regra Malha; aqui é estrutural — é o que impede
 *  que cada verbo do backend vire uma página. */
export function Inspetor() {
  const { selecao, selecionar, obraId } = usePdca()
  const { plano } = usePlanoCorrente(obraId)
  const { data: gantt } = useGantt(plano?.cronograma_id)

  if (!selecao) return null

  const atividade = selecao.tipo === 'atividade'
    ? gantt?.atividades.find((a) => a.atividade_id === selecao.id)
    : undefined

  return (
    <aside
      aria-label="Detalhe do que está selecionado"
      style={{
        width: 316,
        flexShrink: 0,
        borderLeft: '1px solid var(--line)',
        background: 'var(--surface)',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 8, padding: '11px 14px', borderBottom: '1px solid var(--line-2)',
          position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 2,
        }}
      >
        <span
          style={{
            fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase',
            color: 'var(--ink-3)', fontWeight: 700,
          }}
        >
          {selecao.tipo === 'atividade' ? 'Atividade' : 'Local'}
        </span>
        <button
          type="button"
          onClick={() => selecionar(null)}
          aria-label="Fechar detalhe"
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--ink-3)', display: 'flex', padding: 2,
          }}
        >
          <X size={15} />
        </button>
      </div>

      {atividade && gantt
        ? <FaceAtividade atividade={atividade} gantt={gantt} obraId={obraId} />
        : (
          <div style={{ padding: 16, fontSize: 12.5, color: 'var(--ink-3)' }}>
            O item selecionado não está neste plano.
          </div>
        )}
    </aside>
  )
}

function FaceAtividade(
  { atividade, gantt, obraId }: { atividade: Atividade; gantt: PayloadGantt; obraId: number },
) {
  const avanco = gantt.avanco.por_atividade[String(atividade.atividade_id)]
  const porId = new Map(gantt.atividades.map((a) => [a.atividade_id, a]))
  const antes = gantt.precedencias.filter((p) => p.destino === atividade.atividade_id)
  const depois = gantt.precedencias.filter((p) => p.origem === atividade.atividade_id)
  const naBase = gantt.base.linhas.find((l) => l.codigo === atividade.codigo)

  return (
    <div style={{ padding: '14px 14px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)' }}>
          {atividade.codigo}
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.3, marginTop: 2 }}>
          {atividade.nome}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {atividade.critica && <Pill kind="danger">Caminho crítico</Pill>}
          {atividade.eh_marco && <Pill kind="info">Marco</Pill>}
          {atividade.tem_filhos && <Pill kind="slate">Agrupadora</Pill>}
        </div>
      </div>

      <Bloco titulo="Prazo">
        <Linha rotulo="Duração" valor={atividade.eh_marco ? '—' : `${atividade.duracao_dias} d`} />
        <Linha rotulo="Início" valor={data(atividade.inicio_cedo)} />
        <Linha rotulo="Término" valor={data(atividade.termino_cedo)} />
        <Linha
          rotulo="Folga total"
          valor={atividade.folga_total == null ? semApuracao('o plano ainda não foi calculado') : `${atividade.folga_total} d`}
        />
      </Bloco>

      {naBase && naBase.base_termino && (
        <Bloco titulo="Contra o combinado">
          <Linha rotulo="Término na base" valor={data(naBase.base_termino)} />
          <Linha
            rotulo="Desvio"
            valor={naBase.desvio_dias == null ? '—' : `${naBase.desvio_dias > 0 ? '+' : ''}${naBase.desvio_dias} d`}
            tom={naBase.desvio_dias == null || naBase.desvio_dias === 0
              ? undefined
              : (naBase.desvio_dias > 0 ? 'var(--danger-ink)' : 'var(--good-ink)')}
          />
        </Bloco>
      )}

      <Bloco titulo="Avanço">
        <Linha
          rotulo="Executado"
          valor={avanco?.avanco == null
            ? semApuracao('ninguém apontou avanço nesta atividade')
            : `${avanco.avanco.toFixed(2).replace('.', ',')} %`}
        />
        <Linha rotulo="Lançamentos" valor={String(avanco?.lancamentos ?? 0)} />
        <Linha
          rotulo="Peso"
          valor={atividade.peso == null ? '—' : atividade.peso}
          nota={atividade.peso_origem ? `origem: ${atividade.peso_origem}` : undefined}
        />
      </Bloco>

      {(antes.length > 0 || depois.length > 0) && (
        <Bloco titulo="Rede">
          {antes.map((p) => (
            <Linha
              key={`a${p.precedencia_id}`}
              rotulo="Depende de"
              valor={`${porId.get(p.origem)?.codigo ?? p.origem} ${p.tipo}${p.atraso_dias >= 0 ? '+' : ''}${p.atraso_dias}d`}
            />
          ))}
          {depois.map((p) => (
            <Linha
              key={`d${p.precedencia_id}`}
              rotulo="Libera"
              valor={`${porId.get(p.destino)?.codigo ?? p.destino} ${p.tipo}${p.atraso_dias >= 0 ? '+' : ''}${p.atraso_dias}d`}
            />
          ))}
        </Bloco>
      )}

      <Bloco titulo="Onde isto conversa">
        {atividade.local_rotulo
          ? <Linha rotulo="Local" valor={atividade.local_rotulo} />
          : <Linha rotulo="Local" valor={semApuracao('sem local, fica fora da linha de balanço')} />}
        {atividade.etapa_nome && (
          <LinhaLink rotulo="Etapa da obra" valor={atividade.etapa_nome} para={`/app/obras/${obraId}`} />
        )}
        {atividade.item_orcado_rotulo && (
          <LinhaLink
            rotulo="Item orçado"
            valor={atividade.item_orcado_rotulo}
            para={`/app/orcamento/orcar/obra/${obraId}`}
          />
        )}
        {atividade.responsavel_nome && (
          <LinhaLink
            rotulo="Responsável"
            valor={atividade.responsavel_nome}
            para={`/app/rh/${atividade.responsavel}`}
          />
        )}
        {atividade.calendario_nome && (
          <Linha rotulo="Expediente" valor={atividade.calendario_nome} />
        )}
      </Bloco>
    </div>
  )
}

function data(iso: string | null): string {
  return iso ? dateToBR(iso) : '—'
}

/** Nunca zero onde ninguém mediu: o rótulo diz o que falta. */
function semApuracao(porque: string) {
  return <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }} title={porque}>sem apuração</span>
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        style={{
          fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700, marginBottom: 7,
        }}
      >
        {titulo}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>{children}</div>
    </div>
  )
}

function Linha(
  { rotulo, valor, nota, tom }:
  { rotulo: string; valor: React.ReactNode; nota?: string; tom?: string },
) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, justifyContent: 'space-between' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      <span style={{ textAlign: 'right', minWidth: 0 }}>
        <span
          style={{
            fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
            fontSize: 12.5, color: tom ?? 'var(--ink)',
          }}
        >
          {valor}
        </span>
        {nota && (
          <span style={{ display: 'block', fontSize: 10.5, color: 'var(--ink-3)' }}>{nota}</span>
        )}
      </span>
    </div>
  )
}

function LinhaLink(
  { rotulo, valor, para }: { rotulo: string; valor: string; para: string },
) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, justifyContent: 'space-between' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      <Link
        to={para}
        style={{
          fontSize: 12.5, color: 'var(--brand)', textDecoration: 'none',
          display: 'inline-flex', alignItems: 'center', gap: 3, textAlign: 'right',
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{valor}</span>
        <ArrowUpRight size={12} style={{ flexShrink: 0 }} />
      </Link>
    </div>
  )
}
