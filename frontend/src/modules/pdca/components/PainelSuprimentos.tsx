import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowUpRight, ChevronDown, ChevronRight, ShoppingCart } from 'lucide-react'
import { Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import { useAntecedencias, useDefinirAntecedencia, useGerarDemandaDoPlano, useNecessidadeDeMaterial } from '../hooks'
import { mensagemDe } from '../montagem'
import { suprimentos, type LinhaDeNecessidade, type ResumoDeInsumo } from '../api/suprimentosApi'

const num = (v: string | number | null | undefined) => Number(v ?? 0)
const qtd = (v: string | number) => num(v).toLocaleString('pt-BR', { maximumFractionDigits: 3 })
const reais = (v: string | number) => num(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const ESTILO_CAMPO = {
  fontSize: 12, padding: '3px 6px', background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', width: 52, textAlign: 'right',
} as const

/** O cronograma **puxa a compra**: cada insumo do orçamento, na data em que a
 *  atividade precisa dele, descontado o que já está no estoque da obra, pedido
 *  ou em demanda. É a mesma fila que o Suprimentos vê por insumo; daqui o
 *  planejador define a antecedência (padrão da obra e exceção por insumo) e
 *  manda o que falta virar demanda. */
export function PainelSuprimentos(
  { cronogramaId, obraId, planoEditavel = false }: { cronogramaId: number; obraId: number; planoEditavel?: boolean },
) {
  const { hasPermission } = useAuth()
  const { data, isLoading, isError } = useNecessidadeDeMaterial(cronogramaId)
  const { data: antecedencias = [] } = useAntecedencias(obraId)
  const definir = useDefinirAntecedencia(obraId)
  const gerar = useGerarDemandaDoPlano(cronogramaId)
  const podePlanejar = hasPermission('pdca.cronograma.edit')
  const podeComprar = hasPermission('scm.demanda.edit')
  const [soFaltas, setSoFaltas] = useState(true)
  const [abertos, setAbertos] = useState<Set<string>>(new Set())
  const [marcados, setMarcados] = useState<Set<string>>(new Set())
  const [aviso, setAviso] = useState<{ tom: 'ok' | 'erro'; texto: string; demandas?: number[] } | null>(null)
  const qc = useQueryClient()
  const religar = useMutation({
    mutationFn: () => suprimentos.religarOrcamento(cronogramaId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pdca'] }),
  })

  const linhasPorInsumo = useMemo(() => {
    const m = new Map<string, LinhaDeNecessidade[]>()
    for (const l of data?.linhas ?? []) m.set(l.insumo, [...(m.get(l.insumo) ?? []), l])
    return m
  }, [data])
  const insumos = useMemo(
    () => (data?.por_insumo ?? []).filter((r) => !soFaltas || num(r.a_comprar) > 0),
    [data, soFaltas],
  )
  const comFalta = (data?.por_insumo ?? []).filter((r) => num(r.a_comprar) > 0)
  const hoje = new Date().toISOString().slice(0, 10)
  const atrasados = comFalta.filter((r) => (r.primeira_falta ?? r.primeiro_pedir_ate) < hoje).length
  const valor = comFalta.reduce((s, r) => s + num(r.valor_a_comprar), 0)
  const padrao = antecedencias.find((a) => a.item == null)
  const excecao = (item: number | null) => (item == null ? undefined : antecedencias.find((a) => a.item === item))

  if (isLoading) return <Loading o="a necessidade de material do plano" />
  if (isError || !data) {
    return <Card><Empty>Não foi possível montar a necessidade de material. Tente de novo.</Empty></Card>
  }

  async function gerarDemanda(lista: string[] | undefined) {
    setAviso(null)
    try {
      const r = await gerar.mutateAsync({ insumos: lista })
      setMarcados(new Set())
      setAviso({
        tom: 'ok',
        texto: `${r.demandas.length === 1 ? 'Demanda criada' : `${r.demandas.length} demandas criadas`} em rascunho no Suprimentos `
          + `(${r.demandas.map((d) => `#${d.demanda} · ${d.itens} ${d.itens === 1 ? 'item' : 'itens'}`).join(', ')}). O comprador cota e publica.`,
        demandas: r.demandas.map((d) => d.demanda),
      })
    } catch (e) {
      setAviso({ tom: 'erro', texto: mensagemDe(e) })
    }
  }

  const cob = data.cobertura

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 1180 }}>
      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
        <strong>O cronograma puxa a compra.</strong> Cada insumo do orçamento entra na data em que a atividade
        precisa dele (início − antecedência), sem o que já foi executado, e abatido pelo que já está no estoque
        da obra, pedido ou em demanda. O que sobra é o que falta comprar — a mesma fila que o Suprimentos vê.
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'stretch' }}>
        <Indicador rotulo="Insumos a comprar" valor={String(comFalta.length)} />
        <Indicador rotulo="Valor a comprar (orçado)" valor={reais(valor)} />
        <Indicador rotulo="Pedido já atrasado" valor={String(atrasados)} tom={atrasados ? 'var(--danger-ink)' : undefined} />
        <Card style={{ flex: '1 1 300px', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
            Antecedência padrão da obra
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--ink-2)' }}>
            O material chega
            <CampoDias
              valor={padrao?.dias ?? null}
              editavel={podePlanejar}
              rotulo="Antecedência padrão (dias)"
              aoGravar={(dias) => definir.mutate({ item: null, dias, existente: padrao })}
            />
            dias antes do início da atividade.
          </span>
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            {padrao ? 'Exceção por insumo na tabela abaixo; por atividade, no Inspetor.' : 'Sem padrão: o material chega no dia do início. Defina o prazo da obra.'}
          </span>
        </Card>
      </div>

      {cob.ligadas_a_versao_anterior > 0 && (
        <div style={{ fontSize: 12, color: 'var(--info-ink)', background: 'var(--info-soft)', padding: '8px 12px', borderRadius: 'var(--r-sm)', lineHeight: 1.5, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ flex: 1, minWidth: 260 }}>
            O orçamento foi revisado: {cob.ligadas_a_versao_anterior} {cob.ligadas_a_versao_anterior === 1 ? 'atividade está ligada' : 'atividades estão ligadas'} a
            um item da versão anterior. A quantidade daqui já usa a revisão vigente (pelo código EAP); religar grava o vínculo e faz o peso do avanço acompanhar.
          </span>
          {planoEditavel && podePlanejar && (
            <Btn
              tam="sm"
              disabled={religar.isPending}
              onClick={async () => {
                try {
                  const r = await religar.mutateAsync()
                  setAviso({ tom: 'ok', texto: `${r.atividades} ${r.atividades === 1 ? 'atividade religada' : 'atividades religadas'} ao orçamento vigente.` })
                } catch (e) { setAviso({ tom: 'erro', texto: mensagemDe(e) }) }
              }}
            >
              Religar ao orçamento vigente
            </Btn>
          )}
        </div>
      )}

      {/* A cobertura dita como número, não como alerta: quantas atividades já
          têm material (do orçamento ou informado na própria atividade). Sem
          orçamento a compra funciona igual — o material vem da atividade. */}
      {cob.folhas > 0 && (
        <div style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          Material conhecido em <strong style={{ color: 'var(--ink-2)' }}>{cob.folhas - cob.folhas_fora_da_conta} de {cob.folhas}</strong> atividades
          {cob.folhas_fora_da_conta > 0 && <> · nas outras, informe o material no Inspetor (bloco Material){cob.tem_orcamento_vigente ? ' ou ligue ao orçamento' : ''}</>}
          .
        </div>
      )}

      {aviso && (
        <div style={{
          fontSize: 12.5, padding: '8px 12px', borderRadius: 'var(--r-sm)',
          background: aviso.tom === 'ok' ? 'var(--good-soft)' : 'var(--danger-soft)',
          color: aviso.tom === 'ok' ? 'var(--good-ink)' : 'var(--danger-ink)',
        }}
        >
          {aviso.texto}{' '}
          {aviso.demandas && <Link to="/app/scm" style={{ color: 'inherit', fontWeight: 650 }}>Abrir no Suprimentos <ArrowUpRight size={12} /></Link>}
        </div>
      )}

      <Card pad={false}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', borderBottom: '1px solid var(--line-2)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>Comprar até</span>
          <label style={{ fontSize: 12, color: 'var(--ink-2)', display: 'inline-flex', gap: 5, alignItems: 'center' }}>
            <input type="checkbox" checked={soFaltas} onChange={(e) => setSoFaltas(e.target.checked)} />
            só o que falta comprar
          </label>
          <span style={{ flex: 1 }} />
          {podeComprar && comFalta.length > 0 && (
            <Btn
              tam="sm"
              variant="primary"
              disabled={gerar.isPending}
              onClick={() => void gerarDemanda(marcados.size ? [...marcados] : undefined)}
              title="Cria a demanda em rascunho no Suprimentos com o que falta comprar"
            >
              <ShoppingCart size={13} />
              {gerar.isPending ? 'Gerando…' : marcados.size ? `Gerar demanda (${marcados.size} insumos)` : 'Gerar demanda de tudo o que falta'}
            </Btn>
          )}
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                {['', 'Insumo', 'Necessário', 'Estoque', 'Pedido', 'Demanda', 'A comprar', 'Pedir até', 'Antec. (d)'].map((h, i) => (
                  <th key={h || i} style={{ textAlign: i >= 2 && i !== 7 ? 'right' : 'left', padding: '7px 10px', fontSize: 10.5, color: 'var(--ink-3)', fontWeight: 700, letterSpacing: '0.04em', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {insumos.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ padding: 18, color: 'var(--ink-3)', textAlign: 'center' }}>
                    {data.linhas.length === 0
                      ? 'Nenhum material calculado: ligue as atividades a itens do orçamento (com composição explodida).'
                      : 'Nada a comprar — estoque, pedidos e demandas da obra cobrem o plano.'}
                  </td>
                </tr>
              )}
              {insumos.map((r) => (
                <LinhaDoInsumo
                  key={r.insumo}
                  r={r}
                  linhas={linhasPorInsumo.get(r.insumo) ?? []}
                  aberto={abertos.has(r.insumo)}
                  aoAlternar={() => setAbertos((s) => { const n = new Set(s); if (n.has(r.insumo)) n.delete(r.insumo); else n.add(r.insumo); return n })}
                  marcado={marcados.has(r.insumo)}
                  podeMarcar={podeComprar && num(r.a_comprar) > 0}
                  aoMarcar={(v) => setMarcados((s) => { const n = new Set(s); if (v) n.add(r.insumo); else n.delete(r.insumo); return n })}
                  hoje={hoje}
                  antecedencia={
                    <CampoDias
                      valor={excecao(r.item)?.dias ?? null}
                      editavel={podePlanejar && r.item != null}
                      placeholder={padrao ? String(padrao.dias) : '0'}
                      rotulo={`Antecedência de ${r.descricao} (dias)`}
                      aoGravar={(dias) => definir.mutate({ item: r.item, dias, existente: excecao(r.item) })}
                    />
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function LinhaDoInsumo(
  { r, linhas, aberto, aoAlternar, marcado, podeMarcar, aoMarcar, hoje, antecedencia }: {
    r: ResumoDeInsumo
    linhas: LinhaDeNecessidade[]
    aberto: boolean
    aoAlternar: () => void
    marcado: boolean
    podeMarcar: boolean
    aoMarcar: (v: boolean) => void
    hoje: string
    antecedencia: React.ReactNode
  },
) {
  const falta = num(r.a_comprar) > 0
  const quando = r.primeira_falta ?? r.primeiro_pedir_ate
  const atrasado = falta && quando < hoje
  const celula = { padding: '7px 10px', borderBottom: '1px solid var(--line-2)', whiteSpace: 'nowrap' as const }
  const numero = { ...celula, textAlign: 'right' as const, fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }
  return (
    <>
      <tr style={{ background: marcado ? 'var(--accent-soft)' : undefined }}>
        <td style={{ ...celula, width: 44 }}>
          <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
            <button type="button" onClick={aoAlternar} aria-label={aberto ? 'Recolher' : 'Ver por atividade'} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', display: 'flex', padding: 0 }}>
              {aberto ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            </button>
            {podeMarcar && <input type="checkbox" checked={marcado} onChange={(e) => aoMarcar(e.target.checked)} aria-label={`Marcar ${r.descricao}`} />}
          </span>
        </td>
        <td style={{ ...celula, whiteSpace: 'normal', minWidth: 200 }}>
          <span style={{ color: 'var(--ink)', fontWeight: 600 }}>{r.descricao}</span>
          <span style={{ color: 'var(--ink-3)', fontSize: 11 }}> · {r.unidade || 'un'} · {r.tipo_demanda === 'servico' ? 'locação' : 'material'} · {r.atividades} {r.atividades === 1 ? 'atividade' : 'atividades'}</span>
          {r.item == null && <span title="Insumo sem item do catálogo: não dá para abater estoque nem pedido" style={{ color: 'var(--accent-ink)', fontSize: 11 }}> · sem item do catálogo</span>}
          {falta && num(r.fora_da_obra) > 0 && (
            <span title="Saldo livre no almoxarifado central ou no canteiro de outra obra — a sobra que pode vir para cá" style={{ display: 'block', color: 'var(--info-ink)', fontSize: 11 }}>
              {qtd(r.fora_da_obra)} {r.unidade} em outro almoxarifado — transfira antes de comprar
            </span>
          )}
        </td>
        <td style={numero}>{qtd(r.necessario)}</td>
        <td style={{ ...numero, color: 'var(--ink-3)' }}>{qtd(r.estoque)}</td>
        <td style={{ ...numero, color: 'var(--ink-3)' }}>{qtd(r.em_pedido)}</td>
        <td style={{ ...numero, color: 'var(--ink-3)' }}>{qtd(r.em_demanda)}</td>
        <td style={{ ...numero, fontWeight: 700, color: falta ? 'var(--ink)' : 'var(--good-ink)' }}>{falta ? qtd(r.a_comprar) : 'coberto'}</td>
        <td style={celula}>
          {falta ? (
            <span style={{ fontFamily: 'var(--mono)', color: atrasado ? 'var(--danger-ink)' : 'var(--ink-2)' }}>
              {dateToBR(quando)}{atrasado && <Pill kind="danger">atrasado</Pill>}
            </span>
          ) : <span style={{ color: 'var(--ink-3)' }}>—</span>}
        </td>
        <td style={{ ...celula, textAlign: 'right' }}>{antecedencia}</td>
      </tr>
      {aberto && linhas.map((l, i) => (
        <tr key={`${l.atividade}-${i}`} style={{ background: 'var(--inset)' }}>
          <td style={celula} />
          <td style={{ ...celula, whiteSpace: 'normal', fontSize: 12 }}>
            <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{l.atividade_codigo}</span> {l.atividade_nome}
            {l.origem === 'etapa' && <span title="Item do orçamento da etapa que nenhuma atividade cita" style={{ color: 'var(--ink-3)', fontSize: 11 }}> · pela etapa</span>}
            {num(l.executado_pct) > 0 && <span style={{ color: 'var(--ink-3)', fontSize: 11 }}> · {qtd(l.executado_pct)}% executado</span>}
          </td>
          <td style={{ ...numero, fontSize: 12 }}>{qtd(l.restante)}</td>
          <td colSpan={3} style={{ ...celula, fontSize: 11, color: 'var(--ink-3)' }}>
            {[num(l.coberto_estoque) && `${qtd(l.coberto_estoque)} do estoque`, num(l.coberto_pedido) && `${qtd(l.coberto_pedido)} já pedido`, num(l.coberto_demanda) && `${qtd(l.coberto_demanda)} em demanda`].filter(Boolean).join(' · ')}
          </td>
          <td style={{ ...numero, fontSize: 12 }}>{num(l.a_comprar) > 0 ? qtd(l.a_comprar) : '—'}</td>
          <td style={{ ...celula, fontSize: 11.5, fontFamily: 'var(--mono)', color: l.situacao === 'atrasada' ? 'var(--danger-ink)' : 'var(--ink-2)' }}>
            chegar {dateToBR(l.chegar_ate)}
            {l.prazo_fornecedor_dias ? <span style={{ color: 'var(--ink-3)' }}> · pedir {dateToBR(l.pedir_ate)}</span> : null}
          </td>
          <td style={{ ...celula, textAlign: 'right', fontSize: 11, color: 'var(--ink-3)' }} title={`Antecedência vem: ${l.antecedencia_origem}`}>
            {l.antecedencia_dias} d · {({ atividade: 'da atividade', insumo: 'do insumo', obra: 'da obra', nenhuma: 'sem prazo' } as const)[l.antecedencia_origem]}
          </td>
        </tr>
      ))}
    </>
  )
}

function Indicador({ rotulo, valor, tom }: { rotulo: string; valor: string; tom?: string }) {
  return (
    <Card style={{ flex: '0 1 170px', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>{rotulo}</span>
      <span style={{ fontSize: 19, fontWeight: 750, color: tom ?? 'var(--ink)', fontFamily: 'var(--mono)' }}>{valor}</span>
    </Card>
  )
}

/** Número de dias que grava ao sair; vazio apaga (volta a valer o padrão). */
function CampoDias(
  { valor, editavel, aoGravar, rotulo, placeholder }: {
    valor: number | null; editavel: boolean; aoGravar: (dias: number | null) => void; rotulo: string; placeholder?: string
  },
) {
  const [rascunho, setRascunho] = useState(valor == null ? '' : String(valor))
  useEffect(() => { setRascunho(valor == null ? '' : String(valor)) }, [valor])
  if (!editavel) return <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>{valor ?? (placeholder ? `(${placeholder})` : '—')}</span>
  return (
    <input
      aria-label={rotulo}
      inputMode="numeric"
      value={rascunho}
      placeholder={placeholder}
      onChange={(e) => setRascunho(e.target.value.replace(/\D/g, ''))}
      onBlur={() => {
        const novo = rascunho === '' ? null : Number(rascunho)
        if (novo !== valor) aoGravar(novo)
      }}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
      style={ESTILO_CAMPO}
    />
  )
}
