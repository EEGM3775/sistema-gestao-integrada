import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Link2Off, PlusSquare, Sigma, Sparkles, StickyNote,
} from 'lucide-react'
import { Num } from '@/components/malha'
import type { LinhaDaGrade, TotaisDaMedicao } from '../types'

/**
 * **Instrumento 4 da planta §5.2 — a grade de medição, na régua da G703.**
 *
 * A G703 é a planilha de medição que o mercado usa há décadas, e a ordem das
 * colunas dela não é estética — é a ordem em que a conferência acontece:
 *
 * ```
 *  contratado original → aditivos → contratado atual │ já medido → ESTE PERÍODO
 *  → estocado │ acumulado → % → saldo → valor
 * ```
 *
 * Três decisões que separam isto de uma tabela com inputs:
 *
 * 1. **A trava é na digitação.** Passar do saldo pinta a célula e mostra o
 *    excesso na hora. Guardar a recusa para a submissão faria o gestor
 *    preencher 200 linhas e descobrir o erro no fim — e o erro que ele veria
 *    seria "o acumulado do item 4.2 excede", sem saber qual das 200 causou.
 * 2. **Nenhum número desta tela é calculado aqui.** Contratado, aditivo, já
 *    medido e saldo vêm resolvidos do servidor (`/medicoes/{id}/contexto/`). A
 *    primeira escrita desta página montava o saldo no navegador a partir de uma
 *    prévia que só existia em um dos caminhos de entrada: abrindo a medição
 *    pelo link direto, "já medido" saía **negativo**, o saldo passava do
 *    contratado e a trava de excesso — que compara contra ele — desligava.
 * 3. **Linha sem vínculo não é linha zerada.** Ela aparece marcada, porque zero
 *    é "não andou" e sem vínculo é "ninguém mediu isto pelo avanço" — confundir
 *    os dois faz o gestor assinar achando que o serviço parou quando o que
 *    faltou foi o cadastro.
 *
 * Quem opera isto passa o dia aqui; cada clique a mais é multiplicado por
 * centenas de linhas. Daí o teclado ser requisito, e daí a **janela**: acima de
 * `LIMITE_JANELA` linhas só as visíveis são montadas, porque um contrato de
 * infraestrutura chega a 2.000 itens (o teto do plano) e 2.000 `<input>` no DOM
 * fazem o navegador engasgar entre a tecla e o caractere.
 */

/** O que o gestor digitou numa linha. Strings, e não `number`: ele digita
 *  vírgula, e converter a cada tecla estragaria "1,", "0,0" e o campo vazio. */
export interface EdicaoDaLinha {
  quantidade: string
  estocada: string
  /** A memória de cálculo **da pessoa** — "medido em campo com o fiscal,
   *  croqui anexo". O `ItemMedicao.observacao` existia desde a PDCA.3 e não
   *  tinha porta nenhuma na tela; ela aparece no boletim, que é onde é lida. */
  observacao: string
}

interface Props {
  linhas: LinhaDaGrade[]
  valores: Record<number, EdicaoDaLinha>
  onMudar: (itemId: number, campo: keyof EdicaoDaLinha, valor: string) => void
  /** `null` na prévia — o documento ainda não existe, e não há totais do
   *  servidor para mostrar. A grade funciona igual nos dois casos. */
  totais: TotaisDaMedicao | null
  somenteLeitura?: boolean
  /** A coluna de material estocado. Some no contrato que não a usa: coluna que
   *  fica sempre zerada só rouba largura de quem precisa ler a que importa. */
  mostrarEstoque?: boolean
  /** Abre a memória de cálculo da linha — de onde saiu a proposta. */
  onVerMemoria?: (linha: LinhaDaGrade) => void
  /** O que oferecer quando **não há planilha contratual**.
   *
   *  A grade vazia dizia *"cadastre os itens para poder medir"* e não dizia
   *  onde — o dono procurou e não achou. Mensagem que manda fazer algo sem
   *  mostrar o caminho é um beco: ou ela traz o botão, ou não deveria estar
   *  pedindo. */
  acaoVazia?: React.ReactNode
}

