import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Check, Minus, Plus, X } from 'lucide-react'
import { Btn, CampoMoeda, Card, Modal, Num, Pill, SectionHead } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { percentual } from '../formato'
import type {
  DeducaoMedicao, EscadaDoDocumento, Medicao, StatusMedicao, TipoDeducao,
  TotaisDaMedicao,
} from '../types'

const TOM_DO_STATUS: Record<StatusMedicao, 'good' | 'accent' | 'info' | 'danger' | 'slate'> = {
  rascunho: 'info',
  em_aprovacao: 'accent',
  aprovada: 'good',
  reprovada: 'danger',
  cancelada: 'slate',
  retificada: 'slate',
}

/** Os mesmos tipos do servidor (`TipoDeducao`). A tela tinha `imposto` e
 *  `outro`, que o servidor não conhece — todo desconto lançado voltava
 *  recusado, e a recusa aparecia como "[object Object]" (achado do dono,
 *  10/10/2026). O tipo é o que o financeiro concilia com a guia, por isso
 *  INSS, ISS e IRRF são separados. */
const TIPOS_DE_DEDUCAO: { valor: TipoDeducao; rotulo: string }[] = [
  { valor: 'inss', rotulo: 'Retenção de INSS' },
  { valor: 'iss', rotulo: 'Retenção de ISS' },
  { valor: 'irrf', rotulo: 'Retenção de IRRF' },
  { valor: 'adiantamento', rotulo: 'Amortização de adiantamento' },
  { valor: 'multa', rotulo: 'Multa contratual' },
  { valor: 'material', rotulo: 'Material fornecido pela obra' },
  { valor: 'outros', rotulo: 'Outro desconto' },
]

/** **O boletim** — cabeçalho, o dinheiro somado e a escada de quem assina.
 *
 *  Os verbos moram aqui, ao lado da grade, e não numa tela de aprovação à
 *  parte: quem ateste está olhando a medição, e separar a decisão da evidência
 *  é o oposto do que a escada existe para garantir. */
export function BoletimDeMedicao({
  medicao, obraId, podeApurar, podeAtestar, ocupado, erro, gravacaoPendente,
  aoSubmeter, aoAtestar, aoCancelar, aoRetificar, aoSalvarDeducoes,
}: {
  medicao: Medicao
  obraId: number
  podeApurar: boolean
  podeAtestar: boolean
  ocupado?: boolean
  erro?: string | null
  /** **O que a grade ainda não gravou**, para o envio não sair na frente dela.
   *  Submeter manda só o id: o servidor valida e congela o que está *gravado*,
   *  não o que está na tela (D137). */
  gravacaoPendente?: boolean
  aoSubmeter: (observacao: string) => void
  aoAtestar: (aprovar: boolean, observacao: string) => void
  aoCancelar: (motivo: string) => void
  aoRetificar: (motivo: string) => void
  aoSalvarDeducoes: (deducoes: LinhaDeDeducao[]) => void
}) {
  const [dialogo, setDialogo] = useState<
    'submeter' | 'aprovar' | 'reprovar' | 'cancelar' | 'retificar' | null
  >(null)
  const totais = medicao.totais
  const rascunho = medicao.status === 'rascunho'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Cabecalho medicao={medicao} />

      {erro && (
        <div
          style={{
            padding: '9px 12px', borderRadius: 'var(--r-sm)',
            background: 'var(--danger-soft)', color: 'var(--danger-ink)',
            fontSize: 12.5, lineHeight: 1.5,
          }}
        >
          {erro}
        </div>
      )}

      <OsNumeros totais={totais} receita={medicao.lado === 'receita'} />

      {totais.original && (
        <Conciliacao totais={totais} receita={medicao.lado === 'receita'} status={medicao.status} />
      )}

      <Deducoes
        deducoes={medicao.deducoes ?? []}
        totais={totais}
        editavel={rascunho && podeApurar}
        aoSalvar={aoSalvarDeducoes}
      />

      <Escada escada={medicao.escada} status={medicao.status} />

      {medicao.titulo_erp && (
        <TituloNoErp titulo={medicao.titulo_erp} obraId={obraId} />
      )}

      <Verbos
        medicao={medicao}
        podeApurar={podeApurar}
        podeAtestar={podeAtestar}
        ocupado={ocupado}
        gravacaoPendente={gravacaoPendente}
        aoAbrirDialogo={setDialogo}
      />

      {dialogo && (
        <DialogoDoVerbo
          qual={dialogo}
          medicao={medicao}
          ocupado={ocupado}
          aoFechar={() => setDialogo(null)}
          aoConfirmar={(texto) => {
            if (dialogo === 'submeter') aoSubmeter(texto)
            if (dialogo === 'aprovar') aoAtestar(true, texto)
            if (dialogo === 'reprovar') aoAtestar(false, texto)
            if (dialogo === 'cancelar') aoCancelar(texto)
            if (dialogo === 'retificar') aoRetificar(texto)
            setDialogo(null)
          }}
        />
      )}
    </div>
  )
}

