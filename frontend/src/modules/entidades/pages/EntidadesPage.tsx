import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, KeyRound, Landmark, Plus, Trash2, UserPlus, Users } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import { Btn, Card, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { formatCPFCNPJ } from '@/utils/masks'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useAcessosDaEntidade, useConcederAcesso, useEntidades, useRevogarAcesso, type Entidade,
} from '../api'
import EntidadeForm from '../components/EntidadeForm'

/**
 * As entidades da conta (docs/modulos/entidades.md): quem tem CPF ou CNPJ e,
 * por isso, emite nota, recebe boleto e tem DRE. As **do grupo** têm financeiro
 * aqui — matriz, filiais, SPEs; as **externas** são o dono do empreendimento em
 * que a empresa só executa, ou o sócio de fora de uma SPE.
 *
 * Integração visível: cada entidade mostra os empreendimentos de que é dona ou
 * sócia, e quem tem acesso ao financeiro dela.
 */
export default function EntidadesPage() {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('cadastro.entidade.edit')
  const podeConceder = hasPermission('cadastro.entidade.conceder')
  const { data, isLoading } = useEntidades()
  const [editando, setEditando] = useState<Entidade | 'nova' | null>(null)
  const [escolhida, setEscolhida] = useState<number | null>(null)

  const grupo = (data ?? []).filter(e => !e.externa)
  const externas = (data ?? []).filter(e => e.externa)
  const atual = data?.find(e => e.entidade_id === escolhida) ?? grupo[0] ?? null

  return (
    <div className="px-6 py-6 flex flex-col gap-5" style={{ color: 'var(--ink-2)' }}>
      <div className="flex items-end gap-4 flex-wrap">
        <div className="flex-1" style={{ minWidth: 260 }}>
          <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>Entidades (CNPJs e CPFs)</h1>
          <p className="text-xs" style={{ color: 'var(--ink-3)', maxWidth: 680, lineHeight: 1.5 }}>
            Quem é o dono jurídico de cada coisa. Cada entidade do grupo tem o próprio financeiro, nota fiscal,
            boleto e DRE. Com uma só, o sistema funciona como sempre; a partir da segunda, o ERP ganha a barra
            para escolher de qual empresa você está vendo.
          </p>
        </div>
        {podeEditar && <Btn variant="primary" onClick={() => setEditando('nova')}><Plus size={15} /> Nova entidade</Btn>}
      </div>

      {isLoading && <Loading o="as entidades" />}

      {data && (
        <div className="grid gap-5" style={{ gridTemplateColumns: 'minmax(260px, 340px) 1fr', alignItems: 'start' }}>
          <div className="flex flex-col gap-4">
            <Lista titulo="Do grupo" itens={grupo} atual={atual?.entidade_id} onEscolher={setEscolhida} />
            <Lista titulo="Externas" itens={externas} atual={atual?.entidade_id} onEscolher={setEscolhida}
              vazio="Nenhuma. O dono de um empreendimento em que a empresa só executa aparece aqui." />
          </div>
          {atual ? (
            <Detalhe entidade={atual} podeEditar={podeEditar} podeConceder={podeConceder} onEditar={() => setEditando(atual)} />
          ) : (
            <Empty><Building2 size={22} /> Escolha uma entidade.</Empty>
          )}
        </div>
      )}

      {editando && (
        <EntidadeForm
          entidade={editando === 'nova' ? null : editando}
          grupo={grupo}
          onClose={() => setEditando(null)}
          onSalvo={e => { setEditando(null); setEscolhida(e.entidade_id) }}
        />
      )}
    </div>
  )
}