/** Acima disto, só as linhas visíveis vão ao DOM. */
const LIMITE_JANELA = 80
const ALTURA_LINHA = 38
const FOLGA = 8

/** Aceita vírgula e ponto — o gestor cola de planilha e digita à brasileira. */
export function paraDecimal(texto: string): number {
  const limpo = (texto ?? '').toString().trim().replace(/\s/g, '').replace(',', '.')
  if (!limpo) return 0
  const n = Number(limpo)
  return Number.isFinite(n) ? n : 0
}

/** O que vai para a API: ponto decimal, sempre. */
export function paraApi(texto: string): string {
  return String(paraDecimal(texto))
}

const dinheiro = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const quantidade = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 })

const CRITERIO_ROTULO: Record<string, string> = {
  direto: 'Avanço da atividade vinculada',
  ponderado: 'Média das atividades, ponderada pelo peso',
  media_simples: 'Média simples das atividades (nenhuma tem peso)',
  sem_vinculo: 'Sem atividade nem item orçado ligados a esta linha',
}

export default function GradeDeMedicao({
  linhas, valores, onMudar, totais, somenteLeitura = false,
  mostrarEstoque = false, onVerMemoria, acaoVazia,
}: Props) {
  const refs = useRef<Record<string, HTMLInputElement | null>>({})
  const [foco, setFoco] = useState<number | null>(null)
  const caixa = useRef<HTMLDivElement | null>(null)
  const [topo, setTopo] = useState(0)
  const [altura, setAltura] = useState(600)

  const janela = linhas.length > LIMITE_JANELA
  useEffect(() => {
    if (!janela) return
    const el = caixa.current
    if (!el) return
    const rolar = () => setTopo(el.scrollTop)
    const medir = () => setAltura(el.clientHeight || 600)
    medir()
    el.addEventListener('scroll', rolar, { passive: true })
    window.addEventListener('resize', medir)
    return () => {
      el.removeEventListener('scroll', rolar)
      window.removeEventListener('resize', medir)
    }
  }, [janela])

  const primeira = janela ? Math.max(0, Math.floor(topo / ALTURA_LINHA) - FOLGA) : 0
  const ultima = janela
    ? Math.min(linhas.length, Math.ceil((topo + altura) / ALTURA_LINHA) + FOLGA)
    : linhas.length
  const visiveis = linhas.slice(primeira, ultima)

  const valorDe = useCallback(
    (linha: LinhaDaGrade): EdicaoDaLinha => valores[linha.item_contrato_id] ?? {
      quantidade: String(Number(linha.quantidade_proposta)),
      estocada: String(Number(linha.quantidade_estocada)),
      observacao: linha.observacao,
    },
    [valores],
  )

  /**
   * O excesso é calculado **por linha e a cada tecla** — é a trava da planta.
   *
   * `saldo` já vem do servidor descontando o que outras medições ocupam **e** o
   * material já estocado; o que se confere aqui é a soma do que está sendo
   * digitado agora: executar e estocar ocupam o mesmo contrato.
   */
  const excessos = useMemo(() => {
    const mapa = new Map<number, number>()
    for (const linha of linhas) {
      const v = valorDe(linha)
      const ocupa = paraDecimal(v.quantidade)
        + (mostrarEstoque ? paraDecimal(v.estocada) - Number(linha.estocado_anterior) : 0)
      const saldo = Number(linha.saldo)
      if (ocupa > saldo) mapa.set(linha.item_contrato_id, ocupa - saldo)
    }
    return mapa
  }, [linhas, valorDe, mostrarEstoque])

  const totalDigitado = useMemo(
    () => linhas.reduce((soma, l) => {
      const v = valorDe(l)
      const estoque = mostrarEstoque
        ? paraDecimal(v.estocada) - Number(l.estocado_anterior) : 0
      return soma + (paraDecimal(v.quantidade) + estoque) * Number(l.preco_unitario)
    }, 0),
    [linhas, valorDe, mostrarEstoque],
  )

  /**
   * Enter e as setas andam na coluna; Tab é do navegador e continua sendo.
   *
   * Mexer no Tab seria reescrever uma convenção que o sistema operacional
   * garante — e quem opera planilha o dia inteiro tem essa memória muscular
   * calibrada fora do nosso software.
   */
  const teclado = useCallback((
    evento: React.KeyboardEvent, indice: number, campo: keyof EdicaoDaLinha,
  ) => {
    const ir = (destino: number) => {
      if (destino < 0 || destino >= linhas.length) return
      evento.preventDefault()
      const item = linhas[destino].item_contrato_id
      const alvo = refs.current[`${campo}:${item}`]
      if (alvo) { alvo.focus(); alvo.select() }
      else if (caixa.current) {
        // A linha de destino está fora da janela montada: rola até ela e o
        // foco vai no próximo quadro, quando o input existir.
        caixa.current.scrollTop = destino * ALTURA_LINHA - ALTURA_LINHA * 2
        requestAnimationFrame(() => {
          const agora = refs.current[`${campo}:${item}`]
          if (agora) { agora.focus(); agora.select() }
        })
      }
    }
    if (evento.key === 'Enter' || evento.key === 'ArrowDown') ir(indice + 1)
    else if (evento.key === 'ArrowUp') ir(indice - 1)
  }, [linhas])

  /**
   * Colar de planilha: uma coluna de números cai nas linhas seguintes.
   *
   * É o gesto real de quem mede — o empreiteiro manda a planilha dele, e o
   * gestor confere colando a coluna inteira em vez de digitar 200 células.
   */
  const colar = useCallback((
    evento: React.ClipboardEvent, indice: number, campo: keyof EdicaoDaLinha,
  ) => {
    const texto = evento.clipboardData.getData('text')
    if (!texto.includes('\n') && !texto.includes('\t')) return
    evento.preventDefault()
    const celulas = texto
      .split(/\r?\n/)
      .map(l => l.split('\t')[0].trim())
      .filter(l => l !== '')
    celulas.forEach((valor, deslocamento) => {
      const linha = linhas[indice + deslocamento]
      if (linha) onMudar(linha.item_contrato_id, campo, valor)
    })
  }, [linhas, onMudar])

  if (linhas.length === 0) {
    return (
      <div style={{ padding: '14px 2px' }}>
        <p style={{ color: 'var(--ink-2)', fontSize: 13, margin: 0, maxWidth: 620 }}>
          Este contrato ainda não tem <strong>planilha contratual</strong> — a
          lista do que foi contratado, em que quantidade e por qual preço. É ela
          que diz o que se mede e por quanto, e sem ela não há o que propor.
        </p>
        {acaoVazia && <div style={{ marginTop: 10 }}>{acaoVazia}</div>}
      </div>
    )
  }

  const colunas = 8 + (mostrarEstoque ? 1 : 0)

  return (
    <div>
      <div
        ref={caixa}
        style={{
          overflowX: 'auto', border: '1px solid var(--line)', borderRadius: 10,
          maxHeight: janela ? '60vh' : undefined,
          overflowY: janela ? 'auto' : undefined,
        }}
      >
        <table style={{
          width: '100%', borderCollapse: 'collapse', fontSize: 13,
          minWidth: mostrarEstoque ? 1040 : 940,
        }}>
          <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
            <tr style={{ background: 'var(--surface-2)', textAlign: 'left' }}>
              <Th style={{ width: 80 }}>Item</Th>
              <Th>Descrição</Th>
              <Th style={{ width: 50 }}>Un.</Th>
              <Th n title="Contratado hoje: o original mais os aditivos aprovados">
                Contratado
              </Th>
              <Th n>Já medido</Th>
              <Th n>Saldo</Th>
              <Th n title="O que o sistema calculou a partir do avanço apontado no período">
                Proposto
              </Th>
              <Th n style={{ width: 120 }}>Este período</Th>
              {mostrarEstoque && (
                <Th
                  n
                  style={{ width: 120 }}
                  title="Material posto na obra e ainda não aplicado. É um SALDO: declare o que existe agora, e o que se paga é a diferença contra a medição anterior."
                >
                  Estocado
                </Th>
              )}
              <Th n>Valor</Th>
            </tr>
          </thead>
          <tbody>
            {primeira > 0 && (
              <tr style={{ height: primeira * ALTURA_LINHA }} aria-hidden>
                <td colSpan={colunas + 1} />
              </tr>
            )}
            {visiveis.map((linha, i) => {
              const indice = primeira + i
              const v = valorDe(linha)
              const excesso = excessos.get(linha.item_contrato_id)
              const digitado = paraDecimal(v.quantidade)
              const estocada = paraDecimal(v.estocada)
              const deltaEstoque = mostrarEstoque
                ? estocada - Number(linha.estocado_anterior) : 0
              const ajustada =
                linha.quantidade_proposta != null &&
                digitado !== Number(linha.quantidade_proposta) &&
                digitado !== 0
              const semVinculo = linha.criterio === 'sem_vinculo'
              return (
                <tr
                  key={linha.item_contrato_id}
                  style={{
                    height: ALTURA_LINHA,
                    borderTop: '1px solid var(--line)',
                    background: excesso
                      ? 'color-mix(in srgb, var(--danger-ink) 9%, transparent)'
                      : foco === indice ? 'var(--surface-2)' : undefined,
                  }}
                >
                  <Td mono>{linha.codigo}</Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>{linha.descricao}</span>
                      {linha.nasceu_de_aditivo && (
                        <span
                          title="Item incluído por aditivo — não estava no contrato assinado."
                          style={{ display: 'inline-flex', color: 'var(--accent-ink)' }}
                        >
                          <PlusSquare size={13} />
                        </span>
                      )}
                      {semVinculo && (
                        <span
                          title={CRITERIO_ROTULO.sem_vinculo}
                          style={{ display: 'inline-flex', color: 'var(--accent-ink)' }}
                        >
                          <Link2Off size={13} />
                        </span>
                      )}
                      {v.observacao && (
                        <span
                          title={v.observacao}
                          style={{ display: 'inline-flex', color: 'var(--ink-3)' }}
                        >
                          <StickyNote size={13} />
                        </span>
                      )}
                      {linha.limitada_pelo_saldo && (
                        <span
                          title="O avanço apontado daria mais que o saldo — a proposta foi cortada no que resta do contratado."
                          style={{ display: 'inline-flex', color: 'var(--accent-ink)' }}
                        >
                          <AlertTriangle size={13} />
                        </span>
                      )}
                    </div>
                  </Td>
                  <Td>{linha.unidade}</Td>
                  <Td n>
                    <Num>{quantidade(linha.quantidade_contratada)}</Num>
                    {Number(linha.quantidade_aditivada) !== 0 && (
                      <div
                        title={`Contrato assinado: ${quantidade(linha.quantidade_original)}`}
                        style={{
                          fontSize: 11, marginTop: 1,
                          color: Number(linha.quantidade_aditivada) > 0
                            ? 'var(--accent-ink)' : 'var(--danger-ink)',
                        }}
                      >
                        {Number(linha.quantidade_aditivada) > 0 ? '+' : ''}
                        {quantidade(linha.quantidade_aditivada)} aditivo
                      </div>
                    )}
                  </Td>
                  <Td n><Num>{quantidade(linha.quantidade_ja_medida)}</Num></Td>
                  <Td n><Num>{quantidade(linha.saldo)}</Num></Td>
                  <Td n>
                    {semVinculo ? (
                      <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>—</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onVerMemoria?.(linha)}
                        title={`${CRITERIO_ROTULO[linha.criterio]}${
                          linha.percentual_avanco_periodo != null
                            ? ` · ${Number(linha.percentual_avanco_periodo)}% no período`
                            : ''
                        } — clique para ver a memória de cálculo`}
                        style={{
                          background: 'none', border: 'none', padding: 0,
                          color: 'var(--ink-3)', cursor: onVerMemoria ? 'pointer' : 'default',
                          fontFamily: 'var(--mono)', fontSize: 13,
                          display: 'inline-flex', alignItems: 'center', gap: 3,
                        }}
                      >
                        {onVerMemoria && <Sigma size={11} />}
                        <Num>{quantidade(linha.quantidade_proposta)}</Num>
                      </button>
                    )}
                  </Td>
                  <Td n style={{ padding: '2px 6px' }}>
                    <Celula
                      refs={refs}
                      chave={`quantidade:${linha.item_contrato_id}`}
                      valor={v.quantidade}
                      alerta={Boolean(excesso)}
                      somenteLeitura={somenteLeitura}
                      onChange={t => onMudar(linha.item_contrato_id, 'quantidade', t)}
                      onKeyDown={e => teclado(e, indice, 'quantidade')}
                      onPaste={e => colar(e, indice, 'quantidade')}
                      onFocus={() => setFoco(indice)}
                      onBlur={() => setFoco(null)}
                    />
                    {excesso != null && (
                      <div style={{ fontSize: 11, color: 'var(--danger-ink)', marginTop: 2, textAlign: 'right' }}>
                        {quantidade(excesso)} acima do saldo
                      </div>
                    )}
                    {ajustada && excesso == null && (
                      <div
                        title="O gestor ajustou o que o sistema propôs. A proposta original fica guardada na medição."
                        style={{
                          fontSize: 11, color: 'var(--ink-3)', marginTop: 2,
                          textAlign: 'right', display: 'flex', gap: 3,
                          justifyContent: 'flex-end', alignItems: 'center',
                        }}
                      >
                        <Sparkles size={10} /> ajustado
                      </div>
                    )}
                  </Td>
                  {mostrarEstoque && (
                    <Td n style={{ padding: '2px 6px' }}>
                      <Celula
                        refs={refs}
                        chave={`estocada:${linha.item_contrato_id}`}
                        valor={v.estocada}
                        alerta={false}
                        somenteLeitura={somenteLeitura}
                        onChange={t => onMudar(linha.item_contrato_id, 'estocada', t)}
                        onKeyDown={e => teclado(e, indice, 'estocada')}
                        onPaste={e => colar(e, indice, 'estocada')}
                        onFocus={() => setFoco(indice)}
                        onBlur={() => setFoco(null)}
                      />
                      {deltaEstoque !== 0 && (
                        <div
                          title={
                            deltaEstoque > 0
                              ? 'Material que entrou no período — é isto que esta medição paga.'
                              : 'Material que saiu do estoque (foi aplicado, e o serviço entra pela quantidade).'
                          }
                          style={{
                            fontSize: 11, marginTop: 2, textAlign: 'right',
                            color: deltaEstoque > 0 ? 'var(--accent-ink)' : 'var(--ink-3)',
                          }}
                        >
                          {deltaEstoque > 0 ? '+' : ''}{quantidade(deltaEstoque)} no período
                        </div>
                      )}
                    </Td>
                  )}
                  <Td n>
                    <Num>
                      {dinheiro((digitado + deltaEstoque) * Number(linha.preco_unitario))}
                    </Num>
                  </Td>
                </tr>
              )
            })}
            {ultima < linhas.length && (
              <tr style={{ height: (linhas.length - ultima) * ALTURA_LINHA }} aria-hidden>
                <td colSpan={colunas + 1} />
              </tr>
            )}
          </tbody>
          <tfoot style={{ position: 'sticky', bottom: 0 }}>
            <tr style={{ borderTop: '2px solid var(--line)', background: 'var(--surface-2)' }}>
              <Td colSpan={7} style={{ fontWeight: 600 }}>
                {linhas.length} {linhas.length === 1 ? 'item' : 'itens'}
                {janela && (
                  <span style={{ color: 'var(--ink-3)', fontWeight: 400, marginLeft: 8 }}>
                    · mostrando {primeira + 1}–{ultima}
                  </span>
                )}
                {excessos.size > 0 && (
                  <span style={{ color: 'var(--danger-ink)', fontWeight: 500, marginLeft: 8 }}>
                    · {excessos.size} acima do saldo
                  </span>
                )}
              </Td>
              <Td n style={{ fontWeight: 600 }}>
                <Num>
                  {quantidade(
                    linhas.reduce((s, l) => s + paraDecimal(valorDe(l).quantidade), 0),
                  )}
                </Num>
              </Td>
              {mostrarEstoque && (
                <Td n style={{ fontWeight: 600 }}>
                  <Num>
                    {quantidade(
                      linhas.reduce((s, l) => s + paraDecimal(valorDe(l).estocada), 0),
                    )}
                  </Num>
                </Td>
              )}
              <Td n style={{ fontWeight: 600 }}><Num>{dinheiro(totalDigitado)}</Num></Td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* O rodapé de dinheiro vem do SERVIDOR quando a medição existe. A soma
          que a grade mostra acima é a do que está na tela (feedback imediato de
          digitação); bruto → retenção → deduções → líquido é conta de dinheiro,
          e quem a faz é uma fonte só — a mesma razão que manteve o CPM no
          servidor. */}
      {totais && (
        <div style={{
          display: 'flex', gap: 22, justifyContent: 'flex-end', flexWrap: 'wrap',
          marginTop: 12, fontSize: 13,
        }}>
          {Number(totais.material_estocado) !== 0 && (
            <>
              <Parcela rotulo="Executado" valor={dinheiro(totais.executado)} atenuada />
              <Parcela
                rotulo="Material estocado"
                valor={dinheiro(totais.material_estocado)}
                atenuada
              />
            </>
          )}
          <Parcela rotulo="Bruto" valor={dinheiro(totais.bruto)} />
          <Parcela
            rotulo={`Retenção (${Number(totais.retencao_percentual)}%)`}
            valor={`− ${dinheiro(totais.retencao)}`}
            atenuada
          />
          {Number(totais.total_deducoes) > 0 && (
            <Parcela
              rotulo={`Deduções (${totais.deducoes.length})`}
              valor={`− ${dinheiro(totais.total_deducoes)}`}
              atenuada
            />
          )}
          <Parcela rotulo="Líquido a pagar" valor={dinheiro(totais.liquido)} forte />
        </div>
      )}

      {excessos.size > 0 && (
        <p style={{
          marginTop: 10, fontSize: 12.5, color: 'var(--danger-ink)',
          display: 'flex', gap: 6, alignItems: 'flex-start',
        }}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            Medição acumulada não pode exceder o contratado. Aumentar a
            quantidade contratada é <strong>aditivo</strong> — e o aditivo está
            no painel do contrato, não aqui.
          </span>
        </p>
      )}
    </div>
  )
}

