import { useEffect, useState } from 'react'
import {
  Btn, CampoDecimal, CampoInteiro, CampoMoeda, Modal, paraNumero,
} from '@/components/malha'
import apiClient from '@/api/apiClient'
import { centsToApiDecimal } from '@/utils/money'
import { maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import type { NaturezaRetencao, RegimeContrato } from '../types'

interface PedidoDeServico {
  pedido_id: number
  fornecedor: number
  fornecedor_nome?: string
  status: string
  valor_total: string | null
  centro_custo: number | null
}

interface FornecedorOpcao {
  fornecedor_id: number
  razao_social: string
}

interface ClienteOpcao {
  cliente_id: number
  nome_completo: string
}

interface IndiceOpcao {
  id: number
  codigo: string
  nome: string
}

interface ParcelaForm {
  indice: number | ''
  peso: string
  rotulo: string
}

const REGIMES: { valor: RegimeContrato; rotulo: string; explica: string }[] = [
  {
    valor: 'unitario', rotulo: 'Preço unitário',
    explica: 'O valor é a soma da planilha — mede-se quantidade executada.',
  },
  {
    valor: 'global', rotulo: 'Preço global',
    explica: 'Valor fechado; a planilha divide o todo para medir o avanço.',
  },
  {
    valor: 'administracao', rotulo: 'Administração (custo + taxa)',
    explica: 'Mede-se o custo do período, e a taxa é a remuneração do empreiteiro.',
  },
]

const NATUREZAS: { valor: NaturezaRetencao; rotulo: string }[] = [
  { valor: 'nenhuma', rotulo: 'Sem retenção' },
  { valor: 'caucao', rotulo: 'Caução contratual' },
  { valor: 'garantia', rotulo: 'Garantia de execução' },
  { valor: 'tecnica', rotulo: 'Retenção técnica' },
]

/** **O contrato novo** — o que foi combinado com o empreiteiro.
 *
 *  Nasce aqui, e não numa página de cadastro, porque é do contrato que toda
 *  medição desta obra se confere: sem ele o posto abre num estado vazio que
 *  pede uma ação sem caminho, que é o defeito que a régua chama pelo nome
 *  (convenções §12).
 *
 *  **Os seis defeitos do formulário anterior (D132) moram no kit, não aqui**:
 *  dinheiro em `CampoMoeda` (centavos, máscara em real, seleção ao focar),
 *  contagem em `CampoInteiro` (sem zero à esquerda, sem roda do mouse) e
 *  percentual em `CampoDecimal`. O `Modal` vai com `alto`, e o miolo colabora
 *  com `overflowY` e `minHeight: 0` — senão o rodapé sai da tela em janela
 *  baixa e os botões ficam inalcançáveis. */
export function FormularioDeContrato({
  obraId, salvando, erro, aoFechar, aoSalvar,
}: {
  obraId: number
  salvando?: boolean
  erro?: string | null
  aoFechar: () => void
  aoSalvar: (corpo: Record<string, unknown>) => void
}) {
  const [fornecedores, setFornecedores] = useState<FornecedorOpcao[]>([])
  const [carregandoFornecedores, setCarregando] = useState(true)

  const [lado, setLado] = useState<'custo' | 'receita'>('custo')
  const [clientes, setClientes] = useState<ClienteOpcao[]>([])
  const [cliente, setCliente] = useState<number | ''>('')
  const [indices, setIndices] = useState<IndiceOpcao[]>([])
  const [reajustavel, setReajustavel] = useState(false)
  const [dataBase, setDataBase] = useState('')
  const [periodicidade, setPeriodicidade] = useState(12)
  const [parcelaFixa, setParcelaFixa] = useState('0')
  const [parcelas, setParcelas] = useState<ParcelaForm[]>([{ indice: '', peso: '1', rotulo: '' }])
  const [fornecedor, setFornecedor] = useState<number | ''>('')
  const [numero, setNumero] = useState('')
  const [objeto, setObjeto] = useState('')
  const [regime, setRegime] = useState<RegimeContrato>('unitario')
  const [valorGlobal, setValorGlobal] = useState(0)
  const [taxa, setTaxa] = useState('')
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [prazoPagamento, setPrazoPagamento] = useState(30)
  const [retencao, setRetencao] = useState('')
  const [natureza, setNatureza] = useState<NaturezaRetencao>('nenhuma')
  const [condicao, setCondicao] = useState('')
  const [publico, setPublico] = useState(false)
  const [limite, setLimite] = useState('')
  const [pedido, setPedido] = useState<number | ''>('')
  const [pedidos, setPedidos] = useState<PedidoDeServico[]>([])

  /** `/api/fornecedores/` responde **lista crua**, não página — ler `.results`
   *  aqui deixava o select vazio sem erro nenhum (D132). As duas formas são
   *  aceitas, porque o dia em que ele virar paginado não pode esvaziar a
   *  tela. */
  useEffect(() => {
    let vivo = true
    apiClient
      .get<{ results?: FornecedorOpcao[] } | FornecedorOpcao[]>('/fornecedores/', {
        params: { page_size: 300, ordering: 'razao_social' },
      })
      .then(({ data }) => {
        if (!vivo) return
        setFornecedores(Array.isArray(data) ? data : data.results ?? [])
      })
      .finally(() => { if (vivo) setCarregando(false) })
    return () => { vivo = false }
  }, [])

  /** O contratante (lado da receita) e os índices da série única — só quando a
   *  pessoa pede, para não pesar quem abre o formulário de custo. */
  useEffect(() => {
    if (lado !== 'receita' || clientes.length) return
    apiClient
      .get<{ results?: ClienteOpcao[] } | ClienteOpcao[]>('/clientes/', { params: { page_size: 300 } })
      .then(({ data }) => setClientes(Array.isArray(data) ? data : data.results ?? []))
      .catch(() => { /* sem o módulo de clientes: o seletor fica vazio e diz */ })
  }, [lado, clientes.length])
  useEffect(() => {
    if (!reajustavel || indices.length) return
    apiClient
      .get<{ results?: IndiceOpcao[] } | IndiceOpcao[]>('/indices-economicos/')
      .then(({ data }) => setIndices(Array.isArray(data) ? data : data.results ?? []))
      .catch(() => { /* sem índices publicados, a fórmula não tem o que escolher */ })
  }, [reajustavel, indices.length])

  /** Medição × compra de serviço: os pedidos do centro de custo desta obra no
   *  Suprimentos (sem acesso ao Suprimentos, a lista fica vazia e o campo some). */
  useEffect(() => {
    let vivo = true
    apiClient
      .get<{ results?: { centro_custo_id: number }[] } | { centro_custo_id: number }[]>('/scm/centros-custo/', { params: { obra: obraId, page_size: 50 } })
      .then(async ({ data }) => {
        const centros = (Array.isArray(data) ? data : data.results ?? []).map((c) => c.centro_custo_id)
        const listas = await Promise.all(centros.map((c) => apiClient.get<{ results?: PedidoDeServico[] } | PedidoDeServico[]>('/scm/pedidos/', { params: { centro_custo: c, page_size: 200 } })))
        if (!vivo) return
        setPedidos(listas.flatMap(({ data: d }) => (Array.isArray(d) ? d : d.results ?? [])).filter((p) => p.status !== 'cancelado'))
      })
      .catch(() => { /* sem Suprimentos: o campo não aparece */ })
    return () => { vivo = false }
  }, [obraId])

  const comRetencao = Number(paraNumero(retencao) ?? '0') > 0
  const somaPesos = parcelas.reduce((s, p) => s + Number(paraNumero(p.peso) ?? '0'), 0)
    + Number(paraNumero(parcelaFixa) ?? '0')
  const fechou = Math.abs(somaPesos - 1) <= 0.0005
  const formulaOk = !reajustavel || (
    !!dataBase && parcelas.every((p) => p.indice !== '' && Number(paraNumero(p.peso) ?? '0') > 0) && fechou
  )
  const parteOk = lado === 'custo' ? fornecedor !== '' : cliente !== ''
  const completo = parteOk && formulaOk && numero.trim() && objeto.trim() && inicio
    && (regime === 'unitario' || valorGlobal > 0)
    && (regime !== 'administracao' || Number(paraNumero(taxa) ?? '0') > 0)
    && (!comRetencao || natureza !== 'nenhuma')
    && (!publico || Number(paraNumero(limite) ?? '0') > 0)

  function enviar() {
    aoSalvar({
      obra: obraId,
      lado,
      fornecedor: lado === 'custo' ? fornecedor : null,
      cliente: lado === 'receita' ? cliente : null,
      ...(reajustavel ? {
        reajuste_data_base: dataBase,
        reajuste_periodicidade_meses: periodicidade,
        reajuste_parcela_fixa: paraNumero(parcelaFixa) ?? '0',
        parcelas_reajuste: parcelas.map((p) => ({
          indice: p.indice, peso: paraNumero(p.peso) ?? '0', rotulo: p.rotulo.trim(),
        })),
      } : {}),
      numero: numero.trim(),
      objeto: objeto.trim(),
      regime,
      // No unitário o valor é a soma da planilha: mandar um total ao lado dela
      // criaria uma segunda verdade, e o serializer recusa.
      valor_global: regime === 'unitario' ? null : centsToApiDecimal(valorGlobal),
      taxa_administracao:
        regime === 'administracao' ? paraNumero(taxa) : null,
      data_inicio: inicio,
      data_fim: fim || null,
      prazo_pagamento_dias: prazoPagamento,
      retencao_percentual: paraNumero(retencao) ?? '0',
      retencao_natureza: comRetencao ? natureza : 'nenhuma',
      retencao_condicao_liberacao: comRetencao ? condicao.trim() : '',
      regime_publico: publico,
      limite_acrescimo_percentual: publico ? paraNumero(limite) : null,
      pedido_scm: lado === 'custo' && pedido !== '' ? pedido : null,
    })
  }

  return (
    <Modal
      titulo={lado === 'custo' ? 'Novo contrato de empreitada' : 'Novo contrato com o contratante'}
      onClose={aoFechar}
      largura={680}
      alto
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn variant="primary" disabled={!completo || salvando} onClick={enviar}>
            {salvando ? 'Gravando…' : 'Cadastrar contrato'}
          </Btn>
        </div>
      }
    >
      {/* O miolo colabora com o `alto` do Modal: sem estes dois, cabeçalho e
          rodapé empurram o formulário para fora da tela em janela baixa. */}
      <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {erro && (
          <div
            style={{
              padding: '9px 11px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)',
              fontSize: 12.5, lineHeight: 1.5,
            }}
          >
            {erro}
          </div>
        )}

        <Campo rotulo="De que lado da obra">
          <div style={{ display: 'flex', gap: 14 }}>
            {([['custo', 'Empreiteiro', 'a medição gera conta a pagar'],
               ['receita', 'Contratante', 'a medição gera conta a receber']] as const).map(([v, r, e]) => (
              <label key={v} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer' }}>
                <input type="radio" name="lado" checked={lado === v} onChange={() => setLado(v)} style={{ marginTop: 3 }} />
                <span>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{r}</span>
                  <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>{e}</span>
                </span>
              </label>
            ))}
          </div>
        </Campo>

        <Linha>
          {lado === 'receita' ? (
            <Campo rotulo="Contratante" larga>
              <select value={cliente} onChange={(e) => setCliente(e.target.value ? Number(e.target.value) : '')} style={entrada}>
                <option value="">Escolha o contratante</option>
                {clientes.map((c) => (
                  <option key={c.cliente_id} value={c.cliente_id}>{c.nome_completo}</option>
                ))}
              </select>
              <Ajuda>Quem encomendou a obra — o cadastro de clientes da casa.</Ajuda>
            </Campo>
          ) : (
          <Campo rotulo="Empreiteiro" larga>
            <select
              value={fornecedor}
              onChange={(e) => setFornecedor(e.target.value ? Number(e.target.value) : '')}
              disabled={carregandoFornecedores}
              style={entrada}
            >
              <option value="">
                {carregandoFornecedores ? 'Carregando…' : 'Escolha o empreiteiro'}
              </option>
              {fornecedores.map((f) => (
                <option key={f.fornecedor_id} value={f.fornecedor_id}>
                  {f.razao_social}
                </option>
              ))}
            </select>
            {!carregandoFornecedores && fornecedores.length === 0 && (
              <Ajuda>
                Nenhum fornecedor cadastrado ainda — o contrato usa o cadastro da
                casa, em Compras › Fornecedores.
              </Ajuda>
            )}
          </Campo>
          )}
          {lado === 'custo' && pedidos.length > 0 && (
            <Campo rotulo="Pedido de serviço (Suprimentos)">
              <select value={pedido} onChange={(e) => setPedido(e.target.value ? Number(e.target.value) : '')} style={entrada}>
                <option value="">nenhum</option>
                {pedidos
                  .filter((p) => fornecedor === '' || p.fornecedor === fornecedor)
                  .map((p) => (
                    <option key={p.pedido_id} value={p.pedido_id}>
                      #{p.pedido_id} · {p.fornecedor_nome ?? ''}{p.valor_total ? ` · R$ ${Number(p.valor_total).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : ''}
                    </option>
                  ))}
              </select>
              <Ajuda>A empreitada que o Suprimentos contratou: o contrato mede contra ela (pedido × medido × saldo).</Ajuda>
            </Campo>
          )}
          <Campo rotulo="Número do contrato">
            <input value={numero} onChange={(e) => setNumero(e.target.value)} style={entrada} />
            <Ajuda>O número da empresa, o que aparece na pasta e na fatura.</Ajuda>
          </Campo>
        </Linha>

        <Campo rotulo="Objeto">
          <textarea
            value={objeto}
            onChange={(e) => setObjeto(e.target.value)}
            rows={2}
            style={{ ...entrada, resize: 'vertical', fontFamily: 'inherit' }}
          />
        </Campo>

        <Campo rotulo="Como se mede">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {REGIMES.map((r) => (
              <label
                key={r.valor}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer' }}
              >
                <input
                  type="radio"
                  name="regime"
                  checked={regime === r.valor}
                  onChange={() => setRegime(r.valor)}
                  style={{ marginTop: 3 }}
                />
                <span>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{r.rotulo}</span>
                  <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>
                    {r.explica}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </Campo>

        {regime !== 'unitario' && (
          <Linha>
            <Campo rotulo="Valor fechado do contrato">
              <CampoMoeda
                centavos={valorGlobal}
                aoMudar={setValorGlobal}
                aria-label="Valor fechado do contrato"
              />
            </Campo>
            {regime === 'administracao' && (
              <Campo rotulo="Taxa de administração">
                <CampoDecimal valor={taxa} aoMudar={setTaxa} sufixo="%" casas={3} />
                <Ajuda>Só ela é margem do empreiteiro; o resto é reembolso de custo.</Ajuda>
              </Campo>
            )}
          </Linha>
        )}

        <Linha>
          <Campo rotulo="Início da vigência">
            <input
              type="date" value={inicio} onChange={(e) => setInicio(e.target.value)}
              min={minCalendarioISO} max={maxCalendarioISO} style={entrada}
            />
          </Campo>
          <Campo rotulo="Fim previsto (opcional)">
            <input
              type="date" value={fim} onChange={(e) => setFim(e.target.value)}
              min={minCalendarioISO} max={maxCalendarioISO} style={entrada}
            />
          </Campo>
          <Campo rotulo="Prazo de pagamento">
            <CampoInteiro valor={prazoPagamento} aoMudar={setPrazoPagamento} max={999} />
            <Ajuda>Dias entre a aprovação da medição e o vencimento do título.</Ajuda>
          </Campo>
        </Linha>

        <Linha>
          <Campo rotulo="Retenção por medição">
            <CampoDecimal valor={retencao} aoMudar={setRetencao} sufixo="%" casas={3} />
          </Campo>
          {comRetencao && (
            <Campo rotulo="O que é esse dinheiro">
              <select
                value={natureza}
                onChange={(e) => setNatureza(e.target.value as NaturezaRetencao)}
                style={entrada}
              >
                {NATUREZAS.filter((n) => n.valor !== 'nenhuma').map((n) => (
                  <option key={n.valor} value={n.valor}>{n.rotulo}</option>
                ))}
              </select>
            </Campo>
          )}
        </Linha>

        {comRetencao && (
          <Campo rotulo="Quando essa retenção volta ao empreiteiro">
            <textarea
              value={condicao}
              onChange={(e) => setCondicao(e.target.value)}
              rows={2}
              placeholder="Ex.: 12 meses após o recebimento definitivo, sem chamado de garantia"
              style={{ ...entrada, resize: 'vertical', fontFamily: 'inherit' }}
            />
            <Ajuda>
              É esta frase que quem pedir a devolução vai declarar como cumprida.
            </Ajuda>
          </Campo>
        )}

        <Campo rotulo="Reajuste">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={reajustavel} onChange={(e) => setReajustavel(e.target.checked)} />
            <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>Este contrato é reajustado por fórmula paramétrica</span>
          </label>
          {reajustavel && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
              <Linha>
                <Campo rotulo="Data-base">
                  <input type="date" value={dataBase} onChange={(e) => setDataBase(e.target.value)} style={entrada} />
                  <Ajuda>Em regra a data da proposta. O primeiro aniversário conta daqui.</Ajuda>
                </Campo>
                <Campo rotulo="Periodicidade (meses)">
                  <CampoInteiro valor={periodicidade} aoMudar={setPeriodicidade} max={60} />
                </Campo>
                <Campo rotulo="Parcela fixa (a)">
                  <input value={parcelaFixa} onChange={(e) => setParcelaFixa(e.target.value)} style={entrada} />
                  <Ajuda>A parte que não reajusta (0 a 1).</Ajuda>
                </Campo>
              </Linha>
              {parcelas.map((p, i) => (
                <Linha key={i}>
                  <Campo rotulo={i === 0 ? 'Índice' : ' '}>
                    <select value={p.indice} style={entrada}
                      onChange={(e) => setParcelas(parcelas.map((x, j) => j === i ? { ...x, indice: e.target.value ? Number(e.target.value) : '' } : x))}>
                      <option value="">Escolha o índice</option>
                      {indices.map((x) => <option key={x.id} value={x.id}>{x.nome}</option>)}
                    </select>
                  </Campo>
                  <Campo rotulo={i === 0 ? 'Peso (p)' : ' '}>
                    <input value={p.peso} style={entrada}
                      onChange={(e) => setParcelas(parcelas.map((x, j) => j === i ? { ...x, peso: e.target.value } : x))} />
                  </Campo>
                  <Campo rotulo={i === 0 ? 'Rótulo' : ' '}>
                    <input value={p.rotulo} placeholder="mão de obra, materiais…" style={entrada}
                      onChange={(e) => setParcelas(parcelas.map((x, j) => j === i ? { ...x, rotulo: e.target.value } : x))} />
                  </Campo>
                  {parcelas.length > 1 && (
                    <Btn onClick={() => setParcelas(parcelas.filter((_, j) => j !== i))}>Tirar</Btn>
                  )}
                </Linha>
              ))}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Btn onClick={() => setParcelas([...parcelas, { indice: '', peso: '', rotulo: '' }])}>+ Parcela</Btn>
                <span style={{ fontSize: 12, color: fechou ? 'var(--good-ink)' : 'var(--danger-ink)' }}>
                  a + Σp = {somaPesos.toFixed(4)} {fechou ? '✓' : '— precisa somar 1'}
                </span>
              </div>
              {indices.length === 0 && (
                <Ajuda>Nenhum índice publicado na plataforma ainda — o administrador importa a série (INCC, IPCA…).</Ajuda>
              )}
            </div>
          )}
        </Campo>

        <Campo rotulo="Regime">
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 7, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={publico}
              onChange={(e) => setPublico(e.target.checked)}
            />
            <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              Contrato sob regime público
            </span>
          </label>
        </Campo>

        {publico && (
          <Campo rotulo="Limite legal de acréscimo deste contrato">
            <CampoDecimal valor={limite} aoMudar={setLimite} sufixo="%" casas={3} />
            {/* O sistema confere contra o número declarado — escolher 25% ou
                50% por conta própria erraria justamente na exceção. */}
            <Ajuda>
              O sistema confere os aditivos contra este número. Ele varia com a
              lei e com o tipo de obra, então quem cadastra o contrato é quem o
              informa.
            </Ajuda>
          </Campo>
        )}
      </div>
    </Modal>
  )
}

const entrada = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13,
} as const

function Linha({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
      {children}
    </div>
  )
}

function Campo({
  rotulo, larga, children,
}: { rotulo: string; larga?: boolean; children: React.ReactNode }) {
  return (
    <div style={{ flex: larga ? 2 : 1, minWidth: 160 }}>
      <label
        style={{
          display: 'block', fontSize: 10.5, letterSpacing: '0.07em',
          textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
          marginBottom: 5,
        }}
      >
        {rotulo}
      </label>
      {children}
    </div>
  )
}

function Ajuda({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: '5px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
      {children}
    </p>
  )
}
