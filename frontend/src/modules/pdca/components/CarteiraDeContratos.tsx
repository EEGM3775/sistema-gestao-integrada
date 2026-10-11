import { AlertTriangle, Lock, Plus } from 'lucide-react'
import { Btn, Card, Empty, Num, Pill, SectionHead } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { percentual } from '../formato'
import { SemPermissaoAviso } from './SemPermissaoAviso'
import type { CarteiraDeContratos as Carteira, LinhaDeContrato } from '../types'

/** Quanto do contrato já virou pagamento aprovado.
 *
 *  Feito aqui porque é **razão entre dois números que o servidor mandou**, e
 *  não uma terceira verdade: nenhuma das duas parcelas é recalculada. Com
 *  contratado zero devolve `null` — e a tela escreve "—" em vez de 0%, que
 *  leria como "nada foi medido" num contrato que ainda não tem planilha. */
function medidoSobreContratado(linha: LinhaDeContrato): string | null {
  const contratado = apiDecimalToCents(linha.saldo.valor_contratado)
  if (contratado <= 0) return null
  const aprovado = apiDecimalToCents(linha.saldo.medido_aprovado)
  return percentual((aprovado / contratado) * 100)
}

/** **A leitura de cima do posto**: os contratos da obra com saldo, retenção e
 *  o período que a próxima medição cobriria.
 *
 *  Uma linha por contrato, e clicar entra nele. O saldo vem resolvido do
 *  servidor — somar contratado menos medido no navegador daria uma segunda
 *  verdade, e foi assim que a primeira versão desta tela mostrou "já medido"
 *  negativo para quem entrava pelo link direto. */