/**
 * A célula de digitação — e, quando não se digita, **um número**.
 *
 * Um `<input readonly>` é uma mentira de interface: ele tem borda, cursor e
 * fundo de campo, convida a clicar e não aceita nada. Foi assim que o dono
 * relatou *"a parte mais importante da medição não consigo editar"*, colando
 * exatamente esse elemento — ele estava na **prévia**, que é somente leitura
 * por desenho, e a tela não dizia isso em lugar nenhum.
 *
 * Em leitura, o valor vira texto. Quem quiser digitar vai ao documento, e a
 * prévia diz onde fica o botão.
 */
function Celula({ refs, chave, valor, alerta, somenteLeitura, onChange, ...resto }: {
  refs: React.MutableRefObject<Record<string, HTMLInputElement | null>>
  chave: string
  valor: string
  alerta: boolean
  somenteLeitura: boolean
  onChange: (v: string) => void
  onKeyDown: (e: React.KeyboardEvent) => void
  onPaste: (e: React.ClipboardEvent) => void
  onFocus: () => void
  onBlur: () => void
}) {
  if (somenteLeitura) {
    return (
      <span style={{
        display: 'block', textAlign: 'right', padding: '6px 8px',
        fontFamily: 'var(--mono)', fontSize: 13,
        fontVariantNumeric: 'tabular-nums',
        color: alerta ? 'var(--danger-ink)' : 'var(--ink)',
      }}>
        {Number(paraDecimal(valor)).toLocaleString('pt-BR', { maximumFractionDigits: 4 })}
      </span>
    )
  }
  return (
    <input
      ref={el => { refs.current[chave] = el }}
      value={valor}
      inputMode="decimal"
      onChange={e => onChange(e.target.value)}
      onFocus={e => { resto.onFocus(); e.target.select() }}
      onKeyDown={resto.onKeyDown}
      onPaste={resto.onPaste}
      onBlur={resto.onBlur}
      style={{
        width: '100%', textAlign: 'right', padding: '6px 8px',
        fontFamily: 'var(--mono)', fontSize: 13, background: 'var(--surface)',
        color: alerta ? 'var(--danger-ink)' : 'var(--ink)',
        border: `1px solid ${alerta ? 'var(--danger-ink)' : 'var(--line)'}`,
        borderRadius: 6, outline: 'none',
      }}
    />
  )
}

