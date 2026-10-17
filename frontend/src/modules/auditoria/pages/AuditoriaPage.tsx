/** Trilha de auditoria — as duas trilhas numa linha do tempo só (D17).
 *
 *  A plataforma tem **duas** trilhas append-only: a do sistema (`AuditLog` do
 *  backend — escrita de RH, leitura de dado pessoal, baixa, NF, LGPD,
 *  exportação) e a de identidade (`EventoSeguranca` da IAM — senha, e-mail,
 *  papéis, segundo fator, suporte). Reconstituir "uma conta foi tomada" é cruzar
 *  as duas: o reset assistido de um lado e o que a conta fez depois do outro.
 *  Antes isto era feito à mão, com a da IAM legível só por shell.
 *
 *  **A intercalação é honesta.** As duas vêm paginadas, do mais recente para o
 *  mais antigo. Uma linha só aparece quando é certo que nenhuma da outra trilha
 *  cabe acima dela: a fronteira é a última linha carregada da trilha que ainda
 *  tem página. "Carregar mais" puxa a página de quem segura a fronteira.
 *
 *  Clicar num nome recorta as duas trilhas por aquela pessoa.
 */
import { useEffect, useMemo, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { KeyRound, ScrollText, X } from 'lucide-react'
import { Btn, Card, Empty, KpiTile, Loading, Pill, SectionHead } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import * as api from '../api'
import type { FiltroTrilha, LinhaIdentidade, LinhaSistema, Pagina } from '../api'

/** Rótulos do `AuditLog.Acao` (backend/nucleo/models.py). */
const ACAO: Record<string, string> = {
  criar: 'Criação',
  atualizar: 'Atualização',
  excluir: 'Exclusão',
  baixa: 'Baixa financeira',
  emitir_nf: 'Emissão de NF',
  gerar_cobranca: 'Geração de cobrança',
  exportar_lgpd: 'Exportação LGPD',
  anonimizar_lgpd: 'Anonimização LGPD',
  visualizar_pii: 'Visualização de dado pessoal',
  exportar_dados: 'Exportação de dados',
}

type Origem = 'sistema' | 'identidade'

interface Linha {
  chave: string
  origem: Origem
  quando: string
  /** O instante em ms: as duas trilhas escrevem o fuso de jeitos diferentes. */
  ts: number
  /** Quem agiu. Vazio na identidade = o próprio fluxo público (esqueci a senha). */
  quem: string
  oQue: string
  /** Sobre o quê/quem. */
  alvo: string
  detalhe: string
}

function deSistema(l: LinhaSistema): Linha {
  return {
    chave: `s-${l.id}`, origem: 'sistema', quando: l.timestamp, ts: Date.parse(l.timestamp), quem: l.usuario_nome,
    oQue: ACAO[l.acao] ?? l.acao,
    alvo: `${l.modelo}${l.objeto_id ? ` #${l.objeto_id}` : ''}`,
    detalhe: l.detalhes ? resumo(l.detalhes) : '',
  }
}

function deIdentidade(l: LinhaIdentidade): Linha {
  return {
    chave: `i-${l.id}`, origem: 'identidade', quando: l.criado_em, ts: Date.parse(l.criado_em), quem: l.autor_username,
    oQue: l.tipo_rotulo, alvo: l.alvo_username,
    detalhe: [l.ip, resumo(l.detalhes)].filter(Boolean).join(' · '),
  }
}

function resumo(d: Record<string, unknown>): string {
  return Object.entries(d)
    .filter(([, v]) => v !== null && v !== '' && typeof v !== 'object')
    .slice(0, 4)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(' · ')
}

function hojeMenos(dias: number): string {
  const d = new Date()
  d.setDate(d.getDate() - dias)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function dataHora(iso: string) {
  const d = new Date(iso)
  return `${d.toLocaleDateString('pt-BR')} ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
}

function useTrilha<T>(chave: string, filtro: FiltroTrilha, buscar: (f: FiltroTrilha, p: number) => Promise<Pagina<T>>, ligada: boolean) {
  return useInfiniteQuery({
    queryKey: ['auditoria', chave, filtro],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => buscar(filtro, pageParam),
    getNextPageParam: (ultima, todas) => (ultima.next ? todas.length + 1 : undefined),
    enabled: ligada,
    retry: false,
  })
}

export default function AuditoriaPage() {
  const { hasPermission } = useAuth()
  const pode = hasPermission('plataforma.auditoria.view')
  const [desde, setDesde] = useState(() => hojeMenos(30))
  const [ate, setAte] = useState(() => hojeMenos(0))
  const [texto, setTexto] = useState('')
  const [pessoa, setPessoa] = useState('')
  const [origem, setOrigem] = useState<'todas' | Origem>('todas')

  useEffect(() => {
    const t = setTimeout(() => setPessoa(texto.trim()), 300)
    return () => clearTimeout(t)
  }, [texto])

  const filtro = useMemo<FiltroTrilha>(() => ({ desde, ate, pessoa }), [desde, ate, pessoa])
  const sistema = useTrilha('sistema', filtro, api.trilhaDoSistema, pode && origem !== 'identidade')
  const identidade = useTrilha('identidade', filtro, api.trilhaDeIdentidade, pode && origem !== 'sistema')

  const fontes = useMemo(() => {
    const lista: { nome: Origem; linhas: Linha[]; temMais: boolean; buscar: () => void }[] = []
    if (origem !== 'identidade' && !sistema.isError) {
      lista.push({
        nome: 'sistema',
        linhas: (sistema.data?.pages ?? []).flatMap(p => p.results.map(deSistema)),
        temMais: Boolean(sistema.hasNextPage),
        buscar: () => void sistema.fetchNextPage(),
      })
    }
    if (origem !== 'sistema' && !identidade.isError) {
      lista.push({
        nome: 'identidade',
        linhas: (identidade.data?.pages ?? []).flatMap(p => p.results.map(deIdentidade)),
        temMais: Boolean(identidade.hasNextPage),
        buscar: () => void identidade.fetchNextPage(),
      })
    }
    return lista
  }, [origem, sistema, identidade])

  // A fronteira: a última linha carregada de cada trilha que ainda tem página.
  // Abaixo da maior delas pode faltar linha da outra — então não se mostra.
  const { linhas, segurando } = useMemo(() => {
    const comMais = fontes.filter(f => f.temMais && f.linhas.length > 0)
    const limite = comMais.length
      ? comMais.reduce((a, f) => {
        const ultima = f.linhas[f.linhas.length - 1].ts
        return ultima > a.ts ? { ts: ultima, fonte: f } : a
      }, { ts: -Infinity, fonte: comMais[0] })
      : null
    const todas = fontes.flatMap(f => f.linhas)
      .filter(l => !limite || l.ts >= limite.ts)
      .sort((a, b) => b.ts - a.ts)
    return { linhas: todas, segurando: limite?.fonte ?? null }
  }, [fontes])

  if (!pode) {
    return (
      <div style={{ padding: '22px 26px' }}>
        <Empty>A trilha de auditoria é de quem tem a permissão de auditoria (plataforma.auditoria.view).</Empty>
      </div>
    )
  }

  const carregando = (origem !== 'identidade' && sistema.isLoading) || (origem !== 'sistema' && identidade.isLoading)
  const total = (q: typeof sistema | typeof identidade) => q.data?.pages[0]?.count

  return (
    <div style={{ height: '100%', overflowY: 'auto' }}>
      <div style={{ padding: '22px 26px 40px', maxWidth: 1180 }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 680, color: 'var(--ink)', margin: 0 }}>Trilha de auditoria</h1>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 5, maxWidth: 820 }}>
            Quem fez o quê, e quando — o que aconteceu no sistema (financeiro, RH, dado pessoal,
            exportações) e o que aconteceu com as contas (senha, e-mail, papéis, segundo fator) numa
            linha do tempo só. Nada aqui se edita nem se apaga.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
          <KpiTile label="No sistema" valor={total(sistema) ?? (origem === 'identidade' ? '—' : '…')}
            base="registros no período" icon={<ScrollText size={16} />} origem="backend" />
          <KpiTile label="Nas contas" valor={identidade.isError ? '—' : (total(identidade) ?? (origem === 'sistema' ? '—' : '…'))}
            base="eventos de identidade no período" icon={<KeyRound size={16} />} origem="IAM" />
        </div>

        <Card>
          <SectionHead
            sub="Clique num nome para ver só o que aquela pessoa fez — ou sofreu — nas duas trilhas."
            right={
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <label style={rotulo}>de <input type="date" value={desde} max={ate} onChange={e => setDesde(e.target.value)} style={campo} /></label>
                <label style={rotulo}>até <input type="date" value={ate} min={desde} onChange={e => setAte(e.target.value)} style={campo} /></label>
                <input placeholder="Login da pessoa" value={texto} onChange={e => setTexto(e.target.value)}
                  style={{ ...campo, width: 150 }} aria-label="Filtrar por pessoa" />
                <select value={origem} onChange={e => setOrigem(e.target.value as typeof origem)} style={campo} aria-label="Trilha">
                  <option value="todas">As duas trilhas</option>
                  <option value="sistema">Só o sistema</option>
                  <option value="identidade">Só as contas</option>
                </select>
              </div>
            }
          >
            Linha do tempo
          </SectionHead>

          {pessoa && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0 10px' }}>
              <Pill kind="info">pessoa: {pessoa}</Pill>
              <button type="button" onClick={() => setTexto('')} aria-label="Tirar o filtro de pessoa"
                style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}>
                <X size={14} />
              </button>
            </div>
          )}
          {identidade.isError && origem !== 'sistema' && (
            <p style={{ fontSize: 12.5, color: 'var(--danger-ink)', margin: '4px 0 10px' }}>
              A trilha das contas (IAM) não respondeu agora — abaixo está só a do sistema.
            </p>
          )}
          {sistema.isError && origem !== 'identidade' && (
            <p style={{ fontSize: 12.5, color: 'var(--danger-ink)', margin: '4px 0 10px' }}>
              A trilha do sistema não respondeu agora — abaixo está só a das contas.
            </p>
          )}

          {carregando ? (
            <Loading o="a trilha" />
          ) : linhas.length === 0 ? (
            <Empty>Nada registrado no período{pessoa ? ` para ${pessoa}` : ''}.</Empty>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--ink-3)', fontSize: 11.5 }}>
                    <th style={th}>Quando</th><th style={th}>Trilha</th><th style={th}>Quem</th>
                    <th style={th}>O quê</th><th style={th}>Sobre</th><th style={th}>Detalhe</th>
                  </tr>
                </thead>
                <tbody>
                  {linhas.map(l => (
                    <tr key={l.chave} style={{ borderTop: '1px solid var(--line-2)' }}>
                      <td style={{ ...td, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{dataHora(l.quando)}</td>
                      <td style={td}><Pill kind={l.origem === 'sistema' ? 'slate' : 'accent'}>{l.origem === 'sistema' ? 'sistema' : 'conta'}</Pill></td>
                      <td style={td}>
                        {l.quem
                          ? <button type="button" onClick={() => setTexto(l.quem)} style={nome}>{l.quem}</button>
                          : <span style={{ color: 'var(--ink-3)' }} title="O próprio fluxo público (esqueci minha senha)">fluxo público</span>}
                      </td>
                      <td style={td}>{l.oQue}</td>
                      <td style={td}>
                        {l.origem === 'identidade' && l.alvo
                          ? <button type="button" onClick={() => setTexto(l.alvo)} style={nome}>{l.alvo}</button>
                          : l.alvo}
                      </td>
                      <td style={{ ...td, color: 'var(--ink-3)', fontSize: 12 }}>{l.detalhe}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {segurando && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 14 }}>
              <Btn onClick={segurando.buscar}
                disabled={sistema.isFetchingNextPage || identidade.isFetchingNextPage}>
                {sistema.isFetchingNextPage || identidade.isFetchingNextPage ? 'Carregando…' : 'Carregar mais antigos'}
              </Btn>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

const campo: React.CSSProperties = {
  fontSize: 12.5, padding: '6px 9px', borderRadius: 8, border: '1px solid var(--line)',
  background: 'var(--surface)', color: 'var(--ink)',
}
const rotulo: React.CSSProperties = { fontSize: 12, color: 'var(--ink-3)', display: 'flex', gap: 5, alignItems: 'center' }
const th: React.CSSProperties = { padding: '8px 10px', fontWeight: 600 }
const td: React.CSSProperties = { padding: '9px 10px', verticalAlign: 'top', color: 'var(--ink)' }
const nome: React.CSSProperties = {
  border: 'none', background: 'none', padding: 0, cursor: 'pointer',
  color: 'var(--accent-ink, var(--ink))', textDecoration: 'underline', textUnderlineOffset: 2, font: 'inherit',
}
