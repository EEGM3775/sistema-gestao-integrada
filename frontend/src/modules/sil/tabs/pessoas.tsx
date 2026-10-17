import { useState } from 'react'
import {
  ShieldCheck, Plus, Check, Wrench, Hammer, AlertTriangle, RotateCcw, PackageMinus,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import {
  entregasEpiHooks, ferramentasHooks, emprestimosHooks, itensHooks, locaisHooks,
  useTemRh, useDevolverEpi, useAlterarEstadoFerramenta, useDevolverEmprestimo,
} from '../hooks'
import { useQueryClient } from '@tanstack/react-query'
import { BotaoExportar, SeletorDeFuncionario, SeletorDeObra, WizardImportacao } from '@/components/malha'
import { dataBR, epiEstado, ferramentaEstado } from '../lib'
import {
  mono, inp, errBox, Pill, EstadoPill, Card, Btn, SectHead, Loading, Empty, Modal, Field, th, type Say,
} from '../ui'
import type { Item, LocalEstoque, EntregaEPI, Ferramenta, EmprestimoFerramenta } from '../types'

import { minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/** Estados de ferramenta que se escolhem à mão — `emprestada` é do fluxo de empréstimo. */
type EstadoAlteravel = 'disponivel' | 'manutencao' | 'baixada'

/* ── campo de colaborador: usa o RH quando há; senão, texto livre ── */
function ColaboradorField({ temRh, colaborador, setColaborador, nome, setNome }: {
  temRh: boolean; colaborador: string; setColaborador: (v: string) => void; nome: string; setNome: (v: string) => void
}) {
  if (temRh) {
    return (
      <Field label="Colaborador (RH)">
        {/* Busca no servidor (F2); vazio = terceirizado, em texto livre. */}
        <SeletorDeFuncionario valor={colaborador ? Number(colaborador) : null}
          aoMudar={id => setColaborador(id == null ? '' : String(id))} permiteLimpar
          placeholder="— texto livre — busque no RH" aria-label="Colaborador" style={inp} />
        {!colaborador && <input style={{ ...inp, marginTop: 8 }} value={nome} onChange={e => setNome(e.target.value)} placeholder="Nome do colaborador (terceirizado)" />}
      </Field>
    )
  }
  return <Field label="Colaborador"><input style={inp} value={nome} onChange={e => setNome(e.target.value)} placeholder="Nome do colaborador" /></Field>
}

/* ═══════════ EPI (NR-6) ═══════════ */
export function EPI({ say }: { say: Say }) {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('sil.epi.edit')
  const [nova, setNova] = useState(false)
  const { data, isLoading } = entregasEpiHooks.useList({ page_size: 60 })
  const devolver = useDevolverEpi()
  const rows = (data?.results ?? []) as EntregaEPI[]
  return (
    <>
      <div style={{ display: 'flex', gap: 12, padding: '13px 16px', borderRadius: 'var(--r-md)', background: 'var(--info-soft)', border: '1px solid color-mix(in srgb,var(--info) 30%,var(--line))', marginBottom: 4 }}>
        <ShieldCheck size={20} style={{ color: 'var(--info-ink)', flex: 'none' }} />
        <span style={{ fontSize: 12.5, color: 'var(--info-ink)', lineHeight: 1.5 }}><b>NR-6:</b> a entrega de EPI é a prova trabalhista. Cada linha registra <b>quem recebeu</b>, o <b>CA</b> e sua validade, e a devolução/troca. EPI com CA vencido ou troca prevista aparece na fila do painel.</span>
      </div>
      <SectHead right={<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><BotaoExportar recurso="sil.epi" />{podeEditar ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNova(true)}><Plus size={14} /> Registrar entrega</Btn> : null}</div>}>Entregas de EPI</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma entrega de EPI registrada.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 860 }}>
            <thead><tr>{['Colaborador', 'EPI', 'CA', 'Validade CA', 'Entregue', 'Status', ''].map((h, i) => <th key={i} style={th(h, i)}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((e, i) => (
              <tr key={e.entrega_epi_id} style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined, background: e.vencido ? 'var(--danger-soft)' : undefined }}>
                <td style={{ padding: '11px 16px', color: 'var(--ink)', fontWeight: 550 }}>{e.colaborador_label ?? '—'}</td>
                <td style={{ padding: '11px 16px', color: 'var(--ink-2)' }}>{e.item_descricao ?? `#${e.item}`}{e.assinado && <Pill kind="good">assinado</Pill>}</td>
                <td style={{ ...mono, padding: '11px 16px', color: 'var(--ink-2)' }}>{e.ca_numero || '—'}</td>
                <td style={{ ...mono, padding: '11px 16px', color: e.vencido ? 'var(--danger-ink)' : 'var(--ink-2)' }}>{dataBR(e.ca_validade)}{e.vencido && <AlertTriangle size={12} style={{ marginLeft: 5, verticalAlign: -1 }} />}</td>
                <td style={{ ...mono, padding: '11px 16px', fontSize: 12, color: 'var(--ink-3)' }}>{dataBR(e.data_entrega)}</td>
                <td style={{ padding: '11px 16px' }}>{e.vencido ? <Pill kind="danger" pulse>Vencido / trocar</Pill> : <EstadoPill e={epiEstado[e.status]} />}</td>
                <td style={{ padding: '11px 16px', textAlign: 'right' }}>{podeEditar && e.status === 'entregue' && <Btn style={{ padding: '5px 10px', fontSize: 12 }} disabled={devolver.isPending} onClick={async () => { await devolver.mutateAsync(e.entrega_epi_id); say('EPI devolvido') }}><RotateCcw size={12} /> Devolver</Btn>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {nova && <NovaEntregaEPIModal onClose={() => setNova(false)} onDone={() => { setNova(false); say('Entrega de EPI registrada') }} />}
    </>
  )
}
function NovaEntregaEPIModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const create = entregasEpiHooks.useCreate()
  const { data: epiItens } = itensHooks.useAll({ tipo: 'epi' })
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const { data: temRh = false } = useTemRh()
  const [item, setItem] = useState(''), [colaborador, setColaborador] = useState(''), [nome, setNome] = useState('')
  const [local, setLocal] = useState(''), [obra, setObra] = useState(''), [quantidade, setQuantidade] = useState('1')
  const [ca, setCa] = useState(''), [caVal, setCaVal] = useState(''), [troca, setTroca] = useState('')
  const [baixar, setBaixar] = useState(true), [assinado, setAssinado] = useState(true)
  const [saving, setSaving] = useState(false), [err, setErr] = useState('')
  const opItens = (epiItens ?? []) as Item[], opLocais = (locais ?? []) as LocalEstoque[]
  const salvar = async () => {
    setErr('')
    if (!item) return setErr('Escolha o EPI.')
    if (!colaborador && !nome.trim()) return setErr('Informe o colaborador.')
    setSaving(true)
    try {
      await create.mutateAsync({
        item: Number(item), colaborador: colaborador ? Number(colaborador) : null,
        colaborador_nome: colaborador ? '' : nome, local: local ? Number(local) : null,
        obra: obra ? Number(obra) : null, quantidade, ca_numero: ca,
        ca_validade: caVal || null, data_prevista_troca: troca || null,
        assinado, baixar_estoque: baixar,
      })
      onDone()
    } catch { setErr('Não foi possível registrar.'); setSaving(false) }
  }
  return <Modal title="Registrar entrega de EPI" onClose={onClose} wide footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Registrar'}</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="EPI"><select style={inp} value={item} onChange={e => setItem(e.target.value)}><option value="">— selecione —</option>{opItens.map(i => <option key={i.item_id} value={i.item_id}>{i.descricao}</option>)}</select></Field>
      <ColaboradorField temRh={temRh} colaborador={colaborador} setColaborador={setColaborador} nome={nome} setNome={setNome} />
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
      <Field label="Quantidade"><input style={{ ...inp, ...mono }} type="number" min={1} step="1" value={quantidade} onChange={e => setQuantidade(e.target.value)} /></Field>
      <Field label="CA (certificado)"><input style={inp} value={ca} onChange={e => setCa(e.target.value)} placeholder="nº do CA" /></Field>
      <Field label="Validade do CA"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={caVal} onChange={e => setCaVal(e.target.value)} /></Field>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Local (baixa)"><select style={inp} value={local} onChange={e => setLocal(e.target.value)}><option value="">— nenhum —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
      <Field label="Troca prevista"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={troca} onChange={e => setTroca(e.target.value)} /></Field>
    </div>
    <Field label="Obra (apropriação)"><SeletorDeObra valor={obra ? Number(obra) : null} aoMudar={id => setObra(id == null ? '' : String(id))} permiteLimpar placeholder="— nenhuma — busque a obra" aria-label="Obra" style={inp} /></Field>
    <div style={{ display: 'flex', gap: 18, fontSize: 13, color: 'var(--ink-2)' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer' }}><input type="checkbox" checked={baixar} onChange={e => setBaixar(e.target.checked)} /> baixar do estoque</label>
      <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer' }}><input type="checkbox" checked={assinado} onChange={e => setAssinado(e.target.checked)} /> comprovante assinado</label>
    </div>
  </Modal>
}

/* ═══════════ FERRAMENTARIA ═══════════ */
export function Ferramentaria({ say }: { say: Say }) {
  const qcPlanilha = useQueryClient()
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('sil.ferramenta.edit')
  const [nova, setNova] = useState(false), [emprestar, setEmprestar] = useState<Ferramenta | null>(null), [manut, setManut] = useState<Ferramenta | null>(null)
  const { data, isLoading } = ferramentasHooks.useList({ page_size: 60 })
  const { data: empData } = emprestimosHooks.useList({ status: 'emprestada', page_size: 30 })
  const devolver = useDevolverEmprestimo()
  const rows = (data?.results ?? []) as Ferramenta[]
  const emprestimos = (empData?.results ?? []) as EmprestimoFerramenta[]
  return (
    <>
      <SectHead right={<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><BotaoExportar recurso="sil.ferramenta" /><WizardImportacao recurso="sil.ferramenta" onConcluida={() => qcPlanilha.invalidateQueries({ queryKey: ['sil'] })} />{podeEditar ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNova(true)}><Plus size={14} /> Nova ferramenta</Btn> : null}</div>}>Ferramentaria (comodato interno)</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma ferramenta cadastrada.</Empty> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 14 }}>
          {rows.map(f => (
            <Card key={f.ferramenta_id} style={{ display: 'flex', flexDirection: 'column', gap: 11, opacity: f.estado === 'baixada' ? 0.6 : 1 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 11 }}>
                <span style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--inset)', color: 'var(--ink-2)' }}><Hammer size={20} /></span>
                <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 650, fontSize: 14, color: 'var(--ink)', lineHeight: 1.3 }}>{f.nome}</div><div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{f.patrimonio ? `patr. ${f.patrimonio}` : 'sem patrimônio'}{f.local_nome ? ` · ${f.local_nome}` : ''}</div></div>
                <EstadoPill e={ferramentaEstado[f.estado]} />
              </div>
              {(f.manutencao_vencendo || f.calibravel) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11.5, color: f.manutencao_vencendo ? 'var(--danger-ink)' : 'var(--ink-3)' }}>
                  <Wrench size={13} />{f.proxima_calibracao ? `calibrar ${dataBR(f.proxima_calibracao)}` : ''}{f.proxima_calibracao && f.proxima_manutencao ? ' · ' : ''}{f.proxima_manutencao ? `manut. ${dataBR(f.proxima_manutencao)}` : ''}{!f.proxima_calibracao && !f.proxima_manutencao ? 'calibração/manutenção não agendada' : ''}
                </div>
              )}
              {f.emprestimo_ativo && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, padding: '6px 9px', borderRadius: 'var(--r-sm)', background: f.emprestimo_ativo.atrasada ? 'var(--danger-soft)' : 'var(--info-soft)', color: f.emprestimo_ativo.atrasada ? 'var(--danger-ink)' : 'var(--info-ink)' }}>
                  <PackageMinus size={13} /> com <b>{f.emprestimo_ativo.colaborador ?? '—'}</b>{f.emprestimo_ativo.atrasada && ' · em atraso'}
                </div>
              )}
              {podeEditar && (
                <div style={{ display: 'flex', gap: 7, paddingTop: 4 }}>
                  {f.estado === 'disponivel' && <Btn variant="primary" style={{ padding: '6px 11px', fontSize: 12.5 }} onClick={() => setEmprestar(f)}>Emprestar</Btn>}
                  {f.estado === 'emprestada' && f.emprestimo_ativo && <Btn style={{ padding: '6px 11px', fontSize: 12.5 }} disabled={devolver.isPending} onClick={async () => { await devolver.mutateAsync(f.emprestimo_ativo!.emprestimo_id); say('Ferramenta devolvida') }}><Check size={13} /> Devolver</Btn>}
                  <Btn style={{ padding: '6px 11px', fontSize: 12.5 }} onClick={() => setManut(f)}><Wrench size={13} /> Estado</Btn>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <SectHead right={<BotaoExportar recurso="sil.emprestimo" recorte={{ status: 'emprestada' }} />}>Empréstimos em aberto</SectHead>
      {emprestimos.length === 0 ? <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>Nenhum empréstimo em aberto.</div> : (
        <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr>{['Ferramenta', 'Colaborador', 'Emprestada', 'Prev. devolução', 'Status', ''].map((h, i) => <th key={i} style={th(h, i)}>{h}</th>)}</tr></thead>
          <tbody>{emprestimos.map((e, i) => (
            <tr key={e.emprestimo_id} style={{ borderBottom: i < emprestimos.length - 1 ? '1px solid var(--line-2)' : undefined, background: e.atrasada ? 'var(--danger-soft)' : undefined }}>
              <td style={{ padding: '11px 16px', color: 'var(--ink)' }}>{e.ferramenta_nome}{e.ferramenta_patrimonio ? <span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)' }}> · {e.ferramenta_patrimonio}</span> : ''}</td>
              <td style={{ padding: '11px 16px', color: 'var(--ink-2)' }}>{e.colaborador_label ?? '—'}</td>
              <td style={{ ...mono, padding: '11px 16px', fontSize: 12, color: 'var(--ink-3)' }}>{dataBR(e.data_emprestimo)}</td>
              <td style={{ ...mono, padding: '11px 16px', fontSize: 12, color: e.atrasada ? 'var(--danger-ink)' : 'var(--ink-3)' }}>{dataBR(e.data_prevista_devolucao)}</td>
              <td style={{ padding: '11px 16px' }}>{e.atrasada ? <Pill kind="danger" pulse>Atrasada</Pill> : <Pill kind="info">Emprestada</Pill>}</td>
              <td style={{ padding: '11px 16px', textAlign: 'right' }}>{podeEditar && <Btn style={{ padding: '5px 10px', fontSize: 12 }} disabled={devolver.isPending} onClick={async () => { await devolver.mutateAsync(e.emprestimo_id); say('Ferramenta devolvida') }}><Check size={12} /> Devolver</Btn>}</td>
            </tr>
          ))}</tbody>
        </table></Card>
      )}
      {nova && <NovaFerramentaModal onClose={() => setNova(false)} onDone={() => { setNova(false); say('Ferramenta cadastrada') }} />}
      {emprestar && <EmprestarModal ferramenta={emprestar} onClose={() => setEmprestar(null)} onDone={() => { setEmprestar(null); say('Ferramenta emprestada') }} />}
      {manut && <EstadoFerramentaModal ferramenta={manut} onClose={() => setManut(null)} onDone={() => { setManut(null); say('Estado atualizado') }} />}
    </>
  )
}
function NovaFerramentaModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const create = ferramentasHooks.useCreate()
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const [nome, setNome] = useState(''), [patrimonio, setPatrimonio] = useState(''), [local, setLocal] = useState('')
  const [calibravel, setCalibravel] = useState(false), [proxCal, setProxCal] = useState(''), [proxMan, setProxMan] = useState(''), [valor, setValor] = useState('')
  const [err, setErr] = useState('')
  const opLocais = (locais ?? []) as LocalEstoque[]
  const salvar = async () => {
    if (!nome.trim()) return setErr('Informe o nome.')
    try {
      await create.mutateAsync({ nome, patrimonio, local: local ? Number(local) : null, calibravel, proxima_calibracao: proxCal || null, proxima_manutencao: proxMan || null, valor: valor || null })
      onDone()
    } catch { setErr('Não foi possível salvar. O patrimônio já existe?') }
  }
  return <Modal title="Nova ferramenta" onClose={onClose} wide footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={create.isPending}>Cadastrar</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
      <Field label="Nome/descrição"><input style={inp} value={nome} onChange={e => setNome(e.target.value)} placeholder="Ex.: Furadeira de impacto" /></Field>
      <Field label="Nº patrimônio"><input style={inp} value={patrimonio} onChange={e => setPatrimonio(e.target.value)} placeholder="FER-001" /></Field>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Local base"><select style={inp} value={local} onChange={e => setLocal(e.target.value)}><option value="">— nenhum —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
      <Field label="Valor do bem"><input style={{ ...inp, ...mono }} type="number" step="0.01" value={valor} onChange={e => setValor(e.target.value)} placeholder="0,00" /></Field>
    </div>
    <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'var(--ink-2)', marginBottom: 12, cursor: 'pointer' }}><input type="checkbox" checked={calibravel} onChange={e => setCalibravel(e.target.checked)} /> requer calibração</label>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Próxima calibração"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={proxCal} onChange={e => setProxCal(e.target.value)} /></Field>
      <Field label="Próxima manutenção"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={proxMan} onChange={e => setProxMan(e.target.value)} /></Field>
    </div>
  </Modal>
}
function EmprestarModal({ ferramenta, onClose, onDone }: { ferramenta: Ferramenta; onClose: () => void; onDone: () => void }) {
  const create = emprestimosHooks.useCreate()
  const { data: temRh = false } = useTemRh()
  const [colaborador, setColaborador] = useState(''), [nome, setNome] = useState(''), [obra, setObra] = useState(''), [prev, setPrev] = useState('')
  const [err, setErr] = useState('')
  const salvar = async () => {
    if (!colaborador && !nome.trim()) return setErr('Informe o colaborador.')
    try {
      await create.mutateAsync({ ferramenta: ferramenta.ferramenta_id, colaborador: colaborador ? Number(colaborador) : null, colaborador_nome: colaborador ? '' : nome, obra: obra ? Number(obra) : null, data_prevista_devolucao: prev || null })
      onDone()
    } catch { setErr('Não foi possível emprestar.') }
  }
  return <Modal title={`Emprestar — ${ferramenta.nome}`} onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={create.isPending}>Emprestar</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <ColaboradorField temRh={temRh} colaborador={colaborador} setColaborador={setColaborador} nome={nome} setNome={setNome} />
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Obra"><SeletorDeObra valor={obra ? Number(obra) : null} aoMudar={id => setObra(id == null ? '' : String(id))} permiteLimpar placeholder="— nenhuma — busque a obra" aria-label="Obra" style={inp} /></Field>
      <Field label="Devolução prevista"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={prev} onChange={e => setPrev(e.target.value)} /></Field>
    </div>
  </Modal>
}
function EstadoFerramentaModal({ ferramenta, onClose, onDone }: { ferramenta: Ferramenta; onClose: () => void; onDone: () => void }) {
  const alterar = useAlterarEstadoFerramenta()
  // `emprestada` não é estado que se escolhe à mão (quem empresta é o fluxo de
  // empréstimo), então o seletor oferece só os três alteráveis.
  const [estado, setEstado] = useState<EstadoAlteravel>(ferramenta.estado === 'emprestada' ? 'disponivel' : ferramenta.estado)
  const [proxCal, setProxCal] = useState(ferramenta.proxima_calibracao ?? ''), [proxMan, setProxMan] = useState(ferramenta.proxima_manutencao ?? '')
  const salvar = async () => { await alterar.mutateAsync({ id: ferramenta.ferramenta_id, estado, proxima_calibracao: proxCal || null, proxima_manutencao: proxMan || null }); onDone() }
  return <Modal title={`Estado — ${ferramenta.nome}`} onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={alterar.isPending}>Salvar</Btn></>}>
    <Field label="Estado"><select style={inp} value={estado} onChange={e => setEstado(e.target.value as EstadoAlteravel)}><option value="disponivel">Disponível</option><option value="manutencao">Em manutenção</option><option value="baixada">Baixada</option></select></Field>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Próxima calibração"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={proxCal} onChange={e => setProxCal(e.target.value)} /></Field>
      <Field label="Próxima manutenção"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={proxMan} onChange={e => setProxMan(e.target.value)} /></Field>
    </div>
  </Modal>
}
