import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Card, Empty, Loading, Num, Pill, SectionHead, type PillKind } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { useContratoObra, useFichaDoContrato } from '../hooks'
import type { EventoDoContrato, LinhaDeContrato } from '../types'

const TOM: Record<string, PillKind> = {
  rascunho: 'info', em_aprovacao: 'accent', aprovada: 'good', aprovado: 'good',
  reprovada: 'danger', reprovado: 'danger', cancelada: 'slate', cancelado: 'slate',
  retificada: 'slate',
}

const reais = (v: string | null | undefined) => formatBRL(apiDecimalToCents(v ?? '0'))

/** **A ficha do contrato** — a primeira parada do caminho, e o contrato inteiro.
 *
 *  *Achado do dono, 11/10/2026:* "deveria poder ver os detalhes do contrato,
 *  não só uma medição" — a parada chamava "Planilha" e só mostrava os itens.
 *  Agora ela é o **Contrato**: o que foi combinado (cadastro), o dinheiro
 *  (contratado → medido → título no ERP → pago), cada item com o medido e o
 *  saldo, a história (medições, inclusive a retificada, aditivos, liberações)
 *  e, embaixo, a planilha para editar enquanto ninguém mediu. Nenhum número é
 *  somado aqui: tudo vem do servidor (`contratos/{id}/ficha/` e o saldo da
 *  carteira). */
