import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDownToLine, ArrowUpFromLine, Download, ExternalLink, FolderOpen, Search } from 'lucide-react'
import { Card, Empty, Loading, SectionHead } from '@/components/malha'
import { abrirEmNovaAba, baixarParaDisco } from '@/lib/arquivo'
import { fetchEntraram, fetchGuardados, fetchSairam } from '../api'

type Lente = 'guardados' | 'entraram' | 'sairam'

const quandoBR = (iso: string | null) => (iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: iso.length > 10 ? 'short' : undefined }) : '—')

/**
 * Documentos (DMS) — todo arquivo, dentro e fora do sistema.
 *
 * Três lentes sobre os MESMOS arquivos da porta única (`funcoesimpexp`): o que
 * está guardado em cada módulo, o que entrou por lote e o que saiu (exportação
 * e download). Nada aqui é cópia — o arquivo continua no módulo dono, e abrir é
 * a mesma entrega gateada que a tela do módulo usa. Cada pessoa vê só o que
 * poderia baixar.
 */
export default function DocumentosPage() {
  const [lente, setLente] = useState<Lente>('guardados')

  return (
    <div className="px-6 py-6 flex flex-col gap-5" style={{ color: 'var(--ink-2)' }}>
      <div>
        <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>Documentos</h1>
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
          Todo arquivo do sistema num lugar só: o que está guardado em cada módulo, o que entrou e o que saiu.
        </p>
      </div>
      <div className="flex gap-2">
        {([
          ['guardados', 'Guardados', <FolderOpen key="g" size={15} />],
          ['entraram', 'Entraram', <ArrowDownToLine key="e" size={15} />],
          ['sairam', 'Saíram', <ArrowUpFromLine key="s" size={15} />],
        ] as const).map(([chave, rotulo, icone]) => (
          <button key={chave} type="button" onClick={() => setLente(chave)}
            className="flex items-center gap-1.5 text-sm font-semibold"
            style={{
              padding: '6px 14px', borderRadius: 999, cursor: 'pointer',
              border: '1px solid var(--line)',
              background: lente === chave ? 'var(--ink)' : 'var(--surface)',
              color: lente === chave ? 'var(--surface)' : 'var(--ink-2)',
            }}>
            {icone} {rotulo}
          </button>
        ))}
      </div>
      {lente === 'guardados' && <LenteGuardados />}
      {lente === 'entraram' && <LenteEntraram />}
      {lente === 'sairam' && <LenteSairam />}
    </div>
  )
}