function Cabecalho({ medicao }: { medicao: Medicao }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 16, fontWeight: 750, color: 'var(--ink)' }}>
        Boletim {medicao.numero}
      </span>
      <Pill kind={TOM_DO_STATUS[medicao.status]}>{medicao.status_rotulo}</Pill>
      <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
        de {dateToBR(medicao.periodo_inicio)} a {dateToBR(medicao.periodo_fim)}
      </span>
      {medicao.retifica != null && (
        <Pill kind="info" title="Este boletim corrige outro já aprovado">
          retificadora
        </Pill>
      )}
      {medicao.apurada_por && (
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          apurado por {medicao.apurada_por}
        </span>
      )}
    </div>
  )
}

/** Bruto → retenção → deduções → líquido, **na ordem em que o dinheiro
 *  encolhe**. É o líquido que vira título no ERP, e por isso ele é o único
 *  destacado: os outros três existem para explicá-lo. Na retificadora são os
 *  números da medição corrigida **inteira** — a comparação mora na
 *  `Conciliacao`. */
function OsNumeros({ totais, receita }: { totais: TotaisDaMedicao; receita: boolean }) {
  const linhas: { rotulo: string; valor: string; base?: string; sinal?: '-' }[] = [
    { rotulo: 'Serviço executado', valor: totais.executado },
    { rotulo: 'Material posto na obra', valor: totais.material_estocado },
    { rotulo: 'Bruto do período', valor: totais.bruto },
    ...(apiDecimalToCents(totais.reajuste) !== 0 ? [{
      rotulo: totais.reajuste_provisorio ? 'Reajuste (índice provisório)' : 'Reajuste do contrato',
      valor: totais.reajuste,
    }] : []),
    {
      rotulo: 'Retenção contratual',
      valor: totais.retencao,
      base: percentual(totais.retencao_percentual) ?? undefined,
      sinal: '-',
    },
    { rotulo: 'Descontos', valor: totais.total_deducoes, sinal: '-' },
  ]

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 7 }}>
        {linhas.map((linha) => (
          <div
            key={linha.rotulo}
            style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 12.5 }}
          >
            <span style={{ color: 'var(--ink-3)', flex: 1 }}>
              {linha.rotulo}
              {linha.base && <span style={{ marginLeft: 6 }}>({linha.base})</span>}
            </span>
            <Num size={12.5} tone={linha.sinal ? 'var(--ink-3)' : 'var(--ink-2)'}>
              {linha.sinal === '-' && apiDecimalToCents(linha.valor) > 0 ? '− ' : ''}
              {formatBRL(apiDecimalToCents(linha.valor))}
            </Num>
          </div>
        ))}
      </div>

      <div
        style={{
          display: 'flex', alignItems: 'baseline', gap: 10,
          padding: '12px 14px', borderTop: '1px solid var(--line)',
          background: 'var(--inset)',
        }}
      >
        <span style={{ flex: 1, fontSize: 12.5, fontWeight: 700, color: 'var(--ink)' }}>
          {receita ? 'Líquido a receber' : 'Líquido a pagar'}
          {totais.original && ' (medição corrigida)'}
        </span>
        <Num size={18} weight={750} tone="var(--ink)">
          {formatBRL(apiDecimalToCents(totais.liquido))}
        </Num>
      </div>
    </Card>
  )
}

