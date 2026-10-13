import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Link2Off, TriangleAlert } from 'lucide-react'
import { CampoDecimal, Card, Empty, Num, Pill, daApi, paraNumero } from '@/components/malha'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { percentual } from '../formato'
import { rotuloDoSalvamento, useAutosave, type Autosave } from '../autosave'
import type { LinhaDaGradeDeMedicao, PropostaDeMedicao } from '../types'

/** O que a tela manda de volta quando o gestor confirma a grade. */
export interface LinhaEditada {
  item_contrato_id: number
  quantidade: string
  quantidade_estocada: string
  observacao: string
}

/** A retificadora guarda a medição corrigida **inteira** (decisão do dono,
 *  11/10/2026): o campo é o número certo, e o que a original mediu viaja ao
 *  lado (`quantidade_na_original`) para o quadro original | corrigido | diferença. */
function daLinha(linha: LinhaDaGradeDeMedicao): LinhaEditada {
  return {
    item_contrato_id: linha.item_contrato_id,
    quantidade: daApi(linha.quantidade_medida),
    quantidade_estocada: daApi(linha.quantidade_estocada),
    observacao: linha.observacao,
  }
}

/** O valor da linha, do jeito que o servidor o soma: quantidade × preço.
 *
 *  **É a única conta que a tela faz**, e ela é local e transitória — serve
 *  para a pessoa ver o efeito do que está digitando *antes* de salvar. O
 *  número que vale é `totais` do servidor, e é ele que aparece no rodapé: por
 *  isso o rodapé não soma esta coluna. Somar aqui e publicar o resultado como
 *  total seria a segunda verdade que o D138 cobrou caro. */
function valorProvisorio(linha: LinhaDaGradeDeMedicao, editada: LinhaEditada): number {
  const preco = apiDecimalToCents(linha.preco_unitario)
  const quantidade = Number(paraNumero(editada.quantidade) ?? '0')
  const estocada = Number(paraNumero(editada.quantidade_estocada) ?? '0')
  return Math.round(preco * (quantidade + estocada))
}

/** **A grade do boletim — as dez colunas da G703, calculadas no servidor.**
 *
 *  A tela não recalcula contratado, acumulado nem saldo. A primeira escrita
 *  desta página montava `saldo = contratado − já medido` no navegador com
 *  dados que só existiam quando o gestor chegava pela prévia; entrando pelo
 *  link direto da medição, a mesma tela mostrava "já medido" **negativo** e
 *  saldo acima do contratado — e a trava de excesso, que compara contra esse
 *  saldo, parava de funcionar exatamente ali.
 *
 *  **Em leitura, número é texto** (convenções §10): `somenteLeitura` troca o
 *  campo por um `<span>` alinhado em vez de um `input` desabilitado, que tem
 *  borda e cursor e convida a clicar sem aceitar nada. A prévia inteira é
 *  assim, e a tela **diz** que é. */