function LenteGuardados() {
  const [busca, setBusca] = useState('')
  const [termo, setTermo] = useState('')
  const [recurso, setRecurso] = useState('')
  const q = useQuery({ queryKey: ['dms', 'guardados', termo, recurso], queryFn: () => fetchGuardados({ busca: termo, recurso }) })

  return (
    <div className="flex flex-col gap-3">
      <form className="flex flex-wrap gap-2 items-center" onSubmit={e => { e.preventDefault(); setTermo(busca.trim()) }}>
        <span className="flex items-center gap-2" style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: '6px 10px', background: 'var(--surface)' }}>
          <Search size={14} />
          <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="Nome, documento, obra, cliente…"
            style={{ border: 'none', outline: 'none', background: 'transparent', width: 260, color: 'var(--ink)' }} />
        </span>
        <select value={recurso} onChange={e => setRecurso(e.target.value)}
          style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: '7px 10px', background: 'var(--surface)', color: 'var(--ink-2)' }}>
          <option value="">Todos os tipos</option>
          {(q.data?.por_recurso ?? []).map(r => <option key={r.recurso} value={r.recurso}>{r.rotulo} ({r.total})</option>)}
        </select>
      </form>

      {q.isLoading && <Loading o="os arquivos" />}
      {q.data && q.data.arquivos.length === 0 && <Empty><FolderOpen size={22} /> Nenhum arquivo encontrado.</Empty>}
      {q.data && q.data.arquivos.length > 0 && (
        <Card pad={false}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>Arquivo</th>
                <th style={{ fontWeight: 600 }}>Tipo</th>
                <th style={{ fontWeight: 600 }}>De</th>
                <th style={{ fontWeight: 600 }}>Desde</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {q.data.arquivos.map(a => (
                <tr key={`${a.recurso}-${a.especie}-${a.chave}`} style={{ borderTop: '1px solid var(--line)' }}>
                  <td style={{ padding: '7px 12px' }}>
                    <div className="font-semibold" style={{ color: 'var(--ink)' }}>{a.titulo || a.nome}</div>
                    {a.titulo && <div className="text-xs" style={{ color: 'var(--ink-3)' }}>{a.nome}</div>}
                  </td>
                  <td className="text-xs">{a.recurso_rotulo}</td>
                  <td className="text-xs">{a.onde || '—'}</td>
                  <td className="text-xs">{quandoBR(a.quando)}</td>
                  <td style={{ whiteSpace: 'nowrap', paddingRight: 12, textAlign: 'right' }}>
                    <button type="button" title="Abrir" onClick={() => abrirEmNovaAba(a.link)}
                      style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 4 }}><ExternalLink size={15} /></button>
                    <button type="button" title="Baixar" onClick={() => baixarParaDisco(a.link, a.nome)}
                      style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 4 }}><Download size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {q.data && (
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
          {q.data.por_recurso.reduce((s, r) => s + r.total, 0)} arquivo(s) no seu alcance; mostrando os {q.data.arquivos.length} mais recentes.
        </p>
      )}
    </div>
  )
}

function LenteEntraram() {
  const q = useQuery({ queryKey: ['dms', 'entraram'], queryFn: fetchEntraram })
  if (q.isLoading) return <Loading o="o que entrou" />
  if (!q.data?.length) return <Empty><ArrowDownToLine size={22} /> Nenhum lote de importação ainda.</Empty>
  return (
    <Card>
      <SectionHead sub="Lotes de planilha e de arquivos que passaram pela conferência">Entraram</SectionHead>
      <table className="w-full text-sm mt-2">
        <tbody>
          {q.data.map(e => (
            <tr key={e.id} style={{ borderTop: '1px solid var(--line)' }}>
              <td style={{ padding: '6px 0' }}><div className="font-semibold" style={{ color: 'var(--ink)' }}>{e.arquivo || '—'}</div>
                <div className="text-xs" style={{ color: 'var(--ink-3)' }}>{e.recurso_rotulo}</div></td>
              <td className="text-xs">{e.situacao}</td>
              <td className="text-xs">{e.aplicadas} de {e.linhas}</td>
              <td className="text-xs">{e.quem || '—'}</td>
              <td className="text-xs" style={{ textAlign: 'right' }}>{quandoBR(e.quando)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function LenteSairam() {
  const q = useQuery({ queryKey: ['dms', 'sairam'], queryFn: fetchSairam })
  if (q.isLoading) return <Loading o="o que saiu" />
  if (!q.data?.length) return <Empty><ArrowUpFromLine size={22} /> Nada saiu ainda.</Empty>
  return (
    <Card>
      <SectionHead sub="Exportações e downloads de arquivo do cliente — a trilha da LGPD">Saíram</SectionHead>
      <table className="w-full text-sm mt-2">
        <tbody>
          {q.data.map((s, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--line)' }}>
              <td style={{ padding: '6px 0' }}><div className="font-semibold" style={{ color: 'var(--ink)' }}>{s.recurso_rotulo}</div>
                <div className="text-xs" style={{ color: 'var(--ink-3)' }}>{s.tipo === 'entrega' ? 'Download' : 'Exportação'} · {s.descricao}</div></td>
              <td className="text-xs">{s.quem || '—'}</td>
              <td className="text-xs" style={{ textAlign: 'right' }}>{quandoBR(s.quando)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