export function CarteiraDeContratos({
  carteira, contratoAtual, aoEscolher, aoCriar,
}: {
  carteira: Carteira
  contratoAtual: number | null
  aoEscolher: (contrato: number) => void
  /** Ausente quando a pessoa não pode cadastrar contrato — o botão some em vez
   *  de aparecer e recusar. */
  aoCriar?: () => void
}) {
  if (carteira.sem_permissao.length > 0) {
    return (
      <section>
        <SectionHead>Contratos da obra</SectionHead>
        <SemPermissaoAviso itens={carteira.sem_permissao} />
      </section>
    )
  }

  return (
    <section>
      <SectionHead
        sub={
          carteira.total > 0
            ? `${carteira.total} ${carteira.total === 1 ? 'contrato' : 'contratos'} em vigor nesta obra`
            : undefined
        }
        right={
          aoCriar ? (
            <Btn tam="sm" onClick={aoCriar}>
              <Plus size={13} />
              Novo contrato
            </Btn>
          ) : undefined
        }
      >
        Contratos da obra
      </SectionHead>

      {carteira.linhas.length === 0 ? (
        <Empty>
          <strong style={{ color: 'var(--ink-2)' }}>
            Esta obra ainda não tem contrato de empreitada.
          </strong>
          <br />
          <span style={{ lineHeight: 1.6 }}>
            A medição nasce de um contrato: é ele que diz o que foi combinado,
            por que preço e com que retenção.
          </span>
          {/* Estado vazio que pede uma ação **traz o botão** que leva até ela —
              senão a pessoa sai procurando a porta em outra tela. */}
          {aoCriar && (
            <Btn variant="primary" onClick={aoCriar}>
              <Plus size={14} />
              Cadastrar o primeiro contrato
            </Btn>
          )}
        </Empty>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 880 }}>
              <thead>
                <tr>
                  {[
                    'Contrato', 'Empreiteiro', 'Regime', 'Contratado', 'Aprovado',
                    'Na escada', 'Saldo', 'Retido', 'Próximo período',
                  ].map((coluna, i) => (
                    <th
                      key={coluna}
                      style={{
                        textAlign: i >= 3 && i <= 7 ? 'right' : 'left',
                        padding: '8px 12px', fontSize: 10.5, fontWeight: 700,
                        letterSpacing: '0.07em', textTransform: 'uppercase',
                        color: 'var(--ink-3)', borderBottom: '1px solid var(--line)',
                        background: 'var(--surface-2)', whiteSpace: 'nowrap',
                      }}
                    >
                      {coluna}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {carteira.linhas.map((linha) => (
                  <LinhaDaCarteira
                    key={linha.contrato}
                    linha={linha}
                    atual={linha.contrato === contratoAtual}
                    aoEscolher={aoEscolher}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {carteira.truncada && (
            <div
              style={{
                padding: '9px 12px', fontSize: 11.5, color: 'var(--ink-3)',
                borderTop: '1px solid var(--line-2)', background: 'var(--inset)',
                display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              <AlertTriangle size={13} />
              Mostrando {carteira.linhas.length} dos {carteira.total} contratos
              desta obra — o saldo de cada linha é somado no servidor, e a
              leitura para em {carteira.teto} para a página abrir de imediato.
            </div>
          )}
        </Card>
      )}
    </section>
  )
}

function LinhaDaCarteira({
  linha, atual, aoEscolher,
}: {
  linha: LinhaDeContrato
  atual: boolean
  aoEscolher: (contrato: number) => void
}) {
  const saldo = linha.saldo
  const proporcao = medidoSobreContratado(linha)
  const periodo = saldo.periodo_sugerido

  return (
    <tr
      onClick={() => aoEscolher(linha.contrato)}
      style={{
        cursor: 'pointer',
        background: atual ? 'var(--inset)' : 'transparent',
        borderBottom: '1px solid var(--line-2)',
      }}
    >
      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 12.5, color: 'var(--ink)', fontWeight: 650 }}>
            {linha.numero}
          </span>
          {!linha.planilha_editavel && (
            <span title={linha.planilha_fechada_porque} style={{ display: 'flex', color: 'var(--ink-3)' }}>
              <Lock size={11} />
            </span>
          )}
          {linha.regime_publico && <Pill kind="slate">público</Pill>}
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>
          {linha.status_rotulo}
          {saldo.aditivos_abertos > 0 && (
            <> · {saldo.aditivos_abertos} aditivo(s) sem decisão</>
          )}
        </div>
      </td>

      <td style={{ padding: '10px 12px', fontSize: 12.5, color: 'var(--ink-2)', maxWidth: 220 }}>
        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {linha.fornecedor_nome}
        </div>
        <div
          style={{
            fontSize: 11, color: 'var(--ink-3)', marginTop: 2,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {linha.objeto}
        </div>
        {linha.pedido_scm && (
          <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }} title="Medição × compra de serviço: o pedido do Suprimentos que este contrato mede">
            pedido #{linha.pedido_scm.pedido} no Suprimentos · {formatBRL(apiDecimalToCents(linha.pedido_scm.valor_pedido))}
            {' · '}{linha.pedido_scm.status_rotulo.toLowerCase()}
          </div>
        )}
      </td>

      <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
        {linha.regime_rotulo}
      </td>

      <td style={{ padding: '10px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num size={12.5} tone="var(--ink)">
          {formatBRL(apiDecimalToCents(saldo.valor_contratado))}
        </Num>
        {apiDecimalToCents(saldo.valor_aditivado) !== 0 && (
          <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
            aditivos {formatBRL(apiDecimalToCents(saldo.valor_aditivado))}
          </div>
        )}
      </td>

      <td style={{ padding: '10px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num size={12.5} tone="var(--good-ink)">
          {formatBRL(apiDecimalToCents(saldo.medido_aprovado))}
        </Num>
        {/* Percentual **com a base ao lado** — número sem base é o anti-padrão
            §11 da identidade, e aqui a base é o contratado de hoje. */}
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
          {proporcao ? `${proporcao} do contratado` : 'sem planilha'}
        </div>
        {apiDecimalToCents(saldo.liquido_aprovado) !== apiDecimalToCents(saldo.medido_aprovado) && (
          <div
            style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}
            title="O que se paga: o medido menos retenção e descontos. O saldo do contrato é consumido pelo medido, não pelo líquido."
          >
            líquido a pagar {formatBRL(apiDecimalToCents(saldo.liquido_aprovado))}
          </div>
        )}
      </td>

      <td style={{ padding: '10px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num
          size={12.5}
          tone={
            apiDecimalToCents(saldo.medido_em_aprovacao) > 0
              ? 'var(--accent-ink)' : 'var(--ink-3)'
          }
        >
          {formatBRL(apiDecimalToCents(saldo.medido_em_aprovacao))}
        </Num>
      </td>

      <td style={{ padding: '10px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num size={12.5} tone="var(--ink)">
          {formatBRL(apiDecimalToCents(saldo.saldo))}
        </Num>
      </td>

      <td style={{ padding: '10px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num size={12.5} tone="var(--ink-2)">
          {formatBRL(apiDecimalToCents(saldo.retencao.disponivel))}
        </Num>
        {apiDecimalToCents(saldo.retencao.liberado) > 0 && (
          <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
            {formatBRL(apiDecimalToCents(saldo.retencao.liberado))} devolvidos
          </div>
        )}
      </td>

      {/* **O período que a próxima medição cobriria** — não é cobrança, é
          informação: o sistema não conhece a periodicidade combinada com este
          empreiteiro, então diz de onde a corrente parou e deixa a decisão. */}
      <td style={{ padding: '10px 12px', fontSize: 11.5, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
        {dateToBR(periodo.inicio)} → {dateToBR(periodo.fim)}
        <div style={{ fontSize: 10.5, marginTop: 2 }}>
          {periodo.ultima_medicao
            ? `última: nº ${periodo.ultima_medicao.numero}`
            : 'nenhuma medição ainda'}
        </div>
      </td>
    </tr>
  )
}
