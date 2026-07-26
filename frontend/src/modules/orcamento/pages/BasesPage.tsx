import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check, Copy, Database, FileDown, FileUp, FolderPlus, Lock, LockOpen, Plus, Search,
  ShieldCheck, Sparkles, Trash2, Undo2, Upload,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
// IE.1 — importar/exportar vêm do kit compartilhado; o módulo não tem mais os seus.
import { BotaoExportar, WizardImportacao } from '@/components/malha'
import { useDesfazerImportacao, useHistorico, useRecurso } from '@/components/malha/impexp/hooks'
import PaginaShell from '../components/PaginaShell'
import {
  Aviso, Btn, Card, CAPS, Empty, Field, inp, Loading, Modal, mono, Pill, SectHead,
  Select, Seletor,
} from '../ui'
import { brl, dataBR, FONTE_ROTULO, mesBR, num } from '../lib'
import {
  useAdotarLote, useAdotarDoBanco, useBancos, useBasesResumo, useComposicaoBanco,
  useComposicaoReferencia, useCopiarDaBasePublica, useCriarBanco, useDestravarBanco,
  useItensBanco, useReferencias, useRemoverBanco, useTravarBanco,
} from '../hooks'

type Aba = 'oficiais' | 'meus' | 'importacoes'

export default function BasesPage() {
  const { hasPermission } = useAuth()
  const [aba, setAba] = useState<Aba>('oficiais')
  const [baseId, setBaseId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [tipo, setTipo] = useState<'' | 'insumo' | 'composicao'>('')
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [espiando, setEspiando] = useState<number | null>(null)
  const [recado, setRecado] = useState('')

  const { data: bases, isLoading: carregandoBases } = useBasesResumo()
  const adotarLote = useAdotarLote()
  const podeAdotar = hasPermission('orcamento.base.adotar')

  const params = useMemo(
    () => ({ base: baseId || undefined, search: busca || undefined, tipo: tipo || undefined, page_size: 50 }),
    [baseId, busca, tipo],
  )
  const referencias = useReferencias(params, aba === 'oficiais' && baseId !== '')
  const composicao = useComposicaoReferencia(espiando ?? undefined)

  const seletor = (
    <Seletor
      compacto
      valor={aba}
      onChange={setAba}
      opcoes={[
        { valor: 'oficiais' as Aba, rotulo: 'Bases oficiais' },
        { valor: 'meus' as Aba, rotulo: 'Meus bancos' },
        { valor: 'importacoes' as Aba, rotulo: 'Importações' },
      ]}
    />
  )

  return (
    <PaginaShell pagina="bases" seletor={seletor}>
      <div style={{ padding: '18px 22px 40px', overflowY: 'auto' }}>
        {aba === 'oficiais' && (
          <>
            <SectHead right={<Pill kind="slate"><Lock size={11} />somente leitura</Pill>}>
              Publicações disponíveis
            </SectHead>

            {carregandoBases ? <Loading /> : !bases || bases.length === 0 ? (
              <Empty>
                Nenhuma base-mãe importada nesta instalação. As bases oficiais (SINAPI, ORSE, SICRO…)
                são carregadas pelo <b>dono da plataforma</b> e valem para todas as empresas —
                nenhum tenant edita, por isso elas são confiáveis como referência de licitação.
              </Empty>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(250px,1fr))', gap: 11, marginBottom: 8 }}>
                  {bases.map(b => {
                    const ativa = baseId === b.base_id
                    return (
                      <Card
                        key={b.base_id}
                        className="orc-lift"
                        onClick={() => setBaseId(ativa ? '' : b.base_id)}
                        style={{
                          cursor: 'pointer', padding: '13px 15px',
                          borderColor: ativa ? 'var(--accent)' : 'var(--line)',
                          background: ativa ? 'var(--accent-soft)' : 'var(--surface)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                          <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--inset)', color: 'var(--ink-3)' }}>
                            {FONTE_ROTULO[b.fonte]}
                          </span>
                          {b.uf && <span style={{ ...CAPS, fontSize: 9 }}>{b.uf}</span>}
                          <Lock size={11} style={{ color: 'var(--ink-3)', marginLeft: 'auto' }} />
                        </div>
                        <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{b.rotulo}</div>
                        <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4 }}>
                          {b.insumos} insumos · {b.composicoes} composições
                        </div>
                        <div style={{ fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 3 }}>
                          {b.adotados_no_catalogo} adotado(s) no seu catálogo
                        </div>
                        <div style={{ ...CAPS, fontSize: 9, marginTop: 5 }}>data-base {mesBR(b.mes_referencia)} · {b.regime_encargos}</div>
                      </Card>
                    )
                  })}
                </div>

                <Aviso tom="info">
                  <ShieldCheck size={15} style={{ flex: 'none', marginTop: 1 }} />
                  <span>
                    Base-mãe é <b>travada por desenho</b> — ninguém no seu tenant consegue editar um preço
                    da SINAPI, nem por engano. Para ajustar coeficiente ou preço, <b>adote</b> o item: ele
                    vira uma cópia no catálogo da empresa, editável, e a base oficial fica intocada.
                  </span>
                </Aviso>

                {baseId !== '' && (
                  <>
                    <SectHead right={
                      podeAdotar && marcados.size > 0 ? (
                        <Btn tam="sm" variant="primary" disabled={adotarLote.isPending} onClick={async () => {
                          const r = await adotarLote.mutateAsync([...marcados])
                          setMarcados(new Set())
                          setRecado(`${r.adotados ?? marcados.size} item(ns) adotado(s) no catálogo da empresa.`)
                        }}>
                          <Check size={13} />Adotar {marcados.size} no catálogo
                        </Btn>
                      ) : undefined
                    }>
                      Explorar a publicação
                    </SectHead>

                    <div style={{ display: 'flex', gap: 8, marginBottom: 11, flexWrap: 'wrap' }}>
                      <Select value={tipo} onChange={e => setTipo(e.target.value as '' | 'insumo' | 'composicao')}>
                        <option value="">Insumos e composições</option>
                        <option value="composicao">Só composições</option>
                        <option value="insumo">Só insumos</option>
                      </Select>
                      <div style={{ position: 'relative', flex: 1, minWidth: 240 }}>
                        <Search size={14} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
                        <input value={busca} onChange={e => setBusca(e.target.value)}
                          placeholder="Código ou descrição" style={{ ...inp, paddingLeft: 30 }} />
                      </div>
                    </div>

                    <Card pad={false} style={{ overflow: 'hidden' }}>
                      {referencias.isLoading ? <Loading /> : (referencias.data?.results.length ?? 0) === 0 ? (
                        <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>Nada encontrado.</div>
                      ) : referencias.data?.results.map(r => {
                        const marcado = marcados.has(r.referencia_id)
                        return (
                          <div key={r.referencia_id}>
                            <div
                              className="orc-linha"
                              onClick={() => podeAdotar && setMarcados(m => {
                                const p = new Set(m)
                                if (p.has(r.referencia_id)) p.delete(r.referencia_id)
                                else p.add(r.referencia_id)
                                return p
                              })}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 13px',
                                borderBottom: '1px solid var(--line-2)', cursor: podeAdotar ? 'pointer' : 'default',
                                background: marcado ? 'var(--accent-soft)' : undefined,
                              }}
                            >
                              {podeAdotar && <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />}
                              <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 78px' }}>{r.codigo}</span>
                              <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {r.descricao}
                              </span>
                              {r.tipo === 'composicao' && (
                                <button
                                  onClick={e => { e.stopPropagation(); setEspiando(espiando === r.referencia_id ? null : r.referencia_id) }}
                                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650 }}
                                >
                                  {espiando === r.referencia_id ? 'fechar' : 'analítica'}
                                </button>
                              )}
                              {r.adotado_item_id && <Pill kind="good">no catálogo</Pill>}
                              <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 40px', textAlign: 'center' }}>{r.unidade}</span>
                              <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink)', flex: '0 0 108px', textAlign: 'right' }}>{brl(r.custo_unitario)}</span>
                            </div>
                            {espiando === r.referencia_id && (
                              <div style={{ background: 'var(--inset)', padding: '9px 14px 12px 44px', borderBottom: '1px solid var(--line-2)' }}>
                                {composicao.isLoading ? <Loading /> : (composicao.data ?? []).length === 0 ? (
                                  <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Sem analítica nesta publicação.</span>
                                ) : (
                                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                                    <tbody>
                                      {composicao.data?.map(c => (
                                        <tr key={c.componente_id}>
                                          <td style={{ ...mono, padding: '3px 6px', color: 'var(--ink-3)', width: 78 }}>{c.filho_codigo}</td>
                                          <td style={{ padding: '3px 6px', color: 'var(--ink-2)' }}>{c.filho_descricao}</td>
                                          <td style={{ padding: '3px 6px', color: 'var(--ink-3)', width: 40 }}>{c.filho_unidade}</td>
                                          <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 90 }}>{num(c.coeficiente)}</td>
                                          <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 100, color: 'var(--ink)' }}>{brl(c.custo_no_item)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </Card>
                    {referencias.data && referencias.data.count > (referencias.data.results.length ?? 0) && (
                      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 8 }}>
                        Mostrando {referencias.data.results.length} de {referencias.data.count} — refine a busca.
                      </p>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}

        {aba === 'meus' && (
          <PainelMeusBancos
            marcadosDaBase={[...marcados]}
            onRecado={setRecado}
            onLimparMarcados={() => setMarcados(new Set())}
          />
        )}

        {aba === 'importacoes' && <PainelImportacoes onRecado={setRecado} />}
      </div>

      {recado && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', zIndex: 95, animation: 'orcToast .22s ease both',
          background: 'var(--brand)', color: 'var(--brand-ink)', padding: '9px 17px',
          borderRadius: 999, fontSize: 12.5, fontWeight: 650, boxShadow: 'var(--shadow-lg)',
        }}>{recado}</div>
      )}
    </PaginaShell>
  )
}

/** Bancos da empresa: criar, travar, navegar os itens e receber cópia da base pública. */
function PainelMeusBancos({ marcadosDaBase, onRecado, onLimparMarcados }: {
  marcadosDaBase: number[]
  onRecado: (m: string) => void
  onLimparMarcados: () => void
}) {
  const { hasPermission } = useAuth()
  const [bancoId, setBancoId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [criando, setCriando] = useState(false)
  const [espiando, setEspiando] = useState<number | null>(null)
  const [marcados, setMarcados] = useState<Set<number>>(new Set())

  const { data: bancos, isLoading } = useBancos()
  const criar = useCriarBanco()
  const travar = useTravarBanco()
  const destravar = useDestravarBanco()
  const remover = useRemoverBanco()
  const adotar = useAdotarDoBanco()
  const copiarDaBase = useCopiarDaBasePublica()
  const composicao = useComposicaoBanco(espiando ?? undefined)

  const podeEditar = hasPermission('orcamento.orcamento.edit')
  const podeAdotar = hasPermission('orcamento.base.adotar')
  const banco = bancos?.find(b => b.banco_id === bancoId)

  const params = useMemo(
    () => ({ banco: bancoId || undefined, search: busca || undefined, page_size: 50 }),
    [bancoId, busca],
  )
  const itens = useItensBanco(params, bancoId !== '')

  return (
    <>
      <SectHead right={podeEditar
        ? <Btn tam="sm" variant="primary" onClick={() => setCriando(true)}><Plus size={13} />Novo banco</Btn>
        : undefined}>
        Bancos de preço da empresa
      </SectHead>

      {isLoading ? <Loading /> : !bancos || bancos.length === 0 ? (
        <Empty acao={podeEditar
          ? <Btn variant="primary" onClick={() => setCriando(true)}><Plus size={14} />Criar o primeiro banco</Btn>
          : undefined}>
          Nenhum banco próprio ainda. É aqui que entram a <b>tabela da prefeitura</b>, o banco
          histórico da empresa e as composições calibradas pelo preço que você realmente pagou —
          isolados do seu tenant, sem tocar nas bases oficiais.
        </Empty>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(262px,1fr))', gap: 11 }}>
          {bancos.map(b => {
            const ativo = bancoId === b.banco_id
            return (
              <Card
                key={b.banco_id}
                className="orc-lift"
                onClick={() => setBancoId(ativo ? '' : b.banco_id)}
                style={{
                  cursor: 'pointer', padding: '13px 15px',
                  borderColor: ativo ? 'var(--accent)' : 'var(--line)',
                  background: ativo ? 'var(--accent-soft)' : 'var(--surface)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                  <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--inset)', color: 'var(--ink-3)' }}>
                    {FONTE_ROTULO[b.fonte]}
                  </span>
                  {b.uf && <span style={{ ...CAPS, fontSize: 9 }}>{b.uf}</span>}
                  <span style={{ marginLeft: 'auto' }}>
                    {b.travado
                      ? <Pill kind="slate" title={`Travado por ${b.travado_por_nome} em ${dataBR(b.travado_em)}`}><Lock size={10} />travado</Pill>
                      : <Pill kind="good">editável</Pill>}
                  </span>
                </div>
                <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{b.nome}</div>
                <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4 }}>
                  {b.total_itens} itens · {b.total_pastas} pasta(s)
                </div>
                <div style={{ ...CAPS, fontSize: 9, marginTop: 5 }}>
                  {b.mes_referencia ? `data-base ${mesBR(b.mes_referencia)}` : 'sem data-base'}
                  {b.obra_nome ? ` · ${b.obra_nome}` : ''}
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {marcadosDaBase.length > 0 && bancos && bancos.length > 0 && podeEditar && (
        <>
          <div style={{ height: 14 }} />
          <Aviso tom="amber">
            <Copy size={15} style={{ flex: 'none', marginTop: 1 }} />
            <span style={{ flex: 1 }}>
              Você marcou <b>{marcadosDaBase.length} item(ns)</b> na aba de bases oficiais. Copie
              para um banco seu e edite coeficiente e preço lá — a base oficial não é tocada.
            </span>
            <Select
              value={bancoId}
              onChange={e => setBancoId(e.target.value ? Number(e.target.value) : '')}
              style={{ maxWidth: 200 }}
            >
              <option value="">Escolha o banco</option>
              {bancos.filter(b => !b.travado).map(b => (
                <option key={b.banco_id} value={b.banco_id}>{b.nome}</option>
              ))}
            </Select>
            <Btn tam="sm" variant="primary" disabled={!bancoId || copiarDaBase.isPending} onClick={async () => {
              const r = await copiarDaBase.mutateAsync({ banco: Number(bancoId), referencias: marcadosDaBase })
              onLimparMarcados()
              onRecado(`${r.criados} item(ns) copiados — agora editáveis no seu banco.`)
            }}>Copiar</Btn>
          </Aviso>
        </>
      )}

      {banco && (
        <>
          <SectHead right={
            <div style={{ display: 'flex', gap: 7 }}>
              {podeAdotar && marcados.size > 0 && (
                <Btn tam="sm" variant="primary" disabled={adotar.isPending} onClick={async () => {
                  const r = await adotar.mutateAsync({ banco: banco.banco_id, itens: [...marcados] })
                  setMarcados(new Set())
                  onRecado(`${r.criados} item(ns) adotados no catálogo da empresa.`)
                }}>
                  <Check size={13} />Adotar {marcados.size}
                </Btn>
              )}
              {podeEditar && (banco.travado ? (
                <Btn tam="sm" disabled={destravar.isPending} onClick={async () => {
                  await destravar.mutateAsync(banco.banco_id)
                  onRecado('Banco destravado — a alteração fica registrada.')
                }}><LockOpen size={13} />Destravar</Btn>
              ) : (
                <Btn tam="sm" disabled={travar.isPending} onClick={async () => {
                  await travar.mutateAsync(banco.banco_id)
                  onRecado('Banco travado. Ninguém edita o preço sem destravar antes.')
                }}><Lock size={13} />Travar</Btn>
              ))}
              {podeEditar && !banco.travado && (
                <Btn tam="sm" variant="perigo" disabled={remover.isPending} onClick={async () => {
                  await remover.mutateAsync(banco.banco_id)
                  setBancoId('')
                  onRecado('Banco excluído.')
                }}><Trash2 size={13} />Excluir</Btn>
              )}
            </div>
          }>
            {banco.nome}
          </SectHead>

          {banco.travado && (
            <Aviso tom="info">
              <ShieldCheck size={15} style={{ flex: 'none', marginTop: 1 }} />
              <span>
                Banco travado em {dataBR(banco.travado_em)} por <b>{banco.travado_por_nome || '—'}</b>.
                Item, coeficiente e pasta ficam somente leitura — a trava vale para o conteúdo, não
                só para o nome.
              </span>
            </Aviso>
          )}

          <div style={{ position: 'relative', margin: '11px 0' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
            <input value={busca} onChange={e => setBusca(e.target.value)}
              placeholder="Buscar neste banco" style={{ ...inp, paddingLeft: 30 }} />
          </div>

          <Card pad={false} style={{ overflow: 'hidden' }}>
            {itens.isLoading ? <Loading /> : (itens.data?.results.length ?? 0) === 0 ? (
              <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                Banco vazio. Importe uma planilha ou copie itens de uma base oficial.
              </div>
            ) : itens.data?.results.map(item => {
              const marcado = marcados.has(item.item_banco_id)
              return (
                <div key={item.item_banco_id}>
                  <div
                    className="orc-linha"
                    onClick={() => podeAdotar && setMarcados(m => {
                      const p = new Set(m)
                      if (p.has(item.item_banco_id)) p.delete(item.item_banco_id)
                      else p.add(item.item_banco_id)
                      return p
                    })}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 13px',
                      borderBottom: '1px solid var(--line-2)', cursor: podeAdotar ? 'pointer' : 'default',
                      background: marcado ? 'var(--accent-soft)' : undefined,
                    }}
                  >
                    {podeAdotar && <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />}
                    <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 120px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.codigo}
                    </span>
                    <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.descricao}
                    </span>
                    {item.tipo === 'composicao' && (
                      <button
                        onClick={e => { e.stopPropagation(); setEspiando(espiando === item.item_banco_id ? null : item.item_banco_id) }}
                        style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650 }}
                      >
                        {espiando === item.item_banco_id ? 'fechar' : 'analítica'}
                      </button>
                    )}
                    {item.adotado_item_id && <Pill kind="good">no catálogo</Pill>}
                    <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 40px', textAlign: 'center' }}>{item.unidade}</span>
                    <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink)', flex: '0 0 108px', textAlign: 'right' }}>{brl(item.custo_unitario)}</span>
                  </div>
                  {espiando === item.item_banco_id && (
                    <div style={{ background: 'var(--inset)', padding: '9px 14px 12px 44px', borderBottom: '1px solid var(--line-2)' }}>
                      {composicao.isLoading ? <Loading /> : (composicao.data ?? []).length === 0 ? (
                        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Sem componentes cadastrados.</span>
                      ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                          <tbody>
                            {composicao.data?.map(c => (
                              <tr key={c.componente_id}>
                                <td style={{ ...mono, padding: '3px 6px', color: 'var(--ink-3)', width: 120 }}>{c.filho_codigo}</td>
                                <td style={{ padding: '3px 6px', color: 'var(--ink-2)' }}>{c.filho_descricao}</td>
                                <td style={{ padding: '3px 6px', color: 'var(--ink-3)', width: 40 }}>{c.filho_unidade}</td>
                                <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 90 }}>{num(c.coeficiente)}</td>
                                <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 100, color: 'var(--ink)' }}>{brl(c.custo_no_item)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </Card>
        </>
      )}

      {criando && (
        <Modal
          titulo="Novo banco de preço"
          onClose={() => setCriando(false)}
          rodape={<Btn onClick={() => setCriando(false)}>Fechar</Btn>}
        >
          <FormNovoBanco
            salvando={criar.isPending}
            onCriar={async dados => {
              const novo = await criar.mutateAsync(dados)
              setCriando(false)
              setBancoId(novo.banco_id)
              onRecado('Banco criado. Importe uma planilha ou copie itens de uma base oficial.')
            }}
          />
        </Modal>
      )}
    </>
  )
}

function FormNovoBanco({ salvando, onCriar }: {
  salvando: boolean
  onCriar: (dados: Record<string, unknown>) => void
}) {
  const [form, setForm] = useState({ nome: '', descricao: '', uf: '', mes: '' })
  const [erro, setErro] = useState('')
  return (
    <>
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Field label="Nome" dica="Ex.: Prefeitura de Aracaju 03/2026, Banco histórico da empresa">
        <input autoFocus value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} style={inp} />
      </Field>
      <Field label="Descrição">
        <input value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} style={inp} />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="UF"><input value={form.uf} maxLength={2} onChange={e => setForm(f => ({ ...f, uf: e.target.value.toUpperCase() }))} style={inp} /></Field>
        <Field label="Data-base"><input type="month" value={form.mes} onChange={e => setForm(f => ({ ...f, mes: e.target.value }))} style={{ ...inp, ...mono }} /></Field>
      </div>
      <Aviso>
        <Database size={15} style={{ flex: 'none', marginTop: 1 }} />
        O banco é <b>da empresa</b>, não de uma obra — a tabela de uma prefeitura serve todas as
        obras daquela cidade.
      </Aviso>
      <div style={{ height: 14 }} />
      <Btn variant="primary" disabled={salvando} onClick={() => {
        if (!form.nome.trim()) { setErro('O nome é obrigatório.'); return }
        onCriar({
          nome: form.nome.trim(),
          descricao: form.descricao.trim(),
          uf: form.uf.trim(),
          mes_referencia: form.mes ? `${form.mes}-01` : null,
        })
      }}>Criar banco</Btn>
    </>
  )
}

/** Importações: o motor de plataforma, com o banco escolhido como destino.
 *
 *  Depois do **IE.1** esta tela não tem mais leitor, conferência nem histórico
 *  próprios: `<WizardImportacao>` é o mesmo componente que qualquer módulo usa
 *  ([funcoesimpexp §10](../../../../../docs/modulos/funcoesimpexp.md)). O que
 *  sobrou aqui é o que **é** do Orçamento: escolher para qual banco vai. */
function PainelImportacoes({ onRecado }: { onRecado: (m: string) => void }) {
  const [bancoDestino, setBancoDestino] = useState<number | ''>('')
  const { data: bancos } = useBancos()
  const { recurso } = useRecurso('orcamento.banco_preco')
  const { data: historico, isLoading, refetch } = useHistorico('orcamento.banco_preco')

  const bancosEditaveis = (bancos ?? []).filter(b => !b.travado)
  const desfazer = useDesfazerImportacao()

  return (
    <>
      <SectHead>Trazer preços para dentro</SectHead>

      {!recurso ? (
        <Empty>
          Importar tabela de preço exige <b>acesso total</b> ao recurso — as permissões
          {' '}<code style={{ ...mono }}>orcamento.base.view</code> e
          {' '}<code style={{ ...mono }}>orcamento.base.adotar</code>. Meia permissão bloqueia:
          arquivo sai inteiro ou não sai.
        </Empty>
      ) : bancosEditaveis.length === 0 ? (
        <Aviso tom="amber">
          <FolderPlus size={15} style={{ flex: 'none', marginTop: 1 }} />
          Você precisa de um banco destravado para receber a importação. Crie um em <b>Meus bancos</b>
          {' '}(ou destrave o existente).
        </Aviso>
      ) : (
        <Card style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <FileUp size={20} style={{ color: 'var(--accent-ink)' }} />
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>Subir planilha ou PDF</div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
              XLSX, CSV ou PDF. O sistema lê, classifica e <b>para na conferência</b> — nada é gravado antes de você decidir.
            </div>
          </div>
          <Select value={bancoDestino} onChange={e => setBancoDestino(e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 220 }}>
            <option value="">Banco de destino</option>
            {bancosEditaveis.map(b => <option key={b.banco_id} value={b.banco_id}>{b.nome}</option>)}
          </Select>
          {bancoDestino ? (
            <WizardImportacao
              tam="md"
              recurso="orcamento.banco_preco"
              contexto={{ banco: Number(bancoDestino) }}
              rotulo="Escolher arquivo"
              onConcluida={resumo => {
                refetch()
                onRecado(
                  resumo.status === 'descartada'
                    ? 'Importação descartada — nada foi gravado.'
                    : `${resumo.aplicadas} linha(s) gravadas no banco.`,
                )
              }}
            />
          ) : (
            <Btn variant="primary" disabled title="Escolha o banco de destino primeiro">
              <Upload size={14} />Escolher arquivo
            </Btn>
          )}
          <BotaoExportar
            tam="md"
            recurso="orcamento.banco_preco"
            recorte={{ banco: Number(bancoDestino) }}
          />
        </Card>
      )}

      <SectHead>Histórico</SectHead>
      {isLoading ? <Loading /> : !historico || historico.length === 0 ? (
        <Empty>Nenhuma importação ainda.</Empty>
      ) : (
        <Card pad={false} style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                {['Quando', 'Arquivo', 'Por', 'Status', 'Lidas', 'Aplicadas', ''].map((h, i) => (
                  <th key={h || i} style={{
                    ...CAPS, padding: '9px 12px', textAlign: i >= 4 ? 'right' : 'left',
                    borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {historico.map(imp => (
                <tr key={imp.importacao_id} className="orc-linha">
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-3)' }}>{dataBR(imp.criada_em)}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink)' }}>{imp.arquivo || '—'}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-3)' }}>{imp.usuario_nome || '—'}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)' }}>
                    <Pill kind={
                      imp.status === 'aplicada' ? 'good'
                        : imp.status === 'conferindo' || imp.status === 'lendo' ? 'amber'
                          : imp.status === 'erro' ? 'danger' : 'slate'
                    }>{imp.status_nome}</Pill>
                  </td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{imp.total}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{imp.aplicadas}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right' }}>
                    {imp.pode_desfazer && (
                      <Btn
                        tam="sm"
                        disabled={desfazer.isPending}
                        title="Restaura o preço e a procedência de cada linha deste lote"
                        onClick={async () => {
                          await desfazer.mutateAsync(imp.importacao_id)
                          refetch()
                          onRecado('Lote desfeito — os preços anteriores voltaram.')
                        }}
                      >
                        <Undo2 size={13} />Desfazer
                      </Btn>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Aviso tom="info">
        <Sparkles size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span>
          <b>Quem importa o quê:</b> o dono da plataforma importa <b>bases-mãe</b>, que valem para
          todas as empresas. Você importa para os <b>seus bancos</b>, que não saem do seu tenant. Os
          dois caminhos usam esta mesma conferência, e o seu tem teto do plano — por linhas em cada
          importação e por linhas acumuladas na empresa.
        </span>
      </Aviso>

      <SectHead>Exportar</SectHead>
      <Card style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <FileDown size={17} style={{ color: 'var(--ink-3)' }} />
        <span style={{ flex: 1, minWidth: 240, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.55 }}>
          Planilha sintética e analítica em XLSX e PDF, curva ABC e cronograma em XLSX — a entrega
          para licitação, cliente e cartório. Fica no botão <b>Exportar</b> da página Orçar, sobre o
          orçamento aberto.
        </span>
        <Link to="/app/orcamento/orcar" style={{ textDecoration: 'none' }}>
          <Btn tam="sm">Ir para Orçar</Btn>
        </Link>
      </Card>
    </>
  )
}