function Parcela({ rotulo, valor, forte, atenuada }: {
  rotulo: string; valor: string; forte?: boolean; atenuada?: boolean
}) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ color: 'var(--ink-3)', fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '.04em' }}>
        {rotulo}
      </div>
      <div style={{
        fontFamily: 'var(--mono)', fontSize: forte ? 19 : 15,
        fontWeight: forte ? 600 : 400,
        // `--brand`, e não `--brand-ink` (que é `#FFFFFF`, a tinta para usar
        // *sobre* a marca): o líquido a pagar é o número que a tela existe para
        // mostrar, e sair branco em fundo claro o apagaria.
        color: atenuada ? 'var(--ink-3)' : forte ? 'var(--brand)' : 'var(--ink)',
      }}>
        {valor}
      </div>
    </div>
  )
}

function Th({ children, n, style, title }: {
  children: React.ReactNode; n?: boolean; style?: React.CSSProperties; title?: string
}) {
  return (
    <th
      title={title}
      style={{
        padding: '9px 10px', fontWeight: 600, fontSize: 11.5, color: 'var(--ink-2)',
        textTransform: 'uppercase', letterSpacing: '.04em',
        textAlign: n ? 'right' : 'left', whiteSpace: 'nowrap',
        background: 'var(--surface-2)', ...style,
      }}
    >
      {children}
    </th>
  )
}