export function GradeDeMedicao({
  contexto, somenteLeitura, motivoDaLeitura, aoSalvar, aoVerAtividade,
  acaoVazia, aoRegistrarAutosave,
}: {
  /** `PropostaDeMedicao` e não `ContextoDeMedicao` **de propósito**: a mesma
   *  grade desenha a prévia (que não tem documento por trás) e o boletim
   *  aberto. Duas grades para as mesmas dez colunas divergiriam na primeira
   *  coluna nova. */
  contexto: PropostaDeMedicao
  somenteLeitura: boolean
  /** **Por que não se digita aqui**, e a frase é de quem chama.
   *
   *  Leitura por congelamento e leitura por falta de permissão são dois
   *  estados diferentes, e uma frase só para os dois mente num deles: quem não
   *  tem `pdca.medicao.apurar` leria "o boletim já foi enviado" diante de um
   *  rascunho que ninguém enviou, e iria procurar um envio que não houve. */
  motivoDaLeitura?: string
  /** A gravação da grade. **Não há botão de salvar** — ver o `useAutosave`
   *  abaixo e o D137. */
  aoSalvar?: (linhas: LinhaEditada[]) => Promise<unknown>
  /** Clicar numa atividade da memória de cálculo a seleciona no inspetor — é
   *  o que liga o número de volta ao plano que o produziu. */
  aoVerAtividade?: (atividadeId: number) => void
  /** Estado vazio que pede uma ação **traz o botão** que leva até ela
   *  (convenções §12): a página preenche com o caminho certo. */
  acaoVazia?: React.ReactNode
  /** Entrega o autosave a quem tem o botão de submeter: **submeter grava
   *  antes de submeter**, e se a gravação falhar o envio não acontece. Sem
   *  esta ponte, o servidor congelaria o que está gravado e não o que está na
   *  tela — que é o D137 inteiro. */
  aoRegistrarAutosave?: (a: Autosave | null) => void
}) {
  const [editadas, setEditadas] = useState<Map<number, LinhaEditada>>(new Map())
  const [abertas, setAbertas] = useState<Set<number>>(new Set())
  const retificando = contexto.linhas[0]?.quantidade_na_original != null

  /** A grade volta ao que o servidor diz sempre que o documento muda — salvar
   *  devolve linhas novas, e manter o rascunho local por cima mostraria o que
   *  a pessoa digitou no lugar do que foi gravado. */
  useEffect(() => {
    setEditadas(new Map(contexto.linhas.map((l) => [l.item_contrato_id, daLinha(l)])))
  }, [contexto])

  const linhasParaSalvar = useMemo(
    () => contexto.linhas.map(
      (l) => editadas.get(l.item_contrato_id) ?? daLinha(l),
    ),
    [contexto.linhas, editadas],
  )

  /** **A forma estável do que está na tela.** É ela que decide se houve
   *  edição: comparar objetos por identidade faria toda remontagem contar como
   *  mudança e regravaria linhas que ninguém tocou. */
  const assinatura = useMemo(
    () => JSON.stringify(linhasParaSalvar),
    [linhasParaSalvar],
  )

  /** **Grava sozinho, e diz que gravou** — o D137 em uma linha.
   *
   *  "Salvar grade" e "Submeter" como botões independentes produziram a pior
   *  classe de defeito de software de dinheiro: quem digitasse 200 linhas e
   *  clicasse direto em submeter via o documento ser aprovado **com os números
   *  antigos**, sem erro, sem aviso, e com um título a pagar no fim. O botão
   *  de salvar existia porque o sistema não sabia gravar sozinho. */
  const autosave = useAutosave({
    valor: linhasParaSalvar,
    assinatura,
    salvar: (linhas) => (aoSalvar ? aoSalvar(linhas) : Promise.resolve()),
    ativo: !somenteLeitura && aoSalvar != null,
  })

  useEffect(() => {
    aoRegistrarAutosave?.(somenteLeitura ? null : autosave)
    return () => aoRegistrarAutosave?.(null)
  }, [aoRegistrarAutosave, autosave, somenteLeitura])

  if (contexto.linhas.length === 0) {
    return (
      <Card>
        <Empty>
          <span style={{ lineHeight: 1.6 }}>
            Este contrato ainda não tem planilha contratual. Cadastre os itens —
            com quantidade, unidade e preço — para poder medir.
          </span>
          {acaoVazia}
        </Empty>
      </Card>
    )
  }

  function mudar(id: number, campo: keyof LinhaEditada, valor: string) {
    setEditadas((atual) => {
      const novo = new Map(atual)
      const linha = novo.get(id)
      if (linha) novo.set(id, { ...linha, [campo]: valor })
      return novo
    })
  }

  function alternarMemoria(id: number) {
    setAbertas((atual) => {
      const novo = new Set(atual)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })
  }

  const semVinculo = contexto.cobertura.sem_vinculo

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* **O denominador da honestidade.** Sem esta frase, uma linha que o
          sistema não soube calcular chega como zero, e zero de "sem vínculo" é
          indistinguível de zero de "não andou no período". */}
      {semVinculo > 0 && (
        <div
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 8,
            padding: '9px 12px', borderRadius: 'var(--r-sm)',
            background: 'var(--info-soft)', color: 'var(--info-ink)',
            fontSize: 12.5, lineHeight: 1.5,
          }}
        >
          <Link2Off size={14} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>
            {semVinculo} de {contexto.cobertura.itens} itens não têm serviço do
            cronograma ligado a eles, então o sistema não conseguiu propor
            quantidade — preencha à mão ou ligue o item a uma atividade na
            planilha do contrato.
            {contexto.cobertura.codigos_sem_vinculo.length > 0 && (
              <>
                {' '}
                <span style={{ fontFamily: 'var(--mono)' }}>
                  {contexto.cobertura.codigos_sem_vinculo.join(' · ')}
                </span>
              </>
            )}
          </span>
        </div>
      )}

      {somenteLeitura && motivoDaLeitura && (
        <div
          style={{
            padding: '8px 12px', borderRadius: 'var(--r-sm)',
            background: 'var(--inset)', color: 'var(--ink-3)', fontSize: 12.5,
            lineHeight: 1.55,
          }}
        >
          Esta grade é de leitura: {motivoDaLeitura}
        </div>
      )}

      <Card pad={false} style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1020 }}>
            <thead>
              <tr>
                {[
                  { r: 'Item', a: 'left' },
                  { r: 'Descrição', a: 'left' },
                  { r: 'Un', a: 'left' },
                  { r: 'Contratado', a: 'right' },
                  { r: 'Já medido', a: 'right' },
                  { r: 'Saldo', a: 'right' },
                  { r: retificando ? 'Na original' : 'Proposto', a: 'right' },
                  { r: retificando ? 'Corrigido' : 'Medido no período', a: 'right' },
                  { r: 'Material na obra', a: 'right' },
                  { r: retificando ? 'Diferença (R$)' : 'Valor', a: 'right' },
                ].map((coluna) => (
                  <th
                    key={coluna.r}
                    style={{
                      textAlign: coluna.a as 'left' | 'right',
                      padding: '8px 10px', fontSize: 10.5, fontWeight: 700,
                      letterSpacing: '0.07em', textTransform: 'uppercase',
                      color: 'var(--ink-3)', whiteSpace: 'nowrap',
                      borderBottom: '1px solid var(--line)',
                      background: 'var(--surface-2)',
                    }}
                  >
                    {coluna.r}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {contexto.linhas.map((linha) => {
                const editada = editadas.get(linha.item_contrato_id) ?? daLinha(linha)
                const aberta = abertas.has(linha.item_contrato_id)
                return (
                  <Linha
                    key={linha.item_contrato_id}
                    linha={linha}
                    editada={editada}
                    aberta={aberta}
                    somenteLeitura={somenteLeitura}
                    aoMudar={mudar}
                    aoAlternar={alternarMemoria}
                    aoVerAtividade={aoVerAtividade}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* **O selo é permanente**, e não um aviso que só aparece quando falha:
          uma tela que só fala no erro deixa quem digitou sem saber se o
          silêncio é bom. Não há botão de salvar — a grade grava sozinha. */}
      {!somenteLeitura && aoSalvar && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Pill
            kind={
              autosave.estado === 'erro' ? 'danger'
                : autosave.estado === 'salvo' ? 'good'
                  : autosave.estado === 'limpo' ? 'slate' : 'accent'
            }
          >
            {rotuloDoSalvamento(autosave)}
          </Pill>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            A grade grava sozinha — não há botão de salvar.
          </span>
        </div>
      )}
    </div>
  )
}

function Linha({
  linha, editada, aberta, somenteLeitura, aoMudar, aoAlternar, aoVerAtividade,
}: {
  linha: LinhaDaGradeDeMedicao
  editada: LinhaEditada
  aberta: boolean
  somenteLeitura: boolean
  aoMudar: (id: number, campo: keyof LinhaEditada, valor: string) => void
  aoAlternar: (id: number) => void
  aoVerAtividade?: (atividadeId: number) => void
}) {
  const id = linha.item_contrato_id
  const temMemoria = linha.memoria.length > 0
  const proposto = percentual(linha.percentual_avanco_periodo)
  const retificadora = linha.quantidade_na_original != null
  const excede = Number(paraNumero(editada.quantidade) ?? '0')
    + Number(paraNumero(editada.quantidade_estocada) ?? '0')
    > Number(linha.saldo)

  return (
    <>
      <tr style={{ borderBottom: '1px solid var(--line-2)' }}>
        <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
          <button
            type="button"
            onClick={() => aoAlternar(id)}
            aria-expanded={aberta}
            title={
              temMemoria
                ? 'Ver de onde saiu a quantidade proposta'
                : 'Esta linha não tem memória de cálculo — nenhum serviço do cronograma está ligado a ela'
            }
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              background: 'none', border: 'none', padding: 0,
              cursor: 'pointer', color: 'inherit', font: 'inherit',
            }}
          >
            {aberta
              ? <ChevronDown size={13} style={{ color: 'var(--ink-3)' }} />
              : <ChevronRight size={13} style={{ color: 'var(--ink-3)' }} />}
            <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}>
              {linha.codigo}
            </span>
          </button>
        </td>

        <td style={{ padding: '7px 10px', fontSize: 12.5, color: 'var(--ink)', maxWidth: 260 }}>
          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {linha.descricao}
          </div>
          {linha.nasceu_de_aditivo && (
            <span style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>nasceu de aditivo</span>
          )}
        </td>

        <td style={{ padding: '7px 10px', fontSize: 12, color: 'var(--ink-3)' }}>
          {linha.unidade}
        </td>

        <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap' }}>
          <Num size={12} tone="var(--ink-2)">{daApi(linha.quantidade_contratada)}</Num>
          {apiDecimalToCents(linha.quantidade_aditivada) !== 0 && (
            <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>
              original {daApi(linha.quantidade_original)}
            </div>
          )}
        </td>

        <td style={{ padding: '7px 10px', textAlign: 'right' }}>
          <Num size={12} tone="var(--ink-3)">{daApi(linha.quantidade_ja_medida)}</Num>
        </td>

        <td style={{ padding: '7px 10px', textAlign: 'right' }}>
          <Num size={12} tone="var(--ink-2)">{daApi(linha.saldo)}</Num>
        </td>

        <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap' }}>
          {retificadora ? (
            <Num size={12} tone="var(--ink-3)">{daApi(linha.quantidade_na_original ?? '0')}</Num>
          ) : linha.criterio === 'sem_vinculo' ? (
            <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>
              sem vínculo
            </span>
          ) : (
            <>
              <Num size={12} tone="var(--ink-2)">{daApi(linha.quantidade_proposta)}</Num>
              {proposto && (
                <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>{proposto} no período</div>
              )}
            </>
          )}
          {/* A proposta foi **limitada pelo saldo**, e a tela diz: um
              apontamento errado propagaria para uma quantidade acima do
              contratado, e sem este selo o gestor não saberia que o número que
              está vendo já foi aparado. */}
          {!retificadora && linha.limitada_pelo_saldo && (
            <div style={{ marginTop: 3 }}>
              <Pill kind="accent" title="A proposta foi cortada no saldo restante do item">
                <TriangleAlert size={10} />
                no limite
              </Pill>
            </div>
          )}
        </td>

        <td style={{ padding: '5px 10px', textAlign: 'right', minWidth: 130 }}>
          {somenteLeitura ? (
            <Num size={12.5} tone="var(--ink)">
              {daApi(linha.quantidade_medida)}
            </Num>
          ) : (
            <>
              <CampoDecimal
                valor={editada.quantidade}
                aoMudar={(v) => aoMudar(id, 'quantidade', v)}
                aria-label={`Quantidade medida de ${linha.codigo}`}
                style={excede ? { borderColor: 'var(--danger)' } : undefined}
              />
              {/* **A trava acende na digitação, e não na submissão.** O
                  servidor recusa o excesso de qualquer jeito — é ele que
                  manda —, mas descobrir isso só ao submeter faz o gestor
                  conferir uma grade inteira de números impossíveis. O saldo
                  contra o qual se compara é o do servidor; a tela não o
                  recalcula. */}
              {excede && (
                <div
                  style={{
                    fontSize: 10.5, color: 'var(--danger-ink)', marginTop: 3,
                    textAlign: 'right', lineHeight: 1.4,
                  }}
                >
                  passa do saldo ({daApi(linha.saldo)} {linha.unidade})
                </div>
              )}
            </>
          )}
        </td>

        <td style={{ padding: '5px 10px', textAlign: 'right', minWidth: 130 }}>
          {somenteLeitura ? (
            <Num size={12.5} tone="var(--ink-2)">{daApi(linha.quantidade_estocada)}</Num>
          ) : (
            <CampoDecimal
              valor={editada.quantidade_estocada}
              aoMudar={(v) => aoMudar(id, 'quantidade_estocada', v)}
              aria-label={`Material posto na obra de ${linha.codigo}`}
            />
          )}
        </td>

        <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap' }}>
          {retificadora ? (() => {
            const preco = apiDecimalToCents(linha.preco_unitario)
            const novo = Math.round(preco * Number(paraNumero(editada.quantidade) ?? '0'))
            const antes = Math.round(preco * Number(linha.quantidade_na_original))
            const dif = novo - antes
            return (
              <>
                <Num size={12} tone={dif === 0 ? 'var(--ink-3)' : dif < 0 ? 'var(--danger-ink)' : 'var(--good-ink)'}>
                  {dif === 0 ? '—' : `${dif > 0 ? '+' : ''}${formatBRL(dif)}`}
                </Num>
                <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>
                  {formatBRL(antes)} → {formatBRL(novo)}
                </div>
              </>
            )
          })() : (
            <Num size={12} tone="var(--ink-2)">
              {formatBRL(valorProvisorio(linha, editada))}
            </Num>
          )}
          <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>
            {formatBRL(apiDecimalToCents(linha.preco_unitario))}/{linha.unidade}
          </div>
        </td>
      </tr>

      {aberta && (
        <tr>
          <td colSpan={10} style={{ padding: 0, background: 'var(--inset)' }}>
            <Memoria
              linha={linha}
              editada={editada}
              somenteLeitura={somenteLeitura}
              aoMudar={aoMudar}
              aoVerAtividade={aoVerAtividade}
            />
          </td>
        </tr>
      )}
    </>
  )
}