function Lista({ titulo, itens, atual, onEscolher, vazio }: {
  titulo: string
  itens: Entidade[]
  atual?: number
  onEscolher: (id: number) => void
  vazio?: string
}) {
  return (
    <Card pad={false}>
      <div className="text-xs font-bold uppercase" style={{ padding: '10px 14px', color: 'var(--ink-3)', letterSpacing: '.04em' }}>
        {titulo} · {itens.length}
      </div>
      {itens.length === 0 && vazio && <p className="text-xs" style={{ padding: '0 14px 12px', color: 'var(--ink-3)' }}>{vazio}</p>}
      {itens.map(e => (
        <button key={e.entidade_id} type="button" onClick={() => onEscolher(e.entidade_id)} className="w-full text-left"
          style={{
            padding: '10px 14px', borderTop: '1px solid var(--line)', cursor: 'pointer',
            background: e.entidade_id === atual ? 'var(--surface-2)' : 'transparent', opacity: e.ativa ? 1 : 0.6,
          }}>
          <div className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--ink)' }}>
            {e.nome_fantasia || e.nome}
          </div>
          <div className="text-xs mt-0.5 flex items-center gap-2" style={{ color: 'var(--ink-3)' }}>
            <span>{e.papel_nome}</span>
            <span>{e.documento ? formatCPFCNPJ(e.documento) : 'sem CPF/CNPJ'}</span>
          </div>
        </button>
      ))}
    </Card>
  )
}

function Detalhe({ entidade: e, podeEditar, podeConceder, onEditar }: {
  entidade: Entidade
  podeEditar: boolean
  podeConceder: boolean
  onEditar: () => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <SectionHead
          sub={`${e.papel_nome}${e.matriz_nome ? ` de ${e.matriz_nome}` : ''}`}
          right={podeEditar ? <Btn tam="sm" onClick={onEditar}>Editar</Btn> : undefined}
        >
          {e.nome}
        </SectionHead>
        <div className="flex flex-wrap gap-2 mb-3">
          {e.externa ? <Pill kind="slate">Externa — sem financeiro aqui</Pill> : <Pill kind="good">Do grupo</Pill>}
          {!e.ativa && <Pill kind="danger">Inativa</Pill>}
          {!e.externa && !e.documento && <Pill kind="accent">Falta o CPF/CNPJ para emitir nota e boleto</Pill>}
        </div>
        <dl className="grid gap-x-6 gap-y-2 text-sm" style={{ gridTemplateColumns: 'max-content 1fr' }}>
          <dt style={{ color: 'var(--ink-3)' }}>{e.tipo_pessoa === 'PF' ? 'CPF' : 'CNPJ'}</dt>
          <dd>{e.documento ? formatCPFCNPJ(e.documento) : '—'}</dd>
          {e.nome_fantasia && <><dt style={{ color: 'var(--ink-3)' }}>Nome fantasia</dt><dd>{e.nome_fantasia}</dd></>}
          {(e.cidade || e.estado) && <><dt style={{ color: 'var(--ink-3)' }}>Cidade</dt><dd>{[e.cidade, e.estado].filter(Boolean).join(' / ')}</dd></>}
          {e.cliente_nome && (
            <><dt style={{ color: 'var(--ink-3)' }}>No cadastro de clientes</dt>
              <dd><Link to={`/app/clientes/${e.cliente}`} style={{ color: 'var(--accent-ink)' }}>{e.cliente_nome}</Link></dd></>
          )}
        </dl>
      </Card>

      <Card>
        <SectionHead sub="Os empreendimentos de que ela é dona ou sócia">
          <span className="inline-flex items-center gap-2"><Landmark size={16} /> Empreendimentos</span>
        </SectionHead>
        {e.empreendimentos.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--ink-3)' }}>
            Nenhum. A dona e as cotas de um empreendimento se definem na ficha dele.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {e.empreendimentos.map(emp => (
              <Link key={`${emp.como}-${emp.empreendimento}`} to={`/app/empreendimentos/${emp.empreendimento}`}
                className="flex items-center gap-2 text-sm" style={{ color: 'var(--ink)', textDecoration: 'none' }}>
                <strong>{emp.nome}</strong>
                {emp.como === 'propria'
                  ? <Pill kind="info">{e.externa ? 'dona (de terceiro)' : 'entidade própria'}</Pill>
                  : <Pill kind="slate">{emp.cota}%{emp.administradora ? ' · administradora' : ''}</Pill>}
              </Link>
            ))}
          </div>
        )}
      </Card>

      {!e.externa && <Acessos entidade={e} podeConceder={podeConceder} />}
    </div>
  )
}

interface Pessoa { id: number; nome: string; username: string }