/** **A conciliação da retificadora** — original | corrigida | diferença, e o
 *  que cada número faz no contrato e no financeiro *(achado do dono,
 *  11/10/2026: "ia ter R$ 600 a menos e o contrato não ia fechar", sem a tela
 *  dizer por quê)*. A tela não soma nada além da subtração das colunas: os
 *  três números de cada linha vêm do servidor. */
function Conciliacao({ totais, receita, status }: {
  totais: TotaisDaMedicao
  receita: boolean
  status: Medicao['status']
}) {
  const original = totais.original!
  const c = apiDecimalToCents
  const linhas = [
    { rotulo: 'Bruto (com reajuste)', antes: c(original.bruto_reajustado), depois: c(totais.bruto_reajustado) },
    { rotulo: 'Retenção', antes: -c(original.retencao), depois: -c(totais.retencao) },
    { rotulo: 'Descontos', antes: -c(original.total_deducoes), depois: -c(totais.total_deducoes) },
    { rotulo: 'Líquido', antes: c(original.liquido), depois: c(totais.liquido), forte: true },
  ]
  const difBruto = c(totais.bruto_reajustado) - c(original.bruto_reajustado)
  const difLiquido = c(totais.liquido) - c(original.liquido)
  const difDescontos = c(totais.total_deducoes) - c(original.total_deducoes)
  const pagar = receita ? 'receber' : 'pagar'
  const sinal = (v: number) => (v === 0 ? '—' : `${v > 0 ? '+' : '−'} ${formatBRL(Math.abs(v))}`)

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px 4px', fontSize: 12.5, fontWeight: 700, color: 'var(--ink)' }}>
        Conciliação com a medição {original.numero}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr>
              {['', `Medição ${original.numero}`, 'Corrigida', 'Diferença'].map((r, i) => (
                <th
                  key={r || 'rotulo'}
                  style={{
                    textAlign: i === 0 ? 'left' : 'right', padding: '6px 14px',
                    fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em',
                    textTransform: 'uppercase', color: 'var(--ink-3)',
                    borderBottom: '1px solid var(--line)',
                  }}
                >
                  {r}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={l.rotulo} style={{ borderBottom: '1px solid var(--line-2)' }}>
                <td style={{ padding: '6px 14px', color: l.forte ? 'var(--ink)' : 'var(--ink-3)', fontWeight: l.forte ? 700 : 400 }}>
                  {l.rotulo}
                </td>
                <td style={{ padding: '6px 14px', textAlign: 'right' }}>
                  <Num size={12.5} tone="var(--ink-3)">{formatBRL(l.antes)}</Num>
                </td>
                <td style={{ padding: '6px 14px', textAlign: 'right' }}>
                  <Num size={12.5} tone="var(--ink)" weight={l.forte ? 750 : undefined}>{formatBRL(l.depois)}</Num>
                </td>
                <td style={{ padding: '6px 14px', textAlign: 'right' }}>
                  <Num
                    size={12.5}
                    tone={l.depois - l.antes === 0 ? 'var(--ink-3)'
                      : l.depois - l.antes < 0 ? 'var(--danger-ink)' : 'var(--good-ink)'}
                  >
                    {sinal(l.depois - l.antes)}
                  </Num>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        style={{
          padding: '10px 14px', borderTop: '1px solid var(--line)', background: 'var(--inset)',
          fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.55,
          display: 'flex', flexDirection: 'column', gap: 5,
        }}
      >
        <div>
          <strong>No contrato:</strong>{' '}
          {difBruto === 0
            ? 'o medido não muda — o saldo a medir continua o mesmo.'
            : difBruto < 0
              ? `voltam ${formatBRL(-difBruto)} ao saldo a medir do contrato.`
              : `o contrato consome mais ${formatBRL(difBruto)} do saldo.`}
          {difDescontos !== 0 && (
            <> {' '}Os descontos ({sinal(-difDescontos)} no líquido) <strong>não</strong> mexem
              no saldo: o contrato é consumido pelo bruto medido, por isso a soma dos líquidos
              não fecha com o valor do contrato.</>
          )}
        </div>
        <div>
          <strong>No financeiro, ao aprovar:</strong>{' '}
          a medição {original.numero} vira <em>retificada</em> e sai de toda soma.
          {' '}Se o título dela ainda está em aberto, ele é cancelado e nasce um de{' '}
          {formatBRL(c(totais.liquido))} a {pagar}.
          {' '}Se já foi {receita ? 'recebido' : 'pago'},{' '}
          {difLiquido > 0
            ? `nasce o complemento de ${formatBRL(difLiquido)} a ${pagar}`
            : difLiquido < 0
              ? `o saldo em aberto do título cai primeiro e o que sobrar (até ${formatBRL(-difLiquido)}) vira devolução`
              : 'o título já confere'}
          {' '}— e o ERP recebe um aviso <strong>Agir já</strong>.
        </div>
        {status !== 'aprovada' && (
          <div style={{ color: 'var(--ink-3)' }}>
            Até a aprovação, a medição {original.numero} continua valendo. Cancelar esta
            retificadora a apaga de vez.
          </div>
        )}
      </div>
    </Card>
  )
}

export interface LinhaDeDeducao {
  tipo: TipoDeducao
  descricao: string
  /** Centavos, como manda a convenção do dinheiro. Vira decimal na borda. */
  centavos: number
}

/** Os descontos que **não voltam** — imposto retido, amortização, multa.
 *
 *  A retenção contratual não entra aqui, e a tela diz por quê: ela é cláusula
 *  do contrato e volta ao empreiteiro pela liberação de caução. Misturar as
 *  duas faria o gestor descontar duas vezes. */
function Deducoes({
  deducoes, totais, editavel, aoSalvar,
}: {
  deducoes: DeducaoMedicao[]
  totais: TotaisDaMedicao
  editavel: boolean
  aoSalvar: (linhas: LinhaDeDeducao[]) => void
}) {
  const [editando, setEditando] = useState(false)
  const [linhas, setLinhas] = useState<LinhaDeDeducao[]>([])

  function abrir() {
    // "Lançar desconto" abre já com uma linha: abrir vazio pedia um segundo
    // clique em "Outra linha" antes de poder digitar qualquer coisa.
    setLinhas(
      deducoes.length > 0
        ? deducoes.map((d) => ({
          tipo: d.tipo,
          descricao: d.descricao,
          centavos: apiDecimalToCents(d.valor_aplicado),
        }))
        : [{ tipo: 'inss', descricao: '', centavos: 0 }],
    )
    setEditando(true)
  }

  return (
    <section>
      <SectionHead
        right={
          editavel && !editando ? (
            <Btn tam="sm" onClick={abrir}>
              {deducoes.length > 0 ? 'Mudar os descontos' : 'Lançar desconto'}
            </Btn>
          ) : undefined
        }
        sub="Imposto retido, amortização de adiantamento, multa — o que sai do pagamento e não volta."
      >
        Descontos deste boletim
      </SectionHead>

      {editando ? (
        <Card>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {linhas.map((linha, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <select
                  value={linha.tipo}
                  onChange={(e) => {
                    const tipo = e.target.value as TipoDeducao
                    setLinhas((atual) =>
                      atual.map((l, j) => (j === i ? { ...l, tipo } : l)))
                  }}
                  style={{
                    padding: '7px 9px', borderRadius: 8, fontSize: 12.5,
                    border: '1px solid var(--line)', background: 'var(--surface)',
                    color: 'var(--ink)',
                  }}
                >
                  {TIPOS_DE_DEDUCAO.map((t) => (
                    <option key={t.valor} value={t.valor}>{t.rotulo}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={linha.descricao}
                  placeholder="O que é este desconto"
                  onChange={(e) => {
                    const descricao = e.target.value
                    setLinhas((atual) =>
                      atual.map((l, j) => (j === i ? { ...l, descricao } : l)))
                  }}
                  style={{
                    flex: 1, padding: '7px 10px', borderRadius: 8, fontSize: 12.5,
                    border: '1px solid var(--line)', background: 'var(--surface)',
                    color: 'var(--ink)',
                  }}
                />
                <div style={{ width: 150 }}>
                  <CampoMoeda
                    centavos={linha.centavos}
                    aoMudar={(centavos) =>
                      setLinhas((atual) =>
                        atual.map((l, j) => (j === i ? { ...l, centavos } : l)))}
                    aria-label="Valor do desconto"
                  />
                </div>
                <button
                  type="button"
                  aria-label="Tirar este desconto"
                  onClick={() => setLinhas((atual) => atual.filter((_, j) => j !== i))}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--ink-3)', display: 'flex', padding: 4,
                  }}
                >
                  <Minus size={15} />
                </button>
              </div>
            ))}

            <div style={{ display: 'flex', gap: 8 }}>
              <Btn
                tam="sm"
                onClick={() =>
                  setLinhas((atual) => [
                    ...atual, { tipo: 'inss', descricao: '', centavos: 0 },
                  ])}
              >
                <Plus size={13} />
                Outra linha
              </Btn>
              <span style={{ flex: 1 }} />
              <Btn tam="sm" onClick={() => setEditando(false)}>Deixar como está</Btn>
              <Btn
                tam="sm"
                variant="primary"
                onClick={() => {
                  aoSalvar(linhas)
                  setEditando(false)
                }}
              >
                Gravar os descontos
              </Btn>
            </div>
          </div>
        </Card>
      ) : totais.deducoes.length === 0 ? (
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
          Nenhum desconto neste boletim.
        </p>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {totais.deducoes.map((d) => (
            <div
              key={d.deducao_id}
              style={{
                display: 'flex', alignItems: 'baseline', gap: 10,
                padding: '9px 14px', borderBottom: '1px solid var(--line-2)',
                fontSize: 12.5,
              }}
            >
              <Pill kind="slate">{d.tipo_rotulo}</Pill>
              <span style={{ flex: 1, color: 'var(--ink-2)', minWidth: 0 }}>
                {d.descricao || '—'}
                {d.percentual != null && (
                  <span style={{ color: 'var(--ink-3)' }}>
                    {' '}({percentual(d.percentual)}
                    {d.base_calculo != null
                      ? ` de ${formatBRL(apiDecimalToCents(d.base_calculo))}`
                      : ' do bruto'})
                  </span>
                )}
              </span>
              <Num size={12.5} tone="var(--ink-3)">
                − {formatBRL(apiDecimalToCents(d.valor))}
              </Num>
            </div>
          ))}
        </Card>
      )}
    </section>
  )
}

/** Quem assinou, quando e **com que autoridade** — e em que degrau parou.
 *
 *  É a pergunta que a tela não sabia responder: "quem autorizou este pagamento
 *  e com que permissão". Sem o degrau, "em aprovação" não diz de quem se
 *  espera a decisão. */
function Escada({
  escada, status,
}: { escada: EscadaDoDocumento | null; status: StatusMedicao }) {
  if (!escada) {
    return status === 'rascunho' ? null : (
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
        Este boletim não passou por escada de aprovação — esta empresa ainda não
        montou uma para medição, então submeter aprova em um passo.
      </p>
    )
  }

  return (
    <section>
      <SectionHead
        sub={
          escada.nivel
            ? `Parado em ${escada.nivel}${escada.permissao_exigida ? ` · exige ${escada.permissao_exigida}` : ''}`
            : undefined
        }
      >
        Quem assinou
      </SectionHead>

      {escada.atestos.length === 0 ? (
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
          Enviado por {escada.solicitante}. Nenhuma assinatura ainda.
        </p>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {escada.atestos.map((atesto) => (
            <div
              key={atesto.atesto_id}
              style={{
                display: 'flex', alignItems: 'baseline', gap: 10,
                padding: '9px 14px', borderBottom: '1px solid var(--line-2)',
                fontSize: 12.5,
              }}
            >
              <Pill kind={atesto.decisao === 'aprovado' ? 'good' : 'danger'}>
                {atesto.decisao === 'aprovado' ? <Check size={11} /> : <X size={11} />}
                {atesto.nivel_nome}
              </Pill>
              <span style={{ flex: 1, color: 'var(--ink-2)', minWidth: 0 }}>
                {atesto.autor}
                {atesto.observacao && (
                  <span style={{ color: 'var(--ink-3)' }}> — {atesto.observacao}</span>
                )}
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                {dateToBR(atesto.decidido_em.slice(0, 10))}
              </span>
            </div>
          ))}
        </Card>
      )}
    </section>
  )
}

/** O título no ERP — a integração visível, e clicável.
 *
 *  Existe para o botão de cancelar saber o que vai acontecer **antes** de
 *  alguém clicar: com o título aberto, cancelar derruba os dois; com baixa em
 *  cima, só a retificadora conserta. */
function TituloNoErp({
  titulo, obraId,
}: { titulo: NonNullable<Medicao['titulo_erp']>; obraId: number }) {
  void obraId
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--ink-3)', fontWeight: 700,
          }}
        >
          No financeiro
        </span>
        <Pill kind={titulo.pode_cancelar ? 'info' : 'good'}>{titulo.status_rotulo}</Pill>
        <Num size={13} tone="var(--ink)">{formatBRL(apiDecimalToCents(titulo.valor))}</Num>
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          vence em {dateToBR(titulo.data_vencimento)}
          {apiDecimalToCents(titulo.valor_pago) > 0 && (
            <> · {formatBRL(apiDecimalToCents(titulo.valor_pago))} já pagos</>
          )}
        </span>
        <span style={{ flex: 1 }} />
        <Link
          to={titulo.lado === 'receita' ? '/app/erp/contas-a-receber' : '/app/erp/contas-a-pagar'}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 12, color: 'var(--brand)', textDecoration: 'none',
          }}
        >
          Abrir o título
          <ArrowUpRight size={13} />
        </Link>
      </div>
    </Card>
  )
}