/** **De onde saiu o número** — atividade por atividade, com o peso de cada uma.
 *
 *  É o que torna a apuração automática conferível em vez de caixa preta: o
 *  gestor vê que a proposta de 120 m² veio de duas atividades com 60% e 40% de
 *  peso, e clica para ver cada uma no plano. */
function Memoria({
  linha, editada, somenteLeitura, aoMudar, aoVerAtividade,
}: {
  linha: LinhaDaGradeDeMedicao
  editada: LinhaEditada
  somenteLeitura: boolean
  aoMudar: (id: number, campo: keyof LinhaEditada, valor: string) => void
  aoVerAtividade?: (atividadeId: number) => void
}) {
  return (
    <div style={{ padding: '10px 14px 12px 34px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div>
        <div
          style={{
            fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--ink-3)', fontWeight: 700, marginBottom: 5,
          }}
        >
          De onde veio a quantidade proposta
        </div>
        {linha.memoria.length === 0 ? (
          <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            Nenhum serviço do cronograma está ligado a este item, então não há o
            que apurar automaticamente — a quantidade é digitada, e a
            justificativa abaixo é o que explica o número a quem for atestar.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {linha.memoria.map((passo) => (
              <div
                key={passo.atividade}
                style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 12 }}
              >
                <button
                  type="button"
                  onClick={() => aoVerAtividade?.(passo.atividade)}
                  disabled={!aoVerAtividade}
                  style={{
                    background: 'none', border: 'none', padding: 0,
                    cursor: aoVerAtividade ? 'pointer' : 'default',
                    color: aoVerAtividade ? 'var(--brand)' : 'var(--ink-2)',
                    fontFamily: 'var(--mono)', fontSize: 11.5,
                  }}
                >
                  {passo.codigo}
                </button>
                <span style={{ color: 'var(--ink-2)', flex: 1, minWidth: 0 }}>{passo.nome}</span>
                <span style={{ color: 'var(--ink-3)' }}>
                  {percentual(passo.percentual) ?? 'sem apuração'}
                  {passo.peso != null && <> · peso {daApi(passo.peso)}</>}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <label
          style={{
            display: 'block', fontSize: 10.5, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
            marginBottom: 5,
          }}
        >
          Como esta quantidade foi apurada
        </label>
        {somenteLeitura ? (
          <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)' }}>
            {linha.observacao || '—'}
          </p>
        ) : (
          <input
            type="text"
            value={editada.observacao}
            onChange={(e) => aoMudar(linha.item_contrato_id, 'observacao', e.target.value)}
            placeholder="Medido em campo com o fiscal, croqui anexo"
            style={{
              width: '100%', maxWidth: 620, padding: '7px 10px',
              borderRadius: 8, border: '1px solid var(--line)',
              background: 'var(--surface)', color: 'var(--ink)', fontSize: 12.5,
            }}
          />
        )}
      </div>
    </div>
  )
}