function Acessos({ entidade, podeConceder }: { entidade: Entidade; podeConceder: boolean }) {
  const acessos = useAcessosDaEntidade(entidade.entidade_id, podeConceder)
  const conceder = useConcederAcesso()
  const revogar = useRevogarAcesso()
  const pessoas = useQuery({
    queryKey: ['entidades', 'pessoas'],
    queryFn: async () => (await apiClient.get<Pessoa[]>('acessos-entidades/usuarios/')).data,
    enabled: podeConceder,
  })
  const [usuario, setUsuario] = useState('')
  const [filiais, setFiliais] = useState(false)
  const jaTem = useMemo(() => new Set((acessos.data ?? []).map(a => a.usuario)), [acessos.data])
  const erro = conceder.error ? parseApiErrors(conceder.error) : {}

  if (!podeConceder) {
    return (
      <Card>
        <SectionHead><span className="inline-flex items-center gap-2"><KeyRound size={16} /> Quem acessa o financeiro</span></SectionHead>
        <p className="text-sm" style={{ color: 'var(--ink-3)' }}>
          Quem dá e tira o acesso ao financeiro desta entidade é o administrador da empresa, ou quem tem a
          permissão "Dar e tirar acesso de usuários a entidades" em Papéis e Acessos.
        </p>
      </Card>
    )
  }

  return (
    <Card>
      <SectionHead sub="No ERP, cada pessoa vê só as entidades liberadas para ela. O administrador vê todas.">
        <span className="inline-flex items-center gap-2"><KeyRound size={16} /> Quem acessa o financeiro</span>
      </SectionHead>
      {acessos.isLoading && <Loading o="os acessos" />}
      {acessos.data?.length === 0 && <p className="text-sm" style={{ color: 'var(--ink-3)' }}>Ninguém além do administrador.</p>}
      <div className="flex flex-col gap-1.5">
        {acessos.data?.map(a => (
          <div key={a.concessao_id} className="flex items-center gap-2 text-sm">
            <Users size={14} style={{ color: 'var(--ink-3)' }} />
            <span style={{ color: 'var(--ink)' }}>{a.usuario_nome}</span>
            {a.incluir_filiais && <Pill kind="info">com as filiais</Pill>}
            <button type="button" onClick={() => revogar.mutate(a.concessao_id)} title="Tirar o acesso"
              className="ml-auto" style={{ color: 'var(--danger-ink)', background: 'none', border: 'none', cursor: 'pointer' }}>
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
      <div className="flex items-end gap-2 flex-wrap mt-4 pt-3" style={{ borderTop: '1px dashed var(--line)' }}>
        <label className="flex flex-col gap-1 text-xs" style={{ minWidth: 220, flex: 1 }}>
          Dar acesso a
          <select value={usuario} onChange={ev => setUsuario(ev.target.value)}
            style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)' }}>
            <option value="">Escolha a pessoa…</option>
            {(pessoas.data ?? []).filter(p => !jaTem.has(p.id)).map(p => (
              <option key={p.id} value={p.id}>{p.nome}</option>
            ))}
          </select>
        </label>
        {entidade.papel === 'matriz' && (
          <label className="flex items-center gap-1.5 text-xs" style={{ paddingBottom: 8 }}>
            <input type="checkbox" checked={filiais} onChange={ev => setFiliais(ev.target.checked)} /> incluir as filiais
          </label>
        )}
        <Btn tam="sm" variant="primary" disabled={!usuario || conceder.isPending}
          onClick={() => conceder.mutate(
            { usuario: Number(usuario), entidade: entidade.entidade_id, incluir_filiais: filiais },
            { onSuccess: () => { setUsuario(''); setFiliais(false) } },
          )}>
          <UserPlus size={14} /> Dar acesso
        </Btn>
      </div>
      <p className="text-xs mt-2" style={{ color: 'var(--ink-3)' }}>
        Aparece na lista quem já entrou no sistema ao menos uma vez.
        {(erro._form || erro.usuario) && <span style={{ color: 'var(--danger-ink)' }}> {erro._form ?? erro.usuario}</span>}
      </p>
    </Card>
  )
}
