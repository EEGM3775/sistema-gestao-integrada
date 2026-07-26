import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Database, PackageSearch, Plus, Search, Sparkles } from 'lucide-react'
import { Aviso, Btn, CAPS, Field, inp, Loading, Modal, mono, Pill, Select } from '../ui'
import { brl, FONTE_ROTULO, num } from '../lib'
import * as api from '../api/orcamentoApi'
import { orcKeys } from '../api/queryKeys'
import { useBasesResumo, useComposicaoReferencia } from '../hooks'
import type { CatalogoItem, InsumoReferencia } from '../types'

type Origem = 'base' | 'catalogo' | 'novo'

export interface Escolha { itemCatalogoId: number; descricao: string }

/** As três origens que todo software de orçamento oferece no "inserir item":
 *  a base oficial, o catálogo da própria empresa e a criação de um item novo. */
export default function InserirItemModal({ onFechar, onInserir, inserindo }: {
  onFechar: () => void
  onInserir: (escolhas: Escolha[]) => Promise<void> | void
  inserindo: boolean
}) {
  const [origem, setOrigem] = useState<Origem>('base')
  const { data: bases } = useBasesResumo()
  const [baseId, setBaseId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [tipo, setTipo] = useState<'' | 'insumo' | 'composicao'>('')
  const [marcados, setMarcados] = useState<Map<number, InsumoReferencia>>(new Map())
  const [marcadosCatalogo, setMarcadosCatalogo] = useState<Map<number, CatalogoItem>>(new Map())
  const [espiando, setEspiando] = useState<number | null>(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    if (baseId === '' && bases && bases.length > 0) setBaseId(bases[0].base_id)
  }, [bases, baseId])

  const paramsRef = useMemo(
    () => ({ base: baseId || undefined, search: busca || undefined, tipo: tipo || undefined, page_size: 40 }),
    [baseId, busca, tipo],
  )
  const referencias = useQuery({
    queryKey: orcKeys.referencias.list(paramsRef),
    queryFn: () => api.referencias.listar(paramsRef),
    enabled: origem === 'base' && baseId !== '',
  })
  const catalogo = useQuery({
    queryKey: orcKeys.catalogo(busca),
    queryFn: () => api.buscarNoCatalogo(busca),
    enabled: origem === 'catalogo',
  })
  const composicao = useComposicaoReferencia(espiando ?? undefined)

  const [novo, setNovo] = useState({ codigo_interno: '', descricao: '', unidade: '', categoria: '', tipo: 'material' })

  const totalMarcado = marcados.size + marcadosCatalogo.size

  async function confirmar() {
    setErro('')
    try {
      const escolhas: Escolha[] = []
      if (marcados.size) {
        // `adotados` é a contagem; os ids vêm em `itens` — e com a descrição já
        // do catálogo, então não há pareamento por índice para sair errado.
        const resultado = await api.adotarLote([...marcados.keys()])
        for (const item of resultado.itens ?? []) {
          escolhas.push({ itemCatalogoId: item.item_id, descricao: item.descricao })
        }
      }
      for (const item of marcadosCatalogo.values()) {
        escolhas.push({ itemCatalogoId: item.item_id, descricao: item.descricao })
      }
      if (!escolhas.length) { setErro('Marque ao menos um item.'); return }
      await onInserir(escolhas)
    } catch {
      setErro('Não foi possível inserir. Verifique se você tem permissão de adoção no catálogo.')
    }
  }

  async function criarEInserir() {
    setErro('')
    if (!novo.descricao.trim() || !novo.unidade.trim()) { setErro('Descrição e unidade são obrigatórias.'); return }
    try {
      const criado = await api.criarItemNoCatalogo({
        codigo_interno: novo.codigo_interno.trim() || novo.descricao.trim().slice(0, 40).toUpperCase().replace(/\s+/g, '-'),
        descricao: novo.descricao.trim(),
        unidade: novo.unidade.trim(),
        categoria: novo.categoria.trim(),
        tipo: novo.tipo,
      })
      await onInserir([{ itemCatalogoId: criado.item_id, descricao: criado.descricao }])
    } catch {
      setErro('Não foi possível criar o item. Código interno duplicado ou permissão `cadastro.item.edit` ausente.')
    }
  }

  const abas: { chave: Origem; rotulo: string; icone: React.ReactNode }[] = [
    { chave: 'base', rotulo: 'Base de preço', icone: <Database size={13} /> },
    { chave: 'catalogo', rotulo: 'Catálogo da empresa', icone: <PackageSearch size={13} /> },
    { chave: 'novo', rotulo: 'Criar novo', icone: <Plus size={13} /> },
  ]

  return (
    <Modal
      titulo="Inserir item na planilha"
      onClose={onFechar}
      largura={880}
      rodape={
        <>
          <span style={{ marginRight: 'auto', fontSize: 12, color: 'var(--ink-3)' }}>
            {origem === 'novo'
              ? 'O item novo entra no catálogo da empresa e fica disponível para o SCM comprar e o SIL estocar.'
              : `${totalMarcado} item(ns) marcado(s) — a quantidade se digita direto na grade depois.`}
          </span>
          <Btn onClick={onFechar}>Cancelar</Btn>
          {origem === 'novo'
            ? <Btn variant="primary" onClick={criarEInserir} disabled={inserindo}>Criar e inserir</Btn>
            : <Btn variant="primary" onClick={confirmar} disabled={inserindo || totalMarcado === 0}>
                <Check size={14} />Inserir {totalMarcado > 0 ? `(${totalMarcado})` : ''}
              </Btn>}
        </>
      }
    >
      <div style={{ display: 'flex', gap: 3, marginBottom: 14, borderBottom: '1px solid var(--line)' }}>
        {abas.map(a => (
          <button
            key={a.chave}
            onClick={() => setOrigem(a.chave)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, border: 'none', background: 'none',
              padding: '8px 13px', fontSize: 13, fontWeight: 650, cursor: 'pointer',
              color: origem === a.chave ? 'var(--ink)' : 'var(--ink-3)',
              borderBottom: `2px solid ${origem === a.chave ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -1,
            }}
          >{a.icone}{a.rotulo}</button>
        ))}
      </div>

      {erro && <Aviso tom="danger">{erro}</Aviso>}

      {origem === 'base' && (
        <>
          {!bases || bases.length === 0 ? (
            <Aviso tom="amber">
              <Database size={15} style={{ flex: 'none', marginTop: 1 }} />
              Nenhuma base de preço importada ainda. Enquanto não houver SINAPI, ORSE ou um banco
              próprio, use o catálogo da empresa ou crie o item na terceira aba.
            </Aviso>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 8, marginBottom: 11, flexWrap: 'wrap' }}>
                <Select value={baseId} onChange={e => setBaseId(Number(e.target.value))} style={{ maxWidth: 290 }}>
                  {bases.map(b => <option key={b.base_id} value={b.base_id}>{b.rotulo}</option>)}
                </Select>
                <Select value={tipo} onChange={e => setTipo(e.target.value as '' | 'insumo' | 'composicao')}>
                  <option value="">Insumos e composições</option>
                  <option value="composicao">Só composições (serviços)</option>
                  <option value="insumo">Só insumos</option>
                </Select>
                <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                  <Search size={14} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
                  <input
                    autoFocus
                    value={busca}
                    onChange={e => setBusca(e.target.value)}
                    placeholder="Código ou descrição — ex.: 87879, chapisco, alvenaria"
                    style={{ ...inp, paddingLeft: 30 }}
                  />
                </div>
              </div>

              <div style={{ maxHeight: 330, overflowY: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)' }}>
                {referencias.isLoading ? <Loading /> : (referencias.data?.results.length ?? 0) === 0 ? (
                  <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                    Nada encontrado nesta publicação.
                  </div>
                ) : referencias.data?.results.map(r => {
                  const marcado = marcados.has(r.referencia_id)
                  return (
                    <div key={r.referencia_id}>
                      <div
                        onClick={() => setMarcados(m => {
                          const p = new Map(m)
                          if (p.has(r.referencia_id)) p.delete(r.referencia_id)
                          else p.set(r.referencia_id, r)
                          return p
                        })}
                        className="orc-linha"
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10, padding: '8px 11px',
                          borderBottom: '1px solid var(--line-2)', cursor: 'pointer',
                          background: marcado ? 'var(--accent-soft)' : undefined,
                        }}
                      >
                        <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />
                        <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--inset)', color: 'var(--ink-3)', flex: 'none' }}>
                          {FONTE_ROTULO[r.base_fonte]}
                        </span>
                        <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 74px' }}>{r.codigo}</span>
                        <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.descricao}
                        </span>
                        {r.tipo === 'composicao' && (
                          <button
                            onClick={e => { e.stopPropagation(); setEspiando(espiando === r.referencia_id ? null : r.referencia_id) }}
                            style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650 }}
                          >
                            {espiando === r.referencia_id ? 'fechar' : 'ver analítica'}
                          </button>
                        )}
                        {r.adotado_item_id && <Pill kind="good">já no catálogo</Pill>}
                        <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 38px', textAlign: 'center' }}>{r.unidade}</span>
                        <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink)', flex: '0 0 104px', textAlign: 'right' }}>{brl(r.custo_unitario)}</span>
                      </div>

                      {espiando === r.referencia_id && (
                        <div style={{ background: 'var(--inset)', padding: '9px 14px 12px 42px', borderBottom: '1px solid var(--line-2)' }}>
                          <div style={{ ...CAPS, marginBottom: 6 }}>Composição analítica — memória de cálculo</div>
                          {composicao.isLoading ? <Loading /> : (composicao.data ?? []).length === 0 ? (
                            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Esta publicação não trouxe a analítica desta composição.</span>
                          ) : (
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                              <thead>
                                <tr>
                                  {['Código', 'Insumo', 'Und', 'Coeficiente', 'Custo unit.', 'Parcela'].map((h, i) => (
                                    <th key={h} style={{ ...CAPS, fontSize: 9, textAlign: i >= 3 ? 'right' : 'left', padding: '3px 6px' }}>{h}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {composicao.data?.map(c => (
                                  <tr key={c.componente_id}>
                                    <td style={{ ...mono, padding: '3px 6px', color: 'var(--ink-3)' }}>{c.filho_codigo}</td>
                                    <td style={{ padding: '3px 6px', color: 'var(--ink-2)' }}>{c.filho_descricao}</td>
                                    <td style={{ padding: '3px 6px', color: 'var(--ink-3)' }}>{c.filho_unidade}</td>
                                    <td style={{ ...mono, padding: '3px 6px', textAlign: 'right' }}>{num(c.coeficiente)}</td>
                                    <td style={{ ...mono, padding: '3px 6px', textAlign: 'right' }}>{brl(c.filho_custo_unitario)}</td>
                                    <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', color: 'var(--ink)' }}>{brl(c.custo_no_item)}</td>
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
              </div>
              <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 9, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <Sparkles size={13} style={{ flex: 'none', marginTop: 1 }} />
                Inserir da base <b>adota</b> o item no catálogo da empresa (cópia editável) — a base
                oficial permanece intocada, e é o mesmo item que o Suprimentos compra e o Estoque guarda.
              </p>
            </>
          )}
        </>
      )}

      {origem === 'catalogo' && (
        <>
          <div style={{ position: 'relative', marginBottom: 11 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
            <input
              autoFocus
              value={busca}
              onChange={e => setBusca(e.target.value)}
              placeholder="Buscar no catálogo da empresa"
              style={{ ...inp, paddingLeft: 30 }}
            />
          </div>
          <div style={{ maxHeight: 330, overflowY: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)' }}>
            {catalogo.isLoading ? <Loading /> : (catalogo.data ?? []).length === 0 ? (
              <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                Nenhum item no catálogo com esse termo.
              </div>
            ) : catalogo.data?.map(item => {
              const marcado = marcadosCatalogo.has(item.item_id)
              return (
                <div
                  key={item.item_id}
                  className="orc-linha"
                  onClick={() => setMarcadosCatalogo(m => {
                    const p = new Map(m)
                    if (p.has(item.item_id)) p.delete(item.item_id)
                    else p.set(item.item_id, item)
                    return p
                  })}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 11px',
                    borderBottom: '1px solid var(--line-2)', cursor: 'pointer',
                    background: marcado ? 'var(--accent-soft)' : undefined,
                  }}
                >
                  <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />
                  <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 96px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.codigo_interno}
                  </span>
                  <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.descricao}
                  </span>
                  {item.fonte_referencia && <Pill kind="slate">{FONTE_ROTULO[item.fonte_referencia]} {item.codigo_referencia}</Pill>}
                  <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 38px', textAlign: 'center' }}>{item.unidade}</span>
                </div>
              )
            })}
          </div>
        </>
      )}

      {origem === 'novo' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <Field label="Descrição">
                <input autoFocus value={novo.descricao} onChange={e => setNovo(n => ({ ...n, descricao: e.target.value }))} style={inp} />
              </Field>
            </div>
            <Field label="Unidade"><input value={novo.unidade} onChange={e => setNovo(n => ({ ...n, unidade: e.target.value }))} placeholder="m², m³, un, vb" style={inp} /></Field>
            <Field label="Código interno" dica="Em branco, é derivado da descrição.">
              <input value={novo.codigo_interno} onChange={e => setNovo(n => ({ ...n, codigo_interno: e.target.value }))} style={inp} />
            </Field>
            <Field label="Tipo">
              <Select value={novo.tipo} onChange={e => setNovo(n => ({ ...n, tipo: e.target.value }))} style={{ width: '100%', maxWidth: 'none' }}>
                <option value="material">Material</option>
                <option value="servico">Serviço</option>
                <option value="equipamento">Equipamento / Ferramenta</option>
                <option value="composicao">Composição</option>
                <option value="epi">EPI</option>
              </Select>
            </Field>
            <Field label="Categoria"><input value={novo.categoria} onChange={e => setNovo(n => ({ ...n, categoria: e.target.value }))} style={inp} /></Field>
          </div>
          <Aviso>
            <Plus size={15} style={{ flex: 'none', marginTop: 1 }} />
            O item nasce com fonte <b>PRÓPRIA</b> e preço zerado — digite o custo unitário na grade.
            Para virar composição com insumos e coeficientes, use o banco próprio em Bases &amp; bancos.
          </Aviso>
        </>
      )}
    </Modal>
  )
}