export function FichaDoContrato({
  contrato, planilha, aoAbrirMedicao, aoVerAditivos,
}: {
  contrato: LinhaDeContrato
  /** A planilha contratual (cadastro dos itens), montada pela página. */
  planilha: React.ReactNode
  aoAbrirMedicao: (id: number) => void
  aoVerAditivos: () => void
}) {
  const ficha = useFichaDoContrato(contrato.contrato)
  const cadastro = useContratoObra(contrato.contrato)
  const s = contrato.saldo
  const receita = ficha.data?.lado === 'receita'
  const contas = receita ? '/app/erp/contas-a-receber' : '/app/erp/contas-a-pagar'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      {/* --- o dinheiro, do contratado ao pago ----------------------------- */}
      <section>
        <SectionHead sub="do combinado ao que saiu do caixa">O dinheiro do contrato</SectionHead>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
          <Bloco rotulo="Contratado" valor={reais(s.valor_contratado)}
            base={apiDecimalToCents(s.valor_aditivado) !== 0
              ? `original ${reais(s.valor_original)} · aditivos ${reais(s.valor_aditivado)}` : 'sem aditivos'} />
          <Bloco rotulo="Medido aprovado" valor={reais(s.medido_aprovado)}
            base={apiDecimalToCents(s.medido_em_aprovacao) !== 0
              ? `+ ${reais(s.medido_em_aprovacao)} no atesto` : `${s.medicoes} ${s.medicoes === 1 ? 'medição' : 'medições'}`} />
          <Bloco rotulo="Saldo a medir" valor={reais(s.saldo)}
            base={`${s.itens_fechados} de ${s.itens} itens fechados`} />
          <Bloco rotulo="Retenção" valor={reais(s.retencao?.disponivel)}
            base={`retido ${reais(s.retencao?.retido)} · liberado ${reais(s.retencao?.liberado)}`} />
          <Bloco rotulo="Descontos aprovados" valor={reais(s.deducoes_aprovadas)}
            base="multas, impostos, adiantamentos" />
          <Bloco
            rotulo={receita ? 'Faturado no ERP' : 'Títulos no ERP'}
            valor={ficha.data ? reais(ficha.data.financeiro.emitido) : '…'}
            base={ficha.data ? `${ficha.data.financeiro.titulos} ${ficha.data.financeiro.titulos === 1 ? 'título' : 'títulos'}` : ''}
          />
          <Bloco rotulo={receita ? 'Recebido' : 'Pago'}
            valor={ficha.data ? reais(ficha.data.financeiro.pago) : '…'}
            base={ficha.data ? `em aberto ${reais(ficha.data.financeiro.em_aberto)}` : ''}
            destino={contas} />
        </div>
        <p style={{ margin: '8px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          O saldo é consumido pelo <strong>bruto</strong> medido; o título é o <strong>líquido</strong> (depois da
          retenção e dos descontos). Por isso a soma dos títulos não fecha com o valor do contrato.
        </p>
      </section>

      {/* --- o que foi combinado ------------------------------------------- */}
      <section>
        <SectionHead sub="o que foi assinado">Cadastro</SectionHead>
        {cadastro.isLoading ? <Loading o="o cadastro do contrato" /> : cadastro.data ? (
          <Card>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', columnGap: 24 }}>
              <Linha rotulo={receita ? 'Cliente' : 'Empreiteiro'} valor={cadastro.data.fornecedor_nome} />
              <Linha rotulo="Objeto" valor={cadastro.data.objeto} />
              <Linha rotulo="Regime" valor={cadastro.data.regime_rotulo} />
              <Linha rotulo="Situação" valor={<Pill kind={cadastro.data.status === 'rascunho' ? 'slate' : 'good'}>{cadastro.data.status_rotulo}</Pill>} />
              <Linha rotulo="Vigência" valor={`${dateToBR(cadastro.data.data_inicio)}${cadastro.data.data_fim ? ` a ${dateToBR(cadastro.data.data_fim)}` : ' · sem fim'}`} />
              <Linha rotulo="Pagamento" valor={`${cadastro.data.prazo_pagamento_dias} dias após a aprovação`} />
              <Linha rotulo="Retenção" valor={
                Number(cadastro.data.retencao_percentual) > 0
                  ? `${cadastro.data.retencao_percentual.replace('.', ',')}% · ${cadastro.data.retencao_natureza_rotulo}`
                  : 'sem retenção'} />
              {cadastro.data.retencao_condicao_liberacao && (
                <Linha rotulo="Libera quando" valor={cadastro.data.retencao_condicao_liberacao} />
              )}
              <Linha rotulo="Garantia" valor={cadastro.data.garantia_meses ? `${cadastro.data.garantia_meses} meses` : '—'} />
              <Linha rotulo="Reajuste" valor={
                cadastro.data.parcelas_reajuste.length > 0 && cadastro.data.reajuste_data_base
                  ? `${cadastro.data.parcelas_reajuste.map((p) => p.rotulo).join(' + ')} · base ${dateToBR(cadastro.data.reajuste_data_base)} · a cada ${cadastro.data.reajuste_periodicidade_meses} meses`
                  : 'preço fixo'} />
              {cadastro.data.regime === 'administracao' && (
                <Linha rotulo="Taxa de administração" valor={`${(cadastro.data.taxa_administracao ?? '0').replace('.', ',')}%`} />
              )}
              {cadastro.data.regime_publico && (
                <Linha rotulo="Limite de acréscimo" valor={`${(cadastro.data.limite_acrescimo_percentual ?? '25').replace('.', ',')}% (contrato público)`} />
              )}
              {cadastro.data.observacao && <Linha rotulo="Observação" valor={cadastro.data.observacao} />}
            </div>
          </Card>
        ) : <Card><Empty>Não foi possível carregar o cadastro.</Empty></Card>}
      </section>

      {/* --- a história ---------------------------------------------------- */}
      <section>
        <SectionHead sub="medições, aditivos e liberações, em ordem">Linha do tempo</SectionHead>
        {ficha.isLoading ? <Loading o="a história do contrato" /> : (ficha.data?.linha_do_tempo.length ?? 0) === 0 ? (
          <Card><Empty>Nada aconteceu ainda — a primeira medição aparece aqui.</Empty></Card>
        ) : (
          <Card pad={false} style={{ overflow: 'hidden' }}>
            {ficha.data!.linha_do_tempo.map((e) => (
              <Evento
                key={`${e.tipo}-${e.id}`}
                evento={e}
                contas={contas}
                aoAbrir={e.tipo === 'medicao' ? () => aoAbrirMedicao(e.id)
                  : e.tipo === 'aditivo' ? aoVerAditivos : undefined}
              />
            ))}
          </Card>
        )}
      </section>

      {/* --- os itens: contratado, medido, saldo ---------------------------- */}
      <section>
        <SectionHead sub="o acumulado que trava a medição">Itens — medido e saldo</SectionHead>
        {ficha.isLoading ? <Loading o="os itens" /> : (ficha.data?.itens.length ?? 0) === 0 ? (
          <Card><Empty>O contrato ainda não tem itens — cadastre na planilha abaixo.</Empty></Card>
        ) : (
          <Card pad={false} style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760, fontSize: 12.5 }}>
                <thead>
                  <tr>
                    {['Item', 'Descrição', 'Un', 'Contratado', 'Medido', 'Saldo', '%', 'Medido (R$)'].map((r, i) => (
                      <th key={r} style={{
                        textAlign: i < 3 ? 'left' : 'right', padding: '8px 10px', fontSize: 10.5, fontWeight: 700,
                        letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--ink-3)',
                        borderBottom: '1px solid var(--line)', background: 'var(--surface-2)', whiteSpace: 'nowrap',
                      }}>{r}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ficha.data!.itens.map((i) => {
                    const pct = i.percentual != null ? Number(i.percentual) : null
                    return (
                      <tr key={i.item_contrato_id} style={{ borderBottom: '1px solid var(--line-2)' }}>
                        <td style={{ padding: '6px 10px', fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}>{i.codigo}</td>
                        <td style={{ padding: '6px 10px', color: 'var(--ink)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{i.descricao}</td>
                        <td style={{ padding: '6px 10px', color: 'var(--ink-3)' }}>{i.unidade}</td>
                        <td style={{ padding: '6px 10px', textAlign: 'right' }}><Num size={12} tone="var(--ink-2)">{Number(i.contratado).toLocaleString('pt-BR')}</Num></td>
                        <td style={{ padding: '6px 10px', textAlign: 'right' }}><Num size={12} tone="var(--ink)">{Number(i.medido).toLocaleString('pt-BR')}</Num></td>
                        <td style={{ padding: '6px 10px', textAlign: 'right' }}><Num size={12} tone="var(--ink-2)">{Number(i.saldo).toLocaleString('pt-BR')}</Num></td>
                        <td style={{ padding: '6px 10px', textAlign: 'right' }}>
                          <Num size={12} tone={pct != null && pct >= 100 ? 'var(--good-ink)' : 'var(--ink-3)'}>
                            {pct != null ? `${pct.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%` : '—'}
                          </Num>
                        </td>
                        <td style={{ padding: '6px 10px', textAlign: 'right' }}>
                          <Num size={12} tone="var(--ink-2)">{reais(i.valor_medido)}</Num>
                          <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>de {reais(i.valor_contratado)}</div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>

      {/* --- o cadastro dos itens ----------------------------------------- */}
      <section>
        <SectionHead sub={contrato.planilha_editavel ? 'edita-se até a primeira medição' : contrato.planilha_fechada_porque}>
          Planilha contratual
        </SectionHead>
        {planilha}
      </section>
    </div>
  )
}

function Bloco({ rotulo, valor, base, destino }: {
  rotulo: string; valor: string; base?: string; destino?: string
}) {
  return (
    <Card style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--ink-3)' }}>
        {rotulo}
      </span>
      <Num size={17} weight={750} tone="var(--ink)" align="left">{valor}</Num>
      {base && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{base}</span>}
      {destino && (
        <Link to={destino} style={{ fontSize: 11, color: 'var(--brand-app, var(--ink-2))', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
          abrir no ERP <ArrowUpRight size={11} />
        </Link>
      )}
    </Card>
  )
}

function Linha({ rotulo, valor }: { rotulo: string; valor: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--line-2)', fontSize: 12.5 }}>
      <span style={{ width: 130, flex: 'none', color: 'var(--ink-3)' }}>{rotulo}</span>
      <span style={{ color: 'var(--ink)', minWidth: 0 }}>{valor}</span>
    </div>
  )
}

function Evento({ evento: e, contas, aoAbrir }: {
  evento: EventoDoContrato; contas: string; aoAbrir?: () => void
}) {
  const fora = e.status === 'retificada' || e.status === 'cancelada' || e.status === 'reprovada'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
      borderBottom: '1px solid var(--line-2)', opacity: fora ? 0.62 : 1,
    }}>
      <span style={{ width: 78, flex: 'none', fontSize: 11.5, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
        {dateToBR(e.data)}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {aoAbrir ? (
            <button type="button" onClick={aoAbrir} style={{
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              fontSize: 13, fontWeight: 650, color: 'var(--ink)', textDecoration: 'underline',
              textDecorationColor: 'var(--line)', textUnderlineOffset: 3,
            }}>{e.rotulo}</button>
          ) : (
            <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{e.rotulo}</span>
          )}
          <Pill kind={TOM[e.status] ?? 'slate'}>{e.status_rotulo}</Pill>
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
          {e.detalhe}
          {e.titulo && (
            <> · <Link to={contas} style={{ color: 'inherit' }}>
              título {e.titulo.conta_pagar} {e.titulo.status_rotulo.toLowerCase()}
              {apiDecimalToCents(e.titulo.valor_pago) > 0 && ` · ${reais(e.titulo.valor_pago)} pagos`}
            </Link></>
          )}
        </div>
      </div>
      <Num size={13} tone={fora ? 'var(--ink-3)' : 'var(--ink)'}
        style={e.status === 'retificada' ? { textDecoration: 'line-through' } : undefined}>
        {e.tipo === 'aditivo' && apiDecimalToCents(e.liquido) > 0 ? '+ ' : ''}{reais(e.liquido)}
      </Num>
    </div>
  )
}