/** Os verbos, **e só os que a pessoa pode usar naquele estado**.
 *
 *  A permissão e o estado decidem juntos: cancelar um rascunho é de quem
 *  apura; cancelar uma aprovada derruba um título a pagar e é de quem ateste.
 *  A tela não reimplementa essa régua — ela oferece o que o servidor aceitaria
 *  e deixa a recusa acontecer com frase quando o caso for de escada. */
function Verbos({
  medicao, podeApurar, podeAtestar, ocupado, gravacaoPendente, aoAbrirDialogo,
}: {
  medicao: Medicao
  podeApurar: boolean
  podeAtestar: boolean
  ocupado?: boolean
  gravacaoPendente?: boolean
  aoAbrirDialogo: (
    qual: 'submeter' | 'aprovar' | 'reprovar' | 'cancelar' | 'retificar',
  ) => void
}) {
  const { status } = medicao
  const botoes: React.ReactNode[] = []

  if (status === 'rascunho' && podeApurar) {
    botoes.push(
      <Btn key="submeter" tam="sm" variant="primary" disabled={ocupado}
        onClick={() => aoAbrirDialogo('submeter')}>
        Enviar para atesto
      </Btn>,
    )
  }
  if (status === 'rascunho' && podeApurar && gravacaoPendente) {
    botoes.push(
      <span
        key="pendente"
        style={{
          alignSelf: 'center', fontSize: 11.5, color: 'var(--ink-3)',
        }}
      >
        Há digitação ainda não gravada — o envio grava antes de enviar.
      </span>,
    )
  }
  if (status === 'em_aprovacao' && podeAtestar) {
    botoes.push(
      <Btn key="aprovar" tam="sm" variant="primary" disabled={ocupado}
        onClick={() => aoAbrirDialogo('aprovar')}>
        <Check size={13} />
        Atestar
      </Btn>,
      <Btn key="reprovar" tam="sm" disabled={ocupado}
        onClick={() => aoAbrirDialogo('reprovar')}>
        <X size={13} />
        Devolver
      </Btn>,
    )
  }
  if (status === 'aprovada' && podeApurar) {
    botoes.push(
      <Btn key="retificar" tam="sm" disabled={ocupado}
        onClick={() => aoAbrirDialogo('retificar')}>
        Abrir retificadora
      </Btn>,
    )
  }
  if (
    (status === 'rascunho' || status === 'em_aprovacao') && podeApurar
    // A retificadora aprovada já mexeu no financeiro: corrige-se retificando
    // de novo, não retirando (o servidor recusa).
    || (status === 'aprovada' && podeAtestar && medicao.retifica == null)
  ) {
    botoes.push(
      <Btn key="cancelar" tam="sm" disabled={ocupado}
        onClick={() => aoAbrirDialogo('cancelar')}>
        Retirar boletim
      </Btn>,
    )
  }

  if (botoes.length === 0) {
    return (
      <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)' }}>
        Não há nada a decidir aqui com as suas permissões. Quem apura precisa de
        “pdca.medicao.apurar”; quem ateste, de “pdca.medicao.atestar”.
      </p>
    )
  }

  return <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{botoes}</div>
}

