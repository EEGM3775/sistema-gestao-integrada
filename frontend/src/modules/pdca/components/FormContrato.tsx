import { useMemo, useState } from 'react'
import {
  Btn, CampoDecimal, CampoInteiro, CampoMoeda, Modal, daApi, paraNumero,
} from '@/components/malha'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { useAtualizarContrato, useCriarContrato, useFornecedoresOpt } from '../hooks'
import type { Contrato, NaturezaRetencao, ObraOpt, RegimeContrato } from '../types'

/**
 * O cadastro do contrato.
 *
 * **O que este formulário faz de diferente de um CRUD:** ele mostra o campo que
 * a regra exige *quando* ela passa a valer, em vez de exibir todos os campos
 * sempre. Regime global pede o valor fechado; administração pede valor e taxa;
 * unitário não pede nenhum dos dois, porque lá o valor é a soma dos itens — e
 * um total digitado ao lado da soma seria a segunda verdade que a planta §4.9
 * proíbe.
 *
 * O mesmo vale para o **regime público** (§11.3): ligá-lo revela o campo do
 * limite legal de acréscimo, que é **digitado pelo usuário**. O sistema confere
 * contra o número declarado; escolher 25% ou 50% por ele erraria na exceção —
 * nem toda obra com dinheiro público segue o mesmo estatuto.
 */

const REGIMES: { valor: RegimeContrato; rotulo: string; ajuda: string }[] = [
  {
    valor: 'unitario', rotulo: 'Preço unitário',
    ajuda: 'Mede-se quantidade × preço de cada item. É o único regime em que o avanço físico vira quantidade a pagar direto.',
  },
  {
    valor: 'global', rotulo: 'Preço global',
    ajuda: 'Valor fechado. Os itens são o cronograma físico-financeiro e a soma deles precisa fechar com o valor do contrato.',
  },
  {
    valor: 'administracao', rotulo: 'Administração (custo + taxa)',
    ajuda: 'A cada período você informa quanto a obra custou (mão de obra, material, equipamento) e o empreiteiro recebe isso mais a taxa. Não se mede quantidade.',
  },
]

const NATUREZAS: { valor: NaturezaRetencao; rotulo: string }[] = [
  { valor: 'nenhuma', rotulo: 'Sem retenção' },
  { valor: 'caucao', rotulo: 'Caução contratual' },
  { valor: 'garantia', rotulo: 'Garantia de execução' },
  { valor: 'tecnica', rotulo: 'Retenção técnica' },
]

interface Props {
  obras: ObraOpt[]
  contrato?: Contrato
  /** A obra já escolhida pelo endereço (`/app/pdca/obra/:id/contratos`). Com ela
   *  o seletor fica travado: quem chegou aqui pela obra já respondeu essa
   *  pergunta, e reabri-la convidaria a criar o contrato na obra errada. */
  obraFixa?: number
  onClose: () => void
  onPronto: (id: number) => void
}