function Td({ children, n, mono, style, colSpan }: {
  children?: React.ReactNode; n?: boolean; mono?: boolean
  style?: React.CSSProperties; colSpan?: number
}) {
  return (
    <td
      colSpan={colSpan}
      style={{
        padding: '7px 10px', textAlign: n ? 'right' : 'left',
        fontFamily: mono ? 'var(--mono)' : undefined,
        verticalAlign: 'middle', ...style,
      }}
    >
      {children}
    </td>
  )
}

/**
 * O estado da grade, isolado num hook para a página, a prévia e o boletim
 * dividirem.
 *
 * A grade **não é dona** dos dados: ela recebe as linhas do servidor e devolve
 * edições. Sem isto, trocar o período recriaria o componente e perderia o que o
 * gestor já tinha digitado — que é a diferença entre conferir uma planilha e
 * redigitá-la.
 */
export function useGradeEditavel(
  linhas: LinhaDaGrade[] | undefined,
  /**
   * Com o que a grade **começa**.
   *
   * `'proposta'` é a prévia: o documento não existe, e o que se mostra é o que
   * o sistema calculou. `'documento'` é a medição aberta, e ali o começo é o
   * que está **gravado** — inclusive o zero.
   *
   * A diferença não é cosmética. Com `'proposta'` numa medição aberta, zerar
   * uma linha a fazia voltar sozinha: o autosave gravava o zero, o servidor
   * apagava a linha (linha sem quantidade não vira registro), o contexto
   * voltava com `quantidade_medida: 0` — e a grade, não sabendo distinguir
   * "zerei" de "não mexi", recolocava a proposta e a gravava de volta. O gestor
   * via o número que tinha acabado de apagar reaparecer.
   */
  comeco: 'proposta' | 'documento' = 'proposta',
) {
  const [valores, setValores] = useState<Record<number, EdicaoDaLinha>>({})
  const [assinaturaBase, setAssinaturaBase] = useState('')

  /** O que veio do servidor. A grade só se reinicia quando **isto** muda — uma
   *  revalidação do react-query com o mesmo conteúdo não pode apagar a
   *  digitação em curso. */
  const base = useMemo(() => {
    if (!linhas) return null
    const mapa: Record<number, EdicaoDaLinha> = {}
    for (const l of linhas) {
      mapa[l.item_contrato_id] = {
        quantidade: String(
          comeco === 'documento'
            ? Number(l.quantidade_medida ?? 0)
            : Number(l.quantidade_proposta),
        ),
        estocada: String(Number(l.quantidade_estocada)),
        observacao: l.observacao ?? '',
      }
    }
    return mapa
  }, [linhas, comeco])

  const assinatura = useMemo(
    () => (base
      ? Object.entries(base)
        .map(([k, v]) => `${k}=${v.quantidade}/${v.estocada}/${v.observacao}`).join('|')
      : ''),
    [base],
  )

  useEffect(() => {
    if (!base || assinatura === assinaturaBase) return
    setValores(base)
    setAssinaturaBase(assinatura)
  }, [base, assinatura, assinaturaBase])

  const mudar = useCallback((
    itemId: number, campo: keyof EdicaoDaLinha, valor: string,
  ) => {
    setValores(anterior => ({
      ...anterior,
      [itemId]: {
        quantidade: anterior[itemId]?.quantidade ?? '0',
        estocada: anterior[itemId]?.estocada ?? '0',
        observacao: anterior[itemId]?.observacao ?? '',
        [campo]: valor,
      },
    }))
  }, [])

  /** As linhas que vão para a API — as vazias ficam de fora, porque gravar um
   *  item de medição sem quantidade nem estoque enche o documento de linhas que
   *  não pagam nada. */
  const paraEnviar = useMemo(
    () => (linhas ?? [])
      .map(l => ({ linha: l, v: valores[l.item_contrato_id] }))
      .filter(({ v }) => v && (paraDecimal(v.quantidade) !== 0 || paraDecimal(v.estocada) !== 0))
      .map(({ linha, v }) => ({
        item_contrato_id: linha.item_contrato_id,
        quantidade: paraApi(v.quantidade),
        quantidade_estocada: paraApi(v.estocada),
        observacao: v.observacao,
      })),
    [linhas, valores],
  )

  /** A forma estável do que está na tela — é o que o autosave compara. */
  const assinaturaAtual = useMemo(
    () => paraEnviar
      .map(l => `${l.item_contrato_id}=${l.quantidade}/${l.quantidade_estocada}/${l.observacao}`)
      .join('|'),
    [paraEnviar],
  )

  const temExcesso = useMemo(
    () => (linhas ?? []).some(l => {
      const v = valores[l.item_contrato_id]
      if (!v) return false
      const ocupa = paraDecimal(v.quantidade)
        + paraDecimal(v.estocada) - Number(l.estocado_anterior)
      return ocupa > Number(l.saldo)
    }),
    [linhas, valores],
  )

  return { valores, mudar, paraEnviar, assinaturaAtual, temExcesso }
}