/** O diálogo de cada verbo — **e cada um diz o que vai acontecer**.
 *
 *  Devolver exige motivo (quem montou o documento precisa saber o que
 *  corrigir), retificar exige motivo (é ele que separa a correção do erro) e
 *  retirar diz, antes do clique, se o título do financeiro cai junto. */
function DialogoDoVerbo({
  qual, medicao, ocupado, aoFechar, aoConfirmar,
}: {
  qual: 'submeter' | 'aprovar' | 'reprovar' | 'cancelar' | 'retificar'
  medicao: Medicao
  ocupado?: boolean
  aoFechar: () => void
  aoConfirmar: (texto: string) => void
}) {
  const [texto, setTexto] = useState('')
  const liquido = formatBRL(apiDecimalToCents(medicao.totais.liquido))
  const titulo = medicao.titulo_erp

  const config = {
    submeter: {
      titulo: 'Enviar o boletim para atesto',
      explica:
        `Depois de enviado, a grade fecha para edição. O líquido de ${liquido} `
        + 'é o que vai para quem ateste.',
      rotulo: 'Recado para quem vai atestar (opcional)',
      exige: false,
      acao: 'Enviar',
    },
    aprovar: {
      titulo: 'Atestar o boletim',
      explica:
        `Atestar declara que o serviço foi executado como está na grade. `
        + `Aprovado o último degrau, sai um título de ${liquido} no financeiro.`,
      rotulo: 'Observação da assinatura (opcional)',
      exige: false,
      acao: 'Atestar',
    },
    reprovar: {
      titulo: 'Devolver o boletim',
      explica:
        'O boletim volta para quem o montou. Informe o que está errado.',
      rotulo: 'O que precisa ser corrigido',
      exige: true,
      acao: 'Devolver',
    },
    cancelar: medicao.retifica != null ? {
      titulo: 'Descartar a retificadora',
      explica:
        'A retificadora ainda não valeu: ela é apagada de vez e a medição que ela '
        + 'corrigiria continua como está. Depois, se quiser, abra outra.',
      rotulo: 'Motivo (opcional)',
      exige: false,
      acao: 'Descartar',
    } : {
      titulo: 'Retirar o boletim',
      explica: titulo
        ? titulo.pode_cancelar
          ? `Este boletim gerou um título de ${formatBRL(apiDecimalToCents(titulo.valor))} `
            + 'no financeiro, e ele será cancelado junto.'
          : `O título deste boletim já teve baixa de `
            + `${formatBRL(apiDecimalToCents(titulo.valor_pago))} — retirar o `
            + 'boletim não desfaz o pagamento. O caminho para corrigir é a '
            + 'retificadora.'
        : 'O boletim sai sem julgamento de mérito e o número dele não se '
          + 'reaproveita.',
      rotulo: 'Motivo da retirada',
      exige: true,
      acao: 'Retirar',
    },
    retificar: {
      titulo: 'Abrir a medição que corrige esta',
      explica:
        'A retificadora abre no mesmo período como cópia desta — linhas, material '
        + 'e descontos. Você escreve os valores certos; aprovada, ela substitui esta '
        + '(que fica como "retificada", só para leitura) e o financeiro é acertado.',
      rotulo: 'O que estava errado',
      exige: true,
      acao: 'Abrir retificadora',
    },
  }[qual]

  const faltaTexto = config.exige && !texto.trim()

  return (
    <Modal
      titulo={config.titulo}
      onClose={aoFechar}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={faltaTexto || ocupado}
            onClick={() => aoConfirmar(texto.trim())}
          >
            {ocupado ? 'Enviando…' : config.acao}
          </Btn>
        </div>
      }
    >
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
        {config.explica}
      </p>
      <label
        style={{
          display: 'block', fontSize: 11, letterSpacing: '0.06em',
          textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
          marginBottom: 6,
        }}
      >
        {config.rotulo}
      </label>
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        rows={3}
        autoFocus
        style={{
          width: '100%', padding: '8px 10px', borderRadius: 8,
          border: '1px solid var(--line)', background: 'var(--surface)',
          color: 'var(--ink)', fontSize: 13, resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
    </Modal>
  )
}