export function ModalContrato({ obras, contrato, obraFixa, onClose, onPronto }: Props) {
  const editando = contrato != null
  const criar = useCriarContrato()
  const atualizar = useAtualizarContrato(contrato?.contrato_id)
  const [erros, setErros] = useState<FieldErrors>({})
  const [buscaFornecedor, setBuscaFornecedor] = useState('')
  const fornecedores = useFornecedoresOpt(buscaFornecedor)
  // Ao **editar**, o fornecedor do contrato tem de estar na lista mesmo que a
  // busca não o traga (página de 40, ou um termo digitado que não o casa).
  // Sem isto o select cairia em "Selecione…" e o salvar seguinte apagaria o
  // vínculo — o formulário desfazendo em silêncio o que ninguém pediu.
  const opcoesFornecedor = useMemo(() => {
    const achados = fornecedores.data ?? []
    if (!contrato?.fornecedor || achados.some(x => x.fornecedor_id === contrato.fornecedor)) {
      return achados
    }
    return [
      { fornecedor_id: contrato.fornecedor, razao_social: contrato.fornecedor_nome },
      ...achados,
    ]
  }, [fornecedores.data, contrato])

  // **Dinheiro em centavos inteiros, percentual em texto.** São representações
  // diferentes porque as perguntas são diferentes: R$ nunca tem mais de duas
  // casas e não pode passar por float (`utils/money.ts`); percentual tem casas
  // variáveis e precisa aceitar estados intermediários que um número não
  // representa ("5,", vazio).
  const [f, setF] = useState({
    obra: contrato?.obra ?? obraFixa ?? obras[0]?.obra_id ?? 0,
    fornecedor: contrato?.fornecedor ?? 0,
    numero: contrato?.numero ?? '',
    objeto: contrato?.objeto ?? '',
    regime: (contrato?.regime ?? 'unitario') as RegimeContrato,
    valor_global: apiDecimalToCents(contrato?.valor_global),
    taxa_administracao: daApi(contrato?.taxa_administracao),
    data_inicio: contrato?.data_inicio ?? '',
    data_fim: contrato?.data_fim ?? '',
    garantia_meses: contrato?.garantia_meses ?? 0,
    retencao_percentual: daApi(contrato?.retencao_percentual) || '0',
    retencao_natureza: (contrato?.retencao_natureza ?? 'nenhuma') as NaturezaRetencao,
    retencao_condicao_liberacao: contrato?.retencao_condicao_liberacao ?? '',
    regime_publico: contrato?.regime_publico ?? false,
    limite_acrescimo_percentual: daApi(contrato?.limite_acrescimo_percentual),
    prazo_pagamento_dias: contrato?.prazo_pagamento_dias ?? 30,
    status: contrato?.status ?? 'rascunho',
  })

  const set = <K extends keyof typeof f>(campo: K, valor: (typeof f)[K]) =>
    setF(anterior => ({ ...anterior, [campo]: valor }))

  const pedeValorGlobal = f.regime === 'global' || f.regime === 'administracao'
  const temRetencao = Number(paraNumero(f.retencao_percentual) ?? 0) > 0

  async function salvar() {
    setErros({})
    // Campos vazios viram `null`, e não string vazia: o backend distingue "não
    // informado" de zero, e uma string vazia num `DecimalField` nulável vira
    // erro de validação em vez de ausência.
    const payload: Partial<Contrato> = {
      obra: Number(f.obra),
      fornecedor: Number(f.fornecedor),
      numero: f.numero.trim(),
      objeto: f.objeto.trim(),
      regime: f.regime,
      valor_global: pedeValorGlobal && f.valor_global > 0
        ? centsToApiDecimal(f.valor_global) : null,
      taxa_administracao:
        f.regime === 'administracao' ? paraNumero(f.taxa_administracao) : null,
      data_inicio: f.data_inicio,
      data_fim: f.data_fim || null,
      garantia_meses: f.garantia_meses,
      retencao_percentual: paraNumero(f.retencao_percentual) ?? '0',
      retencao_natureza: f.retencao_natureza,
      retencao_condicao_liberacao: f.retencao_condicao_liberacao,
      regime_publico: f.regime_publico,
      limite_acrescimo_percentual:
        f.regime_publico ? paraNumero(f.limite_acrescimo_percentual) : null,
      prazo_pagamento_dias: f.prazo_pagamento_dias || 30,
      status: f.status,
    }
    try {
      const salvo = editando
        ? await atualizar.mutateAsync(payload)
        : await criar.mutateAsync(payload)
      onPronto(salvo.contrato_id)
    } catch (erro) {
      setErros(parseApiErrors(erro))
    }
  }

  const salvando = criar.isPending || atualizar.isPending

  return (
    <Modal
      titulo={editando ? `Contrato ${contrato.numero}` : 'Novo contrato de obra'}
      onClose={onClose}
      largura={620}
      alto
      rodape={
        <>
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn variant="brand" onClick={salvar} disabled={salvando}>
            {salvando ? 'Salvando…' : 'Salvar'}
          </Btn>
        </>
      }
    >
      <FormErrorBanner errors={erros} />
      {/* **Quem rola é o miolo, não a janela.** O `Modal` com `alto` prende
          cabeçalho e rodapé e entrega a sobra ao conteúdo — mas só se o filho
          colaborar (é o que a doc dele pede). Sem o `overflowY` e o
          `minHeight: 0` aqui, este formulário empurrava o rodapé para fora da
          tela em janela baixa, e os botões de salvar ficavam inalcançáveis. */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 14,
        flex: 1, minHeight: 0, overflowY: 'auto',
        // O respiro que impede a sombra do foco de encostar na borda do corte.
        paddingRight: 4, marginRight: -4,
      }}>
        <Duas>
          <Campo rotulo="Obra">
            <select
              value={f.obra}
              onChange={e => set('obra', Number(e.target.value))}
              disabled={editando || obraFixa != null}
              style={entrada}
            >
              {obras.map(o => (
                <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>
              ))}
            </select>
            <FieldError msg={erros.obra} />
          </Campo>

          <Campo rotulo="Empreiteiro">
            <input
              value={buscaFornecedor}
              onChange={e => setBuscaFornecedor(e.target.value)}
              placeholder="Buscar por razão social…"
              style={{ ...entrada, marginBottom: 6 }}
            />
            <select
              value={f.fornecedor}
              onChange={e => set('fornecedor', Number(e.target.value))}
              style={entrada}
            >
              <option value={0}>Selecione…</option>
              {opcoesFornecedor.map(forn => (
                <option key={forn.fornecedor_id} value={forn.fornecedor_id}>
                  {forn.razao_social}
                </option>
              ))}
            </select>
            {/* **Lista vazia não pode ser um select mudo.** São três causas com
                ações opostas — ainda carregando, a ponte não contratada, ou o
                cadastro realmente vazio —, e o `Selecione…` sozinho as trata
                como uma só. É a mesma régua do D118, no select de calendário. */}
            {fornecedores.isLoading ? (
              <p style={ajudaTexto}>Carregando fornecedores…</p>
            ) : fornecedores.isError ? (
              <p style={{ ...ajudaTexto, color: 'var(--danger-ink)' }}>
                Não deu para ler o cadastro de fornecedores — ele exige a
                permissão <code>cadastro.fornecedor.view</code>, que este perfil
                não tem. Peça ao administrador ou escolha outro usuário.
              </p>
            ) : opcoesFornecedor.length === 0 ? (
              <p style={ajudaTexto}>
                {buscaFornecedor
                  ? `Nenhum fornecedor com "${buscaFornecedor}".`
                  : 'Nenhum fornecedor cadastrado ainda. O contrato usa o cadastro '
                    + 'que já existe — cadastre o empreiteiro em Fornecedores primeiro.'}
              </p>
            ) : (
              <p style={ajudaTexto}>
                Usa o cadastro de fornecedores que já existe — o PDCA não cadastra
                fornecedor.
              </p>
            )}
            <FieldError msg={erros.fornecedor} />
          </Campo>
        </Duas>

        <Duas>
          <Campo rotulo="Número do contrato" ajuda="Como a sua empresa numera. Único por obra.">
            <input
              value={f.numero}
              onChange={e => set('numero', e.target.value)}
              placeholder="001/2026"
              style={entrada}
            />
            <FieldError msg={erros.numero} />
          </Campo>
          <Campo rotulo="Situação">
            <select value={f.status} onChange={e => set('status', e.target.value as Contrato['status'])} style={entrada}>
              <option value="rascunho">Rascunho</option>
              <option value="vigente">Vigente</option>
              <option value="suspenso">Suspenso</option>
              <option value="encerrado">Encerrado</option>
              <option value="cancelado">Cancelado</option>
            </select>
            {/* A tela diz a consequência antes de ela acontecer. */}
            <p style={ajudaTexto}>Só contrato vigente aceita medição.</p>
          </Campo>
        </Duas>

        <Campo rotulo="Objeto">
          <textarea
            value={f.objeto}
            onChange={e => set('objeto', e.target.value)}
            rows={2}
            placeholder="O que este contrato compra — ex.: alvenaria e revestimento da torre A"
            style={{ ...entrada, resize: 'vertical' }}
          />
          <FieldError msg={erros.objeto} />
        </Campo>

        <Campo rotulo="Regime">
          <select
            value={f.regime}
            onChange={e => set('regime', e.target.value as RegimeContrato)}
            style={entrada}
          >
            {REGIMES.map(r => <option key={r.valor} value={r.valor}>{r.rotulo}</option>)}
          </select>
          <p style={ajudaTexto}>{REGIMES.find(r => r.valor === f.regime)?.ajuda}</p>
          <FieldError msg={erros.regime} />
        </Campo>

        {/* Os campos aparecem quando a regra passa a valer — não antes. */}
        {pedeValorGlobal && (
          <Duas>
            <Campo rotulo="Valor global">
              <CampoMoeda
                centavos={f.valor_global}
                aoMudar={v => set('valor_global', v)}
              />
              <FieldError msg={erros.valor_global} />
            </Campo>
            {f.regime === 'administracao' && (
              <Campo rotulo="Taxa de administração">
                <CampoDecimal
                  valor={f.taxa_administracao}
                  aoMudar={v => set('taxa_administracao', v)}
                  sufixo="%"
                  casas={3}
                />
                <FieldError msg={erros.taxa_administracao} />
              </Campo>
            )}
          </Duas>
        )}

        <Duas>
          <Campo rotulo="Início da vigência">
            <input type="date" value={f.data_inicio} onChange={e => set('data_inicio', e.target.value)} style={entrada} />
            <FieldError msg={erros.data_inicio} />
          </Campo>
          <Campo rotulo="Fim da vigência">
            <input type="date" value={f.data_fim ?? ''} onChange={e => set('data_fim', e.target.value)} style={entrada} />
            <FieldError msg={erros.data_fim} />
          </Campo>
        </Duas>

        <Duas>
          <Campo rotulo="Prazo de pagamento" ajuda="Conta a partir da aprovação da medição — é o vencimento do título no financeiro.">
            <CampoInteiro
              valor={f.prazo_pagamento_dias}
              aoMudar={v => set('prazo_pagamento_dias', v)}
              max={365}
            />
          </Campo>
          <Campo rotulo="Garantia (meses)">
            <CampoInteiro
              valor={f.garantia_meses}
              aoMudar={v => set('garantia_meses', v)}
              max={600}
            />
          </Campo>
        </Duas>

        <fieldset style={secao}>
          <legend style={legenda}>Retenção</legend>
          <Duas>
            <Campo rotulo="Percentual">
              <CampoDecimal
                valor={f.retencao_percentual}
                aoMudar={v => set('retencao_percentual', v)}
                sufixo="%"
                casas={2}
              />
              <FieldError msg={erros.retencao_percentual} />
            </Campo>
            <Campo rotulo="Natureza">
              <select
                value={f.retencao_natureza}
                onChange={e => set('retencao_natureza', e.target.value as NaturezaRetencao)}
                style={entrada}
              >
                {NATUREZAS.map(n => <option key={n.valor} value={n.valor}>{n.rotulo}</option>)}
              </select>
              <FieldError msg={erros.retencao_natureza} />
            </Campo>
          </Duas>
          {temRetencao && (
            <Campo
              rotulo="Condição de liberação"
              ajuda="Quando este dinheiro volta ao empreiteiro. É contra este texto que a liberação declara o que foi cumprido."
            >
              <textarea
                value={f.retencao_condicao_liberacao}
                onChange={e => set('retencao_condicao_liberacao', e.target.value)}
                rows={2}
                style={{ ...entrada, resize: 'vertical' }}
              />
            </Campo>
          )}
        </fieldset>

        <fieldset style={secao}>
          <legend style={legenda}>Regime público</legend>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5 }}>
            <input
              type="checkbox"
              checked={f.regime_publico}
              onChange={e => set('regime_publico', e.target.checked)}
            />
            Este contrato segue regime público
          </label>
          <p style={ajudaTexto}>
            É uma <strong>opção sua</strong>, não um regime que o sistema impõe pela
            origem do dinheiro — nem toda obra com verba pública segue o mesmo estatuto.
          </p>
          {f.regime_publico && (
            <Campo
              rotulo="Limite legal de acréscimo"
              ajuda="O sistema confere contra o número que você declarar. Ele não escolhe o percentual por você."
            >
              <CampoDecimal
                valor={f.limite_acrescimo_percentual}
                aoMudar={v => set('limite_acrescimo_percentual', v)}
                sufixo="%"
                casas={2}
              />
              <FieldError msg={erros.limite_acrescimo_percentual} />
            </Campo>
          )}
        </fieldset>
      </div>
    </Modal>
  )
}

const entrada: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5,
}

const ajudaTexto: React.CSSProperties = {
  margin: '5px 0 0', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.45,
}

const secao: React.CSSProperties = {
  border: '1px solid var(--line)', borderRadius: 10, padding: '10px 12px 12px',
  display: 'flex', flexDirection: 'column', gap: 12, margin: 0,
}

const legenda: React.CSSProperties = {
  fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase',
  letterSpacing: '.05em', padding: '0 6px',
}

function Campo({ rotulo, ajuda, children }: {
  rotulo: string; ajuda?: string; children: React.ReactNode
}) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <label style={{ display: 'block', fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 4 }}>
        {rotulo}
      </label>
      {children}
      {ajuda && <p style={ajudaTexto}>{ajuda}</p>}
    </div>
  )
}

function Duas({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{children}</div>
  )
}
