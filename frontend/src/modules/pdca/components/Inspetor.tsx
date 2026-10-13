import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, X } from 'lucide-react'
import { Btn, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR, maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import { usePdca } from '../contexto'
import {
  useCalendarios, useCriarEtapa, useCriarRestricao, useEtapasDaObra, useGantt,
  useCustoDoPlano, useGerarDemandaDeCompra, useLocais, useNecessidadeDeMaterial, usePlanoCorrente, usePlanoEmEdicao,
  useReabrirRestricao,
  useRemoverRestricao, useRestricoesDaAtividade,
} from '../hooks'
import { TIPOS_QUE_VIRAM_COMPRA } from '../vocabulario'
import {
  buscarFuncionarios, buscarItensOrcados, buscarNoCatalogo, materiaisDaAtividade, plano as planoApi,
  type ItemOrcadoCurto,
} from '../api/montagemApi'
import { pdcaKeys } from '../api/queryKeys'
import { linhasVisiveis } from '../arvore'
import { emPercentual, fatiasDaObra, pesoDe, rateioQueFecha } from '../pesos'
import { mensagemDe, useMontagem, type Montagem } from '../montagem'
import { AndamentoDaCompra } from './AndamentoDaCompra'
import { CampoData } from './CampoData'
import { DialogoDeExclusao } from './DialogosDoPlano'
import type {
  Atividade, PayloadGantt, Precedencia, TipoPrecedencia, TipoRestricao,
} from '../types'

const TIPOS: { valor: TipoPrecedencia; rotulo: string }[] = [
  { valor: 'FS', rotulo: 'termina → começa (FS)' },
  { valor: 'SS', rotulo: 'começa → começa (SS)' },
  { valor: 'FF', rotulo: 'termina → termina (FF)' },
  { valor: 'SF', rotulo: 'começa → termina (SF)' },
]

const TIPOS_DE_RESTRICAO: { valor: TipoRestricao; rotulo: string }[] = [
  { valor: 'material', rotulo: 'Material' },
  { valor: 'projeto', rotulo: 'Projeto' },
  { valor: 'mao_de_obra', rotulo: 'Mão de obra' },
  { valor: 'equipamento', rotulo: 'Equipamento' },
  { valor: 'area', rotulo: 'Área / frente' },
  { valor: 'licenca', rotulo: 'Licença' },
  { valor: 'decisao', rotulo: 'Decisão do cliente' },
  { valor: 'clima', rotulo: 'Clima' },
]

/** O painel que absorve os verbos e o detalhe sem trocar de rota. Em rascunho,
 *  **tudo** da atividade se edita aqui: nome, duração, marco, data mínima,
 *  expediente, local, etapa, item orçado, responsável, peso, observação, a rede
 *  inteira (para trás e para frente, com tipo e defasagem) e as restrições —
 *  material, projeto, licença — que seguram o começo. */
export function Inspetor() {
  const { selecao, selecionar, obraId, planoEscolhido } = usePdca()
  // A versão que o posto Plano mostra (o rascunho em montagem, ou a escolhida);
  // a seleção que vem da Semana ou do Hoje é do vigente — por isso o recuo.
  const emEdicao = usePlanoEmEdicao(obraId, planoEscolhido)
  const corrente = usePlanoCorrente(obraId)
  const { data: ganttEmEdicao } = useGantt(emEdicao.plano?.cronograma_id)
  const { data: ganttCorrente } = useGantt(corrente.plano?.cronograma_id)
  const estaNoCorrente = selecao?.tipo === 'atividade'
    && !ganttEmEdicao?.atividades.some((a) => a.atividade_id === selecao.id)
    && !!ganttCorrente?.atividades.some((a) => a.atividade_id === selecao.id)
  const plano = estaNoCorrente ? corrente.plano : emEdicao.plano
  const gantt = estaNoCorrente ? ganttCorrente : ganttEmEdicao
  // As restrições são do plano em execução: no rascunho, valem as da gêmea
  // vigente (mesmo código EAP), que é para onde elas vão ao publicar.
  const vigente = emEdicao.vigente
  const ganttVigente = vigente?.cronograma_id === corrente.plano?.cronograma_id ? ganttCorrente : undefined
  const lote = useMontagem({
    cronogramaId: plano?.cronograma_id, obraId,
    atividades: gantt?.atividades ?? [], precedencias: gantt?.precedencias ?? [],
  })
  const { hasPermission } = useAuth()

  if (lote.linhasMarcadas.length > 1 && gantt && plano) {
    return (
      <aside aria-label="Detalhe do que está selecionado" style={ESTILO_ASIDE}>
        <CabecalhoDoInspetor rotulo={`${lote.linhasMarcadas.length} linhas marcadas`} aoFechar={lote.limparMarcas} />
        <FaceDoLote
          montagem={lote}
          gantt={gantt}
          obraId={obraId}
          editavel={hasPermission('pdca.cronograma.edit') && plano.editavel}
          obraSegue={plano.status === 'vigente' || !emEdicao.vigente}
        />
      </aside>
    )
  }

  if (!selecao) return null

  const atividade = selecao.tipo === 'atividade'
    ? gantt?.atividades.find((a) => a.atividade_id === selecao.id)
    : undefined

  return (
    <aside aria-label="Detalhe do que está selecionado" style={ESTILO_ASIDE}>
      <CabecalhoDoInspetor
        rotulo={selecao.tipo === 'atividade' ? (atividade?.tem_filhos ? 'Etapa' : 'Atividade') : 'Local'}
        aoFechar={() => selecionar(null)}
      />

      {atividade && gantt && plano
        ? (
          <FaceAtividade
            key={atividade.atividade_id}
            atividade={atividade}
            gantt={gantt}
            obraId={obraId}
            editavelPlano={plano.editavel}
            daExecucao={
              !vigente || plano.cronograma_id === vigente.cronograma_id || plano.status !== 'rascunho'
                ? atividade
                : ganttVigente?.atividades.find((x) => x.codigo === atividade.codigo) ?? null
            }
          />
        )
        : (
          <div style={{ padding: 16, fontSize: 12.5, color: 'var(--ink-3)' }}>
            O item selecionado não está neste plano.
          </div>
        )}
    </aside>
  )
}

const ESTILO_ASIDE = {
  width: 336, flexShrink: 0, borderLeft: '1px solid var(--line)', background: 'var(--surface)',
  overflowY: 'auto', display: 'flex', flexDirection: 'column',
} as const

function CabecalhoDoInspetor({ rotulo, aoFechar }: { rotulo: string; aoFechar: () => void }) {
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 8, padding: '11px 14px', borderBottom: '1px solid var(--line-2)',
        position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 2,
      }}
    >
      <span style={{ fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
        {rotulo}
      </span>
      <button
        type="button"
        onClick={aoFechar}
        aria-label="Fechar detalhe"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', display: 'flex', padding: 2 }}
      >
        <X size={15} />
      </button>
    </div>
  )
}

/** Várias linhas marcadas: o que se faz com o lote de uma vez. Cada campo se
 *  aplica só quando a pessoa pede ("Aplicar"), e o lote inteiro é **um** passo
 *  no Ctrl+Z. */
function FaceDoLote(
  { montagem, gantt, obraId, editavel, obraSegue }:
  { montagem: Montagem; gantt: PayloadGantt; obraId: number; editavel: boolean; obraSegue: boolean },
) {
  const lista = montagem.linhasMarcadas
  const folhas = lista.filter((a) => !a.tem_filhos)
  const { data: locais = [] } = useLocais(obraId, editavel)
  const { data: calendarios = [] } = useCalendarios(obraId, editavel)
  const { data: funcionarios, isError: semRh } = useQuery({
    queryKey: ['pdca', 'funcionarios'], queryFn: buscarFuncionarios, enabled: editavel,
    staleTime: 5 * 60_000, retry: false,
  })
  const [duracao, setDuracao] = useState('')
  const [inicio, setInicio] = useState('')
  const [excluindo, setExcluindo] = useState(false)
  const ligacoesEntre = gantt.precedencias.filter((p) =>
    lista.some((a) => a.atividade_id === p.origem) && lista.some((a) => a.atividade_id === p.destino)).length

  return (
    <div style={{ padding: '14px 14px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: 'var(--ink-2)', maxHeight: 140, overflowY: 'auto' }}>
        {lista.map((a) => (
          <li key={a.atividade_id}><span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{a.codigo}</span> {a.nome}</li>
        ))}
      </ul>

      {montagem.erro && (
        <div style={{ fontSize: 12, color: 'var(--danger-ink)', background: 'var(--danger-soft)', padding: '6px 8px', borderRadius: 'var(--r-sm)' }}>
          {montagem.erro}
        </div>
      )}

      {!editavel ? (
        <Vazio>Plano publicado: para mudar, replaneje.</Vazio>
      ) : (
        <>
          <Bloco titulo="Sequência">
            <Btn tam="sm" onClick={() => montagem.encadear(lista, `encadear ${lista.length} linhas`)}>
              Encadear em sequência (cada uma depois da anterior)
            </Btn>
            <Btn tam="sm" onClick={() => montagem.desligarEntre(lista)} disabled={ligacoesEntre === 0}>
              Desligar entre elas ({ligacoesEntre})
            </Btn>
          </Bloco>

          <Bloco titulo="Estrutura">
            <div style={{ display: 'flex', gap: 6 }}>
              <Btn tam="sm" onClick={() => montagem.recuarVarias(lista)} title="Tab">Recuar</Btn>
              <Btn tam="sm" onClick={() => montagem.avancarVarias(lista)} title="Shift+Tab">Avançar</Btn>
              <Btn tam="sm" variant="perigo" onClick={() => setExcluindo(true)} title="Delete">Excluir</Btn>
            </div>
          </Bloco>

          <Bloco titulo={`Aplicar a todas (${folhas.length} com duração)`}>
            <Campo rotulo="Duração (dias úteis)">
              <span style={{ display: 'inline-flex', gap: 4 }}>
                <input value={duracao} onChange={(e) => setDuracao(e.target.value)} inputMode="numeric" style={{ ...ESTILO_CAMPO, width: 56, textAlign: 'right' }} />
                <Btn
                  tam="sm"
                  disabled={!folhas.length || !(Math.round(Number(duracao)) >= 1)}
                  onClick={() => montagem.salvarVarias(folhas.filter((a) => !a.eh_marco), { duracao_dias: Math.round(Number(duracao)) }, 'duração do lote')}
                >
                  Aplicar
                </Btn>
              </span>
            </Campo>
            <Campo rotulo="Não começar antes de">
              <span style={{ display: 'inline-flex', gap: 4 }}>
                <input type="date" min={minCalendarioISO} max={maxCalendarioISO} value={inicio} onChange={(e) => setInicio(e.target.value)} style={ESTILO_CAMPO} />
                <Btn tam="sm" disabled={!folhas.length} onClick={() => montagem.salvarVarias(folhas, { nao_comecar_antes_de: inicio || null }, 'data do lote')}>
                  {inicio ? 'Aplicar' : 'Soltar'}
                </Btn>
              </span>
            </Campo>
            <Campo rotulo="Local">
              <select
                value=""
                onChange={(e) => e.target.value && montagem.salvarVarias(lista, { local: e.target.value === '-' ? null : Number(e.target.value) }, 'local do lote')}
                style={ESTILO_SELECT}
                aria-label="Local do lote"
              >
                <option value="">escolher…</option>
                <option value="-">sem local</option>
                {locais.map((l) => <option key={l.local_id} value={l.local_id}>{'· '.repeat(Math.max(0, l.profundidade - 1))}{l.nome}</option>)}
              </select>
            </Campo>
            {!semRh && (
              <Campo rotulo="Responsável">
                <select
                  value=""
                  onChange={(e) => e.target.value && montagem.salvarVarias(lista, { responsavel: e.target.value === '-' ? null : Number(e.target.value) }, 'responsável do lote')}
                  style={ESTILO_SELECT}
                  aria-label="Responsável do lote"
                >
                  <option value="">escolher…</option>
                  <option value="-">ninguém</option>
                  {(funcionarios ?? []).map((f) => <option key={f.funcionario_id} value={f.funcionario_id}>{f.nome_completo}</option>)}
                </select>
              </Campo>
            )}
            <Campo rotulo="Expediente">
              <select
                value=""
                onChange={(e) => e.target.value && montagem.salvarVarias(folhas, { calendario: e.target.value === '-' ? null : Number(e.target.value) }, 'expediente do lote')}
                style={ESTILO_SELECT}
                aria-label="Expediente do lote"
              >
                <option value="">escolher…</option>
                <option value="-">
                  {(() => {
                    const nome = calendarios.find((c) => c.calendario_id === gantt.cronograma.calendario)?.nome
                    return nome ? `${nome} (o do plano)` : 'o do plano'
                  })()}
                </option>
                {calendarios.map((c) => <option key={c.calendario_id} value={c.calendario_id}>{c.nome}</option>)}
              </select>
            </Campo>
          </Bloco>
        </>
      )}

      {excluindo && (
        <DialogoDeExclusao
          lista={lista}
          montagem={montagem}
          precedencias={gantt.precedencias}
          restricoesPorAtividade={new Map()}
          obraSegue={obraSegue}
          aoConfirmar={() => { setExcluindo(false); void montagem.excluirVarias(lista) }}
          aoFechar={() => setExcluindo(false)}
        />
      )}
    </div>
  )
}

function FaceAtividade(
  { atividade, gantt, obraId, editavelPlano, daExecucao }: {
    atividade: Atividade; gantt: PayloadGantt; obraId: number; editavelPlano: boolean
    /** A atividade do plano **em execução** que responde pelas restrições:
     *  ela mesma, ou — no rascunho — a gêmea vigente. `null` = linha nova do
     *  rascunho, sem gêmea ainda. */
    daExecucao: Atividade | null
  },
) {
  const { hasPermission } = useAuth()
  const editavel = hasPermission('pdca.cronograma.edit') && editavelPlano
  const montagem = useMontagem({
    cronogramaId: atividade.cronograma, obraId,
    atividades: gantt.atividades, precedencias: gantt.precedencias,
  })
  const avanco = gantt.avanco.por_atividade[String(atividade.atividade_id)]
  const naBase = gantt.base.linhas.find((l) => l.codigo === atividade.codigo)
  const folha = !atividade.tem_filhos
  const a = atividade

  return (
    <div style={{ padding: '14px 14px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)' }}>{a.codigo}</div>
        {editavel ? (
          <CampoTexto
            valor={a.nome}
            aoGravar={(v) => montagem.salvar(a, { nome: v }, 'renomear')}
            estilo={{ fontSize: 15, fontWeight: 700, marginTop: 2 }}
            rotulo="Nome"
          />
        ) : (
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.3, marginTop: 2 }}>{a.nome}</div>
        )}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {a.critica && <Pill kind="danger">Caminho crítico</Pill>}
          {a.eh_marco && <Pill kind="info">Marco</Pill>}
          {a.tem_filhos && <Pill kind="slate">Etapa (agrupa)</Pill>}
          {a.nao_comecar_antes_de && <Pill kind="info">Data fixada</Pill>}
        </div>
      </div>

      {montagem.erro && (
        <div style={{ fontSize: 12, color: 'var(--danger-ink)', background: 'var(--danger-soft)', padding: '6px 8px', borderRadius: 'var(--r-sm)' }}>
          {montagem.erro}
        </div>
      )}

      <Bloco titulo="Prazo">
        {folha && editavel ? (
          <>
            <Campo rotulo="Marco (instante, sem duração)">
              <input
                type="checkbox"
                checked={a.eh_marco}
                onChange={(e) => montagem.salvar(a, e.target.checked
                  ? { eh_marco: true, duracao_dias: null }
                  : { eh_marco: false, duracao_dias: 1 }, 'marco')}
              />
            </Campo>
            {!a.eh_marco && (
              <Campo rotulo="Duração (dias úteis)">
                <CampoTexto
                  valor={String(a.duracao_dias ?? '')}
                  numerico
                  aoGravar={(v) => {
                    const n = Math.round(Number(v.replace(',', '.')))
                    if (Number.isFinite(n) && n >= 1) return montagem.salvar(a, { duracao_dias: n }, 'duração')
                    montagem.avisar('A duração precisa ser de ao menos 1 dia útil.')
                  }}
                  rotulo="Duração"
                />
              </Campo>
            )}
            <Campo rotulo="Não começar antes de">
              <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                <CampoData
                  valor={a.nao_comecar_antes_de}
                  rotulo="Não começar antes de"
                  aoGravar={(iso) => montagem.salvar(a, { nao_comecar_antes_de: iso }, 'data mínima')}
                  estilo={ESTILO_CAMPO}
                />
                {a.nao_comecar_antes_de && (
                  <button type="button" title="Soltar a data" aria-label="Soltar a data" onClick={() => montagem.salvar(a, { nao_comecar_antes_de: null }, 'data mínima')} style={BOTAO_X}>×</button>
                )}
              </span>
            </Campo>
          </>
        ) : (
          <>
            <Linha rotulo="Duração" valor={a.eh_marco ? 'marco' : folha ? `${a.duracao_dias} d` : 'o intervalo das filhas'} />
            {a.nao_comecar_antes_de && <Linha rotulo="Não começa antes de" valor={data(a.nao_comecar_antes_de)} />}
          </>
        )}
        <Linha rotulo="Início" valor={data(a.inicio_cedo)} />
        <Linha rotulo="Término" valor={data(a.termino_cedo)} />
        <Linha
          rotulo="Folga total"
          valor={a.folga_total == null ? semApuracao('o plano ainda não foi calculado') : `${a.folga_total} d`}
          tom={a.folga_total === 0 ? 'var(--danger-ink)' : undefined}
        />
        {folha && (
          <SeletorDeExpediente
            atividade={a} obraId={obraId} montagem={montagem} editavel={editavel}
            doPlano={gantt.cronograma.calendario}
          />
        )}
      </Bloco>

      {naBase && naBase.base_termino && (
        <Bloco titulo="Contra o combinado">
          <Linha rotulo="Término na base" valor={data(naBase.base_termino)} />
          <Linha
            rotulo="Desvio"
            valor={naBase.desvio_dias == null ? '—' : `${naBase.desvio_dias > 0 ? '+' : ''}${naBase.desvio_dias} d`}
            tom={naBase.desvio_dias == null || naBase.desvio_dias === 0
              ? undefined
              : (naBase.desvio_dias > 0 ? 'var(--danger-ink)' : 'var(--good-ink)')}
          />
        </Bloco>
      )}

      <Rede atividade={a} gantt={gantt} montagem={montagem} editavel={editavel} />

      {daExecucao ? (
        <Restricoes
          atividade={daExecucao} obraId={obraId} montagem={montagem}
          editavelPlano={editavel && daExecucao.atividade_id === a.atividade_id}
          doVigente={daExecucao.atividade_id !== a.atividade_id}
        />
      ) : folha && (
        <Bloco titulo="Restrições (material, projeto, licença…)">
          <Vazio>Linha nova deste rascunho: as restrições se registram no plano em execução — depois de publicar.</Vazio>
        </Bloco>
      )}

      {folha && !a.eh_marco && <MaterialDaAtividade atividade={a} montagem={montagem} editavel={editavel} />}

      <Bloco titulo="Avanço físico e peso">
        <div style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          O <strong>executado</strong> vem dos apontamentos do campo (posto Hoje). O <strong>peso</strong> diz
          quanto esta atividade conta no avanço físico da etapa e da obra — a média ponderada que aparece no
          pulso da obra, no posto Hoje. Ligada a um item orçado, o peso é o custo dele; sem item, informe aqui.
          Atividade sem peso fica fora da conta.
        </div>
        <Linha
          rotulo="Executado"
          valor={avanco?.avanco == null
            ? semApuracao('ninguém apontou avanço nesta atividade')
            : `${avanco.avanco.toFixed(2).replace('.', ',')} %`}
        />
        <Linha rotulo="Lançamentos" valor={String(avanco?.lancamentos ?? 0)} />
        {folha && editavel && a.peso_origem !== 'orcado' ? (
          <Campo rotulo="Peso informado">
            <CampoTexto
              valor={a.peso_informado ?? ''}
              numerico
              aoGravar={(v) => montagem.salvar(a, { peso_informado: v ? v.replace(',', '.') : null }, 'peso')}
              rotulo="Peso"
            />
          </Campo>
        ) : folha && (
          <Linha
            rotulo="Peso"
            valor={a.peso == null ? '—' : a.peso}
            nota={a.peso_origem === 'orcado' ? 'vem do item orçado' : a.peso_origem === 'informado' ? 'informado' : undefined}
          />
        )}
        {folha && <Participacao atividade={a} gantt={gantt} />}
        {!folha && <ComposicaoDoPeso etapa={a} gantt={gantt} montagem={montagem} editavel={editavel} />}
      </Bloco>

      <Bloco titulo="Onde isto conversa">
        <SeletorDeLocal atividade={a} obraId={obraId} montagem={montagem} editavel={editavel} />
        {editavel ? (
          <SeletorDeEtapa atividade={a} obraId={obraId} montagem={montagem} />
        ) : a.etapa_nome && <Linha rotulo="Etapa da obra" valor={a.etapa_nome} />}
        {folha && <SeletorDeItemOrcado atividade={a} obraId={obraId} montagem={montagem} editavel={editavel} />}
        <SeletorDeResponsavel atividade={a} montagem={montagem} editavel={editavel} />
        {editavel ? (
          <Campo rotulo="Observação" coluna>
            <CampoTexto
              valor={a.observacao ?? ''}
              aoGravar={(v) => montagem.salvar(a, { observacao: v }, 'observação')}
              rotulo="Observação"
              multilinha
            />
          </Campo>
        ) : a.observacao ? <Linha rotulo="Observação" valor={a.observacao} /> : null}
      </Bloco>
    </div>
  )
}

/* -- Material: o que a atividade consome e quando chega ------------------- */

const SITUACAO: Record<string, { rotulo: string; tom: 'good' | 'accent' | 'danger' }> = {
  coberta: { rotulo: 'coberto', tom: 'good' },
  comprar: { rotulo: 'comprar', tom: 'accent' },
  atrasada: { rotulo: 'pedido atrasado', tom: 'danger' },
}

/** O pedaço da fila de suprimentos desta atividade — a integração visível
 *  entre o plano, o orçamento, o estoque e as compras. */
function MaterialDaAtividade(
  { atividade, montagem, editavel }: { atividade: Atividade; montagem: Montagem; editavel: boolean },
) {
  const { data } = useNecessidadeDeMaterial(atividade.cronograma)
  const minhas = (data?.linhas ?? []).filter((l) => l.atividade === atividade.atividade_id)
  return (
    <Bloco titulo="Material">
      {minhas.length === 0 && (
        <Vazio>
          {atividade.item_orcado
            ? 'O item orçado não tem material explodido (ou já foi todo executado).'
            : 'Informe o material abaixo, ou ligue ao orçamento — os dois entram na fila de compras.'}
        </Vazio>
      )}
      {minhas.map((l) => (
        <div key={l.insumo} style={{ display: 'flex', gap: 6, alignItems: 'baseline', fontSize: 12 }}>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={l.descricao}>
            {l.descricao}
          </span>
          <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
            {Number(l.restante).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} {l.unidade}
          </span>
          <Pill kind={SITUACAO[l.situacao].tom}>{SITUACAO[l.situacao].rotulo}</Pill>
        </div>
      ))}
      {minhas.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
          chegar até {dateToBR(minhas[0].chegar_ate)} ({minhas[0].antecedencia_dias} d antes do início) ·{' '}
          <Link to={`/app/pdca/o/${data?.obra ?? ''}/plano?vista=suprimentos`} style={{ color: 'var(--brand)' }}>ver a fila de compras</Link>
        </div>
      )}
      <MaterialInformado atividade={atividade} />
      <CustoDaAtividadeNoPlano atividade={atividade} />
      {editavel ? (
        <Campo rotulo="Chegar quantos dias antes">
          <CampoTexto
            valor={atividade.antecedencia_compra_dias == null ? '' : String(atividade.antecedencia_compra_dias)}
            numerico
            largura={56}
            rotulo="Antecedência de compra desta atividade (dias)"
            aoGravar={(v) => {
              const n = v === '' ? null : Math.round(Number(v))
              if (n == null || (Number.isFinite(n) && n >= 0)) return montagem.salvar(atividade, { antecedencia_compra_dias: n }, 'antecedência de compra')
            }}
          />
        </Campo>
      ) : atividade.antecedencia_compra_dias != null && (
        <Linha rotulo="Chegar antes" valor={`${atividade.antecedencia_compra_dias} d`} />
      )}
    </Bloco>
  )
}

/** **O material informado na atividade** — a compra sem orçamento (pergunta
 *  do dono, 10/10/2026: "se eu não tiver orçamento, não posso fazer pedido?").
 *  Entra na fila de compras como o do orçamento. Escolher do catálogo deixa o
 *  estoque e os pedidos abaterem; o texto sozinho também serve para pedir. */
function MaterialInformado({ atividade }: { atividade: Atividade }) {
  const { hasPermission } = useAuth()
  const pode = hasPermission('pdca.cronograma.edit')
  const qc = useQueryClient()
  const chave = ['pdca', 'materiais-atividade', atividade.atividade_id]
  const { data: lista = [] } = useQuery({ queryKey: chave, queryFn: () => materiaisDaAtividade.listar(atividade.atividade_id) })
  const [abrindo, setAbrindo] = useState(false)
  const [descricao, setDescricao] = useState('')
  const [item, setItem] = useState<{ id: number; unidade: string } | null>(null)
  const [unidade, setUnidade] = useState('')
  const [quantidade, setQuantidade] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const sugestoes = useQuery({
    queryKey: ['pdca', 'catalogo', descricao.trim()],
    queryFn: () => buscarNoCatalogo(descricao.trim()),
    enabled: abrindo && descricao.trim().length >= 2 && item == null,
    staleTime: 60_000,
  })

  async function atualizar() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: chave }),
      qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.suprimentos(atividade.cronograma) }),
    ])
  }
  async function incluir() {
    setErro(null)
    try {
      await materiaisDaAtividade.criar({
        atividade: atividade.atividade_id, item: item?.id ?? null, descricao: descricao.trim(),
        unidade: unidade.trim(), quantidade: quantidade.replace(',', '.'),
      })
      setDescricao(''); setItem(null); setUnidade(''); setQuantidade(''); setAbrindo(false)
      await atualizar()
    } catch (e) {
      setErro(mensagemDe(e))
    }
  }

  const campo = {
    fontSize: 12, padding: '4px 7px', background: 'var(--surface)', color: 'var(--ink)',
    border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', minWidth: 0,
  } as const
  if (!pode && lista.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, borderTop: '1px dashed var(--line-2)', paddingTop: 6 }}>
      <Subtitulo>Informado na atividade</Subtitulo>
      {lista.map((m) => (
        <div key={m.material_id} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.descricao}>
            {m.descricao}
          </span>
          <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
            {Number(m.quantidade).toLocaleString('pt-BR', { maximumFractionDigits: 3 })} {m.unidade}
          </span>
          {pode && (
            <button
              type="button" aria-label={`Tirar ${m.descricao}`}
              onClick={async () => { await materiaisDaAtividade.remover(m.material_id); await atualizar() }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', display: 'flex', padding: 0 }}
            >
              <X size={12} />
            </button>
          )}
        </div>
      ))}
      {pode && !abrindo && (
        <button type="button" onClick={() => setAbrindo(true)} style={{ ...LINK_DO_BLOCO }}>+ Informar material</button>
      )}
      {pode && abrindo && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <input
            autoFocus value={descricao} placeholder="Material (procure no catálogo ou escreva)"
            aria-label="Material"
            onChange={(e) => { setDescricao(e.target.value); setItem(null) }}
            style={campo}
          />
          {item == null && (sugestoes.data ?? []).length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', maxHeight: 140, overflowY: 'auto' }}>
              {(sugestoes.data ?? []).map((s) => (
                <button
                  key={s.item_id} type="button"
                  onClick={() => { setDescricao(s.descricao); setItem({ id: s.item_id, unidade: s.unidade }); setUnidade(s.unidade) }}
                  style={{ textAlign: 'left', background: 'var(--surface)', border: 'none', borderBottom: '1px solid var(--line-2)', padding: '4px 7px', fontSize: 11.5, cursor: 'pointer', color: 'var(--ink-2)' }}
                >
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{s.codigo_interno}</span> {s.descricao} · {s.unidade}
                </button>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 5 }}>
            <input value={quantidade} inputMode="decimal" placeholder="Quantidade" aria-label="Quantidade" onChange={(e) => setQuantidade(e.target.value)} style={{ ...campo, flex: 1 }} />
            <input value={unidade} placeholder="un" aria-label="Unidade" onChange={(e) => setUnidade(e.target.value)} style={{ ...campo, width: 56 }} />
          </div>
          {erro && <span style={{ fontSize: 11.5, color: 'var(--danger-ink)' }}>{erro}</span>}
          <div style={{ display: 'flex', gap: 5 }}>
            <Btn tam="sm" variant="primary" disabled={!descricao.trim() || !quantidade.trim()} onClick={() => void incluir()}>Incluir</Btn>
            <Btn tam="sm" onClick={() => { setAbrindo(false); setErro(null) }}>Cancelar</Btn>
          </div>
        </div>
      )}
    </div>
  )
}

const LINK_DO_BLOCO = {
  background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left',
  color: 'var(--brand)', fontSize: 12, fontWeight: 600,
} as const

/** O dinheiro da atividade nos quatro módulos (pedido e recebido rateados). */
function CustoDaAtividadeNoPlano({ atividade }: { atividade: Atividade }) {
  const { data } = useCustoDoPlano(atividade.cronograma)
  const minha = data?.etapas.flatMap((e) => e.atividades).find((x) => x.atividade === atividade.atividade_id)
  if (!minha || Number(minha.orcado) + Number(minha.comprometido) + Number(minha.medido) === 0) return null
  const r = (v: string) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, borderTop: '1px dashed var(--line-2)', paddingTop: 6 }}>
      <Subtitulo>Custo</Subtitulo>
      <Linha rotulo="Orçado" valor={r(minha.orcado)} />
      <Linha rotulo="Comprometido (pedidos)" valor={r(minha.comprometido)} nota="rateado pelo consumo do insumo" />
      <Linha rotulo="Recebido" valor={r(minha.recebido)} />
      {Number(minha.medido) > 0 && <Linha rotulo="Medido (empreiteiro)" valor={r(minha.medido)} />}
    </div>
  )
}

/* -- Peso: a parcela da folha e a composição da etapa ---------------------- */

/** Quanto esta folha conta: na etapa (o pai) e na obra. */
function Participacao({ atividade, gantt }: { atividade: Atividade; gantt: PayloadGantt }) {
  const peso = pesoDe(gantt.avanco, atividade.atividade_id)
  if (peso == null) return null
  const daObra = fatiasDaObra(gantt.avanco, gantt.atividades).get(atividade.atividade_id) ?? null
  const daEtapa = atividade.pai != null ? naEtapa(gantt, atividade.pai).get(atividade.atividade_id) ?? null : null
  return (
    <Linha
      rotulo="Participação"
      valor={[daEtapa != null ? `${emPercentual(daEtapa)} da etapa` : null, `${emPercentual(daObra)} da obra`].filter(Boolean).join(' · ')}
    />
  )
}

/** A parcela de cada filha **na etapa**, repartida para fechar 100%. */
function naEtapa(gantt: PayloadGantt, etapaId: number): Map<number, number> {
  const filhas = gantt.atividades.filter((x) => x.pai === etapaId)
  const partes = rateioQueFecha(filhas.map((f) => pesoDe(gantt.avanco, f.atividade_id)))
  const mapa = new Map<number, number>()
  filhas.forEach((f, i) => { const u = partes[i]; if (u != null) mapa.set(f.atividade_id, u / 10) })
  return mapa
}

/** A etapa vale **a soma das filhas** — e é aqui que se compõe: o peso de
 *  cada filha, a parcela dela na etapa, e a da etapa na obra. As filhas sem
 *  item orçado se pesam aqui mesmo, sem abrir uma por uma. */
function ComposicaoDoPeso(
  { etapa, gantt, montagem, editavel }: { etapa: Atividade; gantt: PayloadGantt; montagem: Montagem; editavel: boolean },
) {
  const filhas = gantt.atividades
    .filter((x) => x.pai === etapa.atividade_id)
    .sort((x, y) => (x.ordem - y.ordem) || x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true }))
  const total = pesoDe(gantt.avanco, etapa.atividade_id)
  const daObra = fatiasDaObra(gantt.avanco, gantt.atividades).get(etapa.atividade_id) ?? null
  const fatias = naEtapa(gantt, etapa.atividade_id)
  const semPeso = filhas.filter((f) => pesoDe(gantt.avanco, f.atividade_id) == null).length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <Subtitulo>Composição do peso</Subtitulo>
      <div style={{ display: 'flex', gap: 5, fontSize: 10, color: 'var(--ink-3)', fontWeight: 650 }} aria-hidden>
        <span style={{ flex: 1 }}>Filha</span>
        <span style={{ width: 54, textAlign: 'right' }}>Peso</span>
        <span style={{ width: 46, textAlign: 'right' }}>% etapa</span>
      </div>
      {filhas.map((f) => {
        const peso = pesoDe(gantt.avanco, f.atividade_id)
        const podeDigitar = editavel && !f.tem_filhos && f.peso_origem !== 'orcado'
        return (
          <div key={f.atividade_id} style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
            <span title={f.nome} style={{ flex: 1, minWidth: 0, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{f.codigo}</span> {f.nome}
            </span>
            {podeDigitar ? (
              <CampoTexto
                valor={f.peso_informado ?? ''}
                numerico
                largura={54}
                rotulo={`Peso de ${f.nome}`}
                aoGravar={(v) => montagem.salvar(f, { peso_informado: v ? v.replace(',', '.') : null }, 'peso')}
              />
            ) : (
              <span
                style={{ width: 54, textAlign: 'right', fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}
                title={f.peso_origem === 'orcado' ? 'Vem do item orçado' : f.tem_filhos ? 'Soma das filhas dela' : undefined}
              >
                {peso == null ? '—' : peso.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
              </span>
            )}
            <span style={{ width: 46, textAlign: 'right', fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)' }}>
              {emPercentual(fatias.get(f.atividade_id))}
            </span>
          </div>
        )
      })}
      {fatias.size > 0 && (
        <div style={{ display: 'flex', gap: 5, borderTop: '1px solid var(--line-2)', paddingTop: 4, fontSize: 11.5, color: 'var(--ink-2)', fontWeight: 650 }}>
          <span style={{ flex: 1 }}>Total</span>
          <span style={{ width: 54, textAlign: 'right', fontFamily: 'var(--mono)' }}>
            {total == null ? '—' : total.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
          </span>
          <span style={{ width: 46, textAlign: 'right', fontFamily: 'var(--mono)' }}>100%</span>
        </div>
      )}
      <Linha
        rotulo="Peso da etapa"
        valor={total == null ? '—' : total.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
        nota={`soma das filhas${daObra != null ? ` · ${emPercentual(daObra)} da obra` : ''}${semPeso ? ` · ${semPeso} sem peso, fora da conta` : ''}`}
      />
    </div>
  )
}

/* -- Rede: o que segura esta atividade e o que ela libera ----------------- */

function Rede(
  { atividade, gantt, montagem, editavel }:
  { atividade: Atividade; gantt: PayloadGantt; montagem: Montagem; editavel: boolean },
) {
  const porId = useMemo(() => new Map(gantt.atividades.map((a) => [a.atividade_id, a])), [gantt.atividades])
  // Na ordem da grade (a árvore), não na do código: "1.10" não vem antes de "1.2",
  // e a etapa vem antes das filhas.
  const posicao = useMemo(
    () => new Map(linhasVisiveis(gantt.atividades, new Set()).map((l, i) => [l.atividade.atividade_id, i])),
    [gantt.atividades],
  )
  const naOrdem = (id: number) => posicao.get(id) ?? Number.MAX_SAFE_INTEGER
  const antes = gantt.precedencias
    .filter((p) => p.destino === atividade.atividade_id)
    .sort((x, y) => naOrdem(x.origem) - naOrdem(y.origem))
  const depois = gantt.precedencias
    .filter((p) => p.origem === atividade.atividade_id)
    .sort((x, y) => naOrdem(x.destino) - naOrdem(y.destino))

  // Não se liga a si, nem ao que está dentro ou acima (etapa ↔ o que ela contém).
  const parentes = useMemo(() => {
    const s = new Set<number>([atividade.atividade_id])
    let p = atividade.pai
    while (p != null) { s.add(p); p = porId.get(p)?.pai ?? null }
    const descer = (id: number) => gantt.atividades.filter((x) => x.pai === id).forEach((f) => { s.add(f.atividade_id); descer(f.atividade_id) })
    descer(atividade.atividade_id)
    return s
  }, [atividade, gantt.atividades, porId])
  const opcoes = gantt.atividades
    .filter((x) => !parentes.has(x.atividade_id))
    .sort((x, y) => naOrdem(x.atividade_id) - naOrdem(y.atividade_id))

  return (
    <Bloco titulo={atividade.tem_filhos ? 'Dependências da fase' : 'Dependências'}>
      {editavel && (antes.length > 0 || depois.length > 0) && (
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          <strong>Tipo</strong>: FS termina → começa · SS começa → começa · FF termina → termina · SF começa → termina.{' '}
          <strong>Defasagem</strong>: dias úteis de espera entre as duas (negativo antecipa).
        </div>
      )}
      <Subtitulo>Depende de</Subtitulo>
      {antes.length === 0 && <Vazio>começa no início do plano (ou na data fixada)</Vazio>}
      {editavel && antes.length > 0 && <CabecalhoDeLigacoes />}
      {antes.map((p) => (
        <LinhaDeLigacao key={p.precedencia_id} p={p} outra={porId.get(p.origem)} montagem={montagem} editavel={editavel} />
      ))}
      {editavel && (
        <NovaLigacao
          opcoes={opcoes.filter((x) => !antes.some((p) => p.origem === x.atividade_id))}
          rotulo="+ Depende de…"
          aoLigar={(outra, tipo, atraso) => montagem.ligar(outra, atividade.atividade_id, tipo, atraso)}
        />
      )}
      <Subtitulo>Libera</Subtitulo>
      {depois.length === 0 && <Vazio>nada espera por ela</Vazio>}
      {editavel && depois.length > 0 && <CabecalhoDeLigacoes />}
      {depois.map((p) => (
        <LinhaDeLigacao key={p.precedencia_id} p={p} outra={porId.get(p.destino)} montagem={montagem} editavel={editavel} />
      ))}
      {editavel && (
        <NovaLigacao
          opcoes={opcoes.filter((x) => !depois.some((p) => p.destino === x.atividade_id))}
          rotulo="+ Libera…"
          aoLigar={(outra, tipo, atraso) => montagem.ligar(atividade.atividade_id, outra, tipo, atraso)}
        />
      )}
    </Bloco>
  )
}

/** Os rótulos das colunas da linha de ligação — mesmas larguras dela. */
function CabecalhoDeLigacoes() {
  const rotulo = { fontSize: 10, color: 'var(--ink-3)', fontWeight: 650, letterSpacing: '0.04em' } as const
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }} aria-hidden>
      <span style={{ ...rotulo, flex: 1 }}>Atividade</span>
      <span style={{ ...rotulo, width: 56 }} title="Como as duas se ligam">Tipo</span>
      <span style={{ ...rotulo, width: 42, textAlign: 'right' }} title="Dias úteis de espera (negativo antecipa)">Defas. (d)</span>
      <span style={{ width: 22 }} />
    </div>
  )
}

function LinhaDeLigacao(
  { p, outra, montagem, editavel }:
  { p: Precedencia; outra: Atividade | undefined; montagem: Montagem; editavel: boolean },
) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span title={outra?.nome} style={{ flex: 1, minWidth: 0, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{outra?.codigo}</span> {outra?.nome}
      </span>
      {editavel ? (
        <>
          <select
            value={p.tipo}
            aria-label="Tipo da ligação"
            onChange={(e) => montagem.alterarLigacao(p, { tipo: e.target.value as TipoPrecedencia })}
            style={{ ...ESTILO_CAMPO, width: 56 }}
          >
            {TIPOS.map((t) => <option key={t.valor} value={t.valor} title={t.rotulo}>{t.valor}</option>)}
          </select>
          <CampoTexto
            valor={String(p.atraso_dias)}
            numerico
            largura={42}
            rotulo="Defasagem em dias (negativo antecipa)"
            aoGravar={(v) => {
              const n = Math.round(Number(v.replace(',', '.')))
              if (Number.isFinite(n)) return montagem.alterarLigacao(p, { atraso_dias: n })
            }}
          />
          <button type="button" title="Desligar" aria-label="Desligar" onClick={() => montagem.desligar(p)} style={BOTAO_X}>×</button>
        </>
      ) : (
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-2)' }}>
          {p.tipo}{p.atraso_dias ? `${p.atraso_dias > 0 ? '+' : ''}${p.atraso_dias}d` : ''}
        </span>
      )}
    </div>
  )
}

function NovaLigacao(
  { opcoes, rotulo, aoLigar }:
  { opcoes: Atividade[]; rotulo: string; aoLigar: (outra: number, tipo: TipoPrecedencia, atraso: number) => unknown },
) {
  const [outra, setOutra] = useState('')
  const [tipo, setTipo] = useState<TipoPrecedencia>('FS')
  const [atraso, setAtraso] = useState('0')
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      <select value={outra} onChange={(e) => setOutra(e.target.value)} aria-label={rotulo} style={{ ...ESTILO_CAMPO, flex: 1, minWidth: 0 }}>
        <option value="">{rotulo}</option>
        {opcoes.map((x) => (
          <option key={x.atividade_id} value={x.atividade_id}>{x.codigo} · {x.nome}{x.tem_filhos ? ' (etapa)' : ''}</option>
        ))}
      </select>
      {outra && (
        <>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoPrecedencia)} aria-label="Tipo" style={{ ...ESTILO_CAMPO, width: 56 }}>
            {TIPOS.map((t) => <option key={t.valor} value={t.valor} title={t.rotulo}>{t.valor}</option>)}
          </select>
          <input value={atraso} onChange={(e) => setAtraso(e.target.value)} aria-label="Defasagem (dias)" title="Defasagem em dias (negativo antecipa)" style={{ ...ESTILO_CAMPO, width: 40, textAlign: 'right' }} />
          <Btn
            tam="sm"
            variant="primary"
            onClick={async () => {
              await aoLigar(Number(outra), tipo, Math.round(Number(atraso.replace(',', '.')) || 0))
              setOutra(''); setAtraso('0'); setTipo('FS')
            }}
          >
            Ligar
          </Btn>
        </>
      )}
    </div>
  )
}

/* -- Restrições: o que segura o começo (material, projeto, licença…) ------ */

function Restricoes(
  { atividade, obraId, montagem, editavelPlano, doVigente = false }: {
    atividade: Atividade; obraId: number; montagem: Montagem; editavelPlano: boolean
    /** Mostradas a partir do rascunho: são as da gêmea no plano vigente. */
    doVigente?: boolean
  },
) {
  const { hasPermission } = useAuth()
  const { data: todas = [] } = useRestricoesDaAtividade(atividade.atividade_id)
  const criar = useCriarRestricao(obraId)
  const remover = useRemoverRestricao(obraId)
  const reabrir = useReabrirRestricao(obraId)
  const gerarCompra = useGerarDemandaDeCompra(obraId)
  // Abertas primeiro; as resolvidas ficam embaixo, com a nota, para voltar atrás.
  const abertas = todas.filter((r) => r.status === 'aberta')
  const resolvidas = todas.filter((r) => r.status === 'removida')
  const podeRegistrar = hasPermission('pdca.restricao.edit')
  const podeRemover = hasPermission('pdca.restricao.remover')
  const podeComprar = podeRegistrar && hasPermission('scm.demanda.edit')
  const [novo, setNovo] = useState<{ tipo: TipoRestricao; descricao: string; prazo: string; responsavel: string; segurar: boolean } | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [resolvendo, setResolvendo] = useState<{ id: number; nota: string } | null>(null)

  if (atividade.tem_filhos && todas.length === 0) return null

  async function agir(acao: () => Promise<unknown>) {
    setErro(null)
    try { await acao() } catch (e) { setErro(mensagemDe(e)) }
  }

  async function registrar() {
    if (!novo || !novo.descricao.trim()) return
    setErro(null)
    try {
      await criar.mutateAsync({
        atividade: atividade.atividade_id, tipo: novo.tipo, descricao: novo.descricao.trim(),
        prazo: novo.prazo || null, responsavel: novo.responsavel.trim(),
      })
      if (novo.segurar && novo.prazo && editavelPlano) {
        await montagem.salvar(atividade, { nao_comecar_antes_de: novo.prazo }, 'segurar até a chegada')
      }
      setNovo(null)
    } catch (e) {
      setErro(mensagemDe(e))
    }
  }

  return (
    <Bloco titulo="Restrições (material, projeto, licença…)">
      {doVigente && (
        <div style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          Valem para o plano em execução (a mesma atividade no vigente) e passam para esta versão ao publicar.
        </div>
      )}
      {abertas.length === 0 && <Vazio>nada impede o começo</Vazio>}
      {abertas.map((r) => (
        <div key={r.restricao_id} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '6px 8px', background: 'var(--inset)', borderRadius: 'var(--r-sm)' }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
            <Pill kind={TIPOS_QUE_VIRAM_COMPRA.has(r.tipo) ? 'accent' : 'slate'}>{r.tipo_rotulo}</Pill>
            <span style={{ fontSize: 12, flex: 1 }}>{r.descricao}</span>
          </div>
          <div style={{ fontSize: 11, color: r.dias_para_o_prazo != null && r.dias_para_o_prazo < 0 ? 'var(--danger-ink)' : 'var(--ink-3)' }}>
            {r.prazo ? `até ${dateToBR(r.prazo)}` : 'sem prazo'}
            {r.responsavel ? ` · ${r.responsavel}` : ''}
            {r.vezes_reaberta > 0 ? ` · voltou ${r.vezes_reaberta === 1 ? '1 vez' : `${r.vezes_reaberta} vezes`}` : ''}
          </div>
          {r.compra && (
            <AndamentoDaCompra
              compra={r.compra}
              ocupado={remover.isPending}
              aoDestravar={podeRemover ? (nota) => void agir(() => remover.mutateAsync({ id: r.restricao_id, nota })) : undefined}
            />
          )}
          <div style={{ display: 'flex', gap: 6 }}>
            {TIPOS_QUE_VIRAM_COMPRA.has(r.tipo) && !r.demanda_scm && podeComprar && (
              <Btn
                tam="sm"
                onClick={() => agir(() => gerarCompra.mutateAsync({ id: r.restricao_id }))}
                disabled={gerarCompra.isPending}
                title={r.tipo === 'material' ? 'Abre a demanda de compra no Suprimentos' : 'Abre a contratação (locação / empreitada) no Suprimentos'}
              >
                {r.tipo === 'material' ? 'Pedir compra' : 'Pedir contratação'}
              </Btn>
            )}
            {podeRemover && resolvendo?.id !== r.restricao_id && (
              <Btn tam="sm" onClick={() => setResolvendo({ id: r.restricao_id, nota: '' })}>Resolvida</Btn>
            )}
          </div>
          {resolvendo?.id === r.restricao_id && (
            <div style={{ display: 'flex', gap: 5 }}>
              <input
                autoFocus
                value={resolvendo.nota}
                onChange={(e) => setResolvendo({ ...resolvendo, nota: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Escape') setResolvendo(null) }}
                placeholder="Como foi resolvida? (fica no histórico)"
                style={{ ...ESTILO_CAMPO, flex: 1 }}
              />
              <Btn
                tam="sm"
                variant="primary"
                disabled={resolvendo.nota.trim().length < 3 || remover.isPending}
                onClick={() => { void agir(() => remover.mutateAsync({ id: r.restricao_id, nota: resolvendo.nota.trim() })); setResolvendo(null) }}
              >
                Guardar
              </Btn>
            </div>
          )}
        </div>
      ))}
      {resolvidas.length > 0 && (
        <>
          <Subtitulo>Resolvidas ({resolvidas.length})</Subtitulo>
          {resolvidas.map((r) => (
            <div key={r.restricao_id} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '6px 8px', border: '1px dashed var(--line)', borderRadius: 'var(--r-sm)' }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                <Pill kind="good">✓ {r.tipo_rotulo}</Pill>
                <span style={{ fontSize: 12, flex: 1, color: 'var(--ink-3)', textDecoration: 'line-through' }}>{r.descricao}</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                resolvida{r.removida_em ? ` em ${dateToBR(r.removida_em.slice(0, 10))}` : ''}
                {r.removida_por ? ` por ${r.removida_por}` : ''}
                {r.nota_remocao ? ` — ${r.nota_remocao}` : ''}
              </div>
              {podeRemover && (
                <div>
                  <Btn
                    tam="sm"
                    onClick={() => agir(() => reabrir.mutateAsync(r.restricao_id))}
                    disabled={reabrir.isPending}
                    title="Volta a ser aberta e a segurar o começo — fica registrado que voltou"
                  >
                    Não resolvida — reabrir
                  </Btn>
                </div>
              )}
            </div>
          ))}
        </>
      )}
      {erro && !novo && <span style={{ fontSize: 11, color: 'var(--danger-ink)' }}>{erro}</span>}
      {podeRegistrar && !atividade.tem_filhos && (novo ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <select value={novo.tipo} onChange={(e) => setNovo({ ...novo, tipo: e.target.value as TipoRestricao })} style={ESTILO_CAMPO} aria-label="Tipo de restrição">
            {TIPOS_DE_RESTRICAO.map((t) => <option key={t.valor} value={t.valor}>{t.rotulo}</option>)}
          </select>
          <input
            autoFocus
            value={novo.descricao}
            onChange={(e) => setNovo({ ...novo, descricao: e.target.value })}
            placeholder={novo.tipo === 'material' ? 'Ex.: aço CA-50 da 2ª laje' : 'O que impede o começo'}
            style={ESTILO_CAMPO}
          />
          <div style={{ display: 'flex', gap: 5 }}>
            <input
              type="date" min={minCalendarioISO} max={maxCalendarioISO}
              value={novo.prazo} onChange={(e) => setNovo({ ...novo, prazo: e.target.value })}
              title={novo.tipo === 'material' ? 'Quando o material chega' : 'Até quando precisa estar resolvido'}
              style={{ ...ESTILO_CAMPO, flex: 1 }}
            />
            <input value={novo.responsavel} onChange={(e) => setNovo({ ...novo, responsavel: e.target.value })} placeholder="Quem resolve" style={{ ...ESTILO_CAMPO, flex: 1 }} />
          </div>
          {editavelPlano && novo.prazo && (
            <label style={{ fontSize: 11.5, color: 'var(--ink-2)', display: 'flex', gap: 5, alignItems: 'center' }}>
              <input type="checkbox" checked={novo.segurar} onChange={(e) => setNovo({ ...novo, segurar: e.target.checked })} />
              A atividade só começa nessa data (fixa no cronograma)
            </label>
          )}
          <div style={{ display: 'flex', gap: 6 }}>
            <Btn tam="sm" variant="primary" onClick={registrar} disabled={criar.isPending || !novo.descricao.trim()}>Registrar</Btn>
            <Btn tam="sm" onClick={() => setNovo(null)}>Cancelar</Btn>
          </div>
          {erro && <span style={{ fontSize: 11, color: 'var(--danger-ink)' }}>{erro}</span>}
        </div>
      ) : (
        <Btn tam="sm" onClick={() => setNovo({ tipo: 'material', descricao: '', prazo: '', responsavel: '', segurar: true })}>
          + Restrição (material, projeto…)
        </Btn>
      ))}
    </Bloco>
  )
}

/* -- Seletores ------------------------------------------------------------ */

function SeletorDeLocal(
  { atividade, obraId, montagem, editavel }:
  { atividade: Atividade; obraId: number; montagem: Montagem; editavel: boolean },
) {
  const { data: locais = [] } = useLocais(obraId, editavel)
  if (!editavel) {
    return atividade.local_rotulo
      ? <Linha rotulo="Local" valor={atividade.local_rotulo} />
      : <Linha rotulo="Local" valor={semApuracao('sem local, fica fora da linha de balanço')} />
  }
  const paraLocais = { pathname: `/app/pdca/o/${obraId}/plano`, search: '?vista=locais' }
  if (locais.length === 0) {
    // Sem locais o seletor vazio não dizia nada. O que é, para que serve, e o
    // caminho para cadastrar — e que é opcional.
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Linha rotulo="Local" valor={semApuracao('opcional — a obra não tem locais')} />
        <div style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          Local é <em>onde</em> na obra o serviço acontece (trecho, estaca, torre, pavimento). Serve à linha
          de balanço e a apontar por frente.{' '}
          <Link to={paraLocais} style={{ color: 'var(--brand)' }}>Cadastrar locais</Link>
        </div>
      </div>
    )
  }
  return (
    <Campo rotulo="Local">
      <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', minWidth: 0 }}>
        <select
          value={atividade.local ?? ''}
          onChange={(e) => montagem.salvar(atividade, { local: e.target.value ? Number(e.target.value) : null }, 'local')}
          style={ESTILO_SELECT}
          aria-label="Local"
          title="Onde na obra o serviço acontece (trecho, torre, pavimento…)"
        >
          <option value="">sem local</option>
          {locais.map((l) => (
            <option key={l.local_id} value={l.local_id}>{'· '.repeat(Math.max(0, l.profundidade - 1))}{l.nome}</option>
          ))}
        </select>
        <Link to={paraLocais} title="Cadastrar ou editar os locais da obra" style={{ fontSize: 11, color: 'var(--brand)' }}>editar</Link>
      </span>
    </Campo>
  )
}

/** Vazio é **herdar o expediente do plano** — e o rótulo diz qual é, para a
 *  atividade que segue o "Expediente da obra" não parecer sem expediente. Só
 *  quem escolhe outro (o turno da noite, a frente que trabalha sábado) grava
 *  um expediente próprio; mudar o do plano no topo arrasta todas as que herdam. */
function SeletorDeExpediente(
  { atividade, obraId, montagem, editavel, doPlano }:
  { atividade: Atividade; obraId: number; montagem: Montagem; editavel: boolean; doPlano: number | null },
) {
  const { data: calendarios = [] } = useCalendarios(obraId)
  const nomeDoPlano = calendarios.find((c) => c.calendario_id === doPlano)?.nome
  const herdado = nomeDoPlano ? `${nomeDoPlano} (o do plano)` : 'o do plano'
  if (!editavel) return <Linha rotulo="Expediente" valor={atividade.calendario_nome || herdado} />
  return (
    <Campo rotulo="Expediente">
      <select
        value={atividade.calendario ?? ''}
        onChange={(e) => montagem.salvar(atividade, { calendario: e.target.value ? Number(e.target.value) : null }, 'expediente')}
        style={ESTILO_SELECT}
        aria-label="Expediente"
      >
        <option value="">{herdado}</option>
        {calendarios
          .filter((c) => c.calendario_id !== doPlano || atividade.calendario === doPlano)
          .map((c) => <option key={c.calendario_id} value={c.calendario_id}>{c.nome}</option>)}
      </select>
    </Campo>
  )
}

function SeletorDeResponsavel(
  { atividade, montagem, editavel }: { atividade: Atividade; montagem: Montagem; editavel: boolean },
) {
  const { data, isError } = useQuery({
    queryKey: ['pdca', 'funcionarios'],
    queryFn: buscarFuncionarios,
    enabled: editavel,
    staleTime: 5 * 60_000,
    retry: false,
  })
  if (!editavel || isError) {
    return atividade.responsavel_nome
      ? <LinhaLink rotulo="Responsável" valor={atividade.responsavel_nome} para={`/app/rh/${atividade.responsavel}`} />
      : editavel ? <Linha rotulo="Responsável" valor={semApuracao('sem acesso à lista de funcionários (módulo RH)')} /> : null
  }
  return (
    <Campo rotulo="Responsável">
      <select
        value={atividade.responsavel ?? ''}
        onChange={(e) => montagem.salvar(atividade, { responsavel: e.target.value ? Number(e.target.value) : null }, 'responsável')}
        style={ESTILO_SELECT}
        aria-label="Responsável"
      >
        <option value="">ninguém</option>
        {(data ?? []).map((f) => <option key={f.funcionario_id} value={f.funcionario_id}>{f.nome_completo}</option>)}
      </select>
    </Campo>
  )
}

function SeletorDeItemOrcado(
  { atividade, obraId, montagem, editavel }:
  { atividade: Atividade; obraId: number; montagem: Montagem; editavel: boolean },
) {
  const [buscando, setBuscando] = useState(false)
  const [termo, setTermo] = useState('')
  const [itens, setItens] = useState<ItemOrcadoCurto[]>([])
  const [erro, setErro] = useState<string | null>(null)
  const { data: orcamentos = [] } = useQuery({
    queryKey: ['pdca', 'orcamentos-do-plano', atividade.cronograma],
    queryFn: () => planoApi.orcamentos(atividade.cronograma),
    enabled: editavel && buscando,
  })
  const orcamento = orcamentos[0]

  useEffect(() => {
    if (!buscando || !orcamento) return
    const t = setTimeout(() => {
      buscarItensOrcados(orcamento.orcamento_id, termo)
        .then((r) => { setItens(r); setErro(null) })
        .catch((e) => setErro(mensagemDe(e, 'Sem acesso aos itens do orçamento.')))
    }, 250)
    return () => clearTimeout(t)
  }, [buscando, termo, orcamento])

  const atual = atividade.item_orcado_rotulo
    ? <LinhaLink rotulo="Item orçado" valor={atividade.item_orcado_rotulo} para={`/app/orcamento/orcar/obra/${obraId}`} />
    : <Linha rotulo="Item orçado" valor={semApuracao('sem item, o peso não vem do custo')} />
  if (!editavel) return atividade.item_orcado_rotulo ? atual : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {atual}
      {!buscando ? (
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <Btn tam="sm" onClick={() => setBuscando(true)}>{atividade.item_orcado ? 'Trocar item' : 'Ligar ao orçamento'}</Btn>
          {atividade.item_orcado && (
            <Btn tam="sm" onClick={() => montagem.salvar(atividade, { item_orcado: null }, 'item orçado')}>Desligar</Btn>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {!orcamento ? (
            <Vazio>Esta obra não tem orçamento.</Vazio>
          ) : (
            <>
              <input autoFocus value={termo} onChange={(e) => setTermo(e.target.value)} placeholder={`Buscar em ${orcamento.descricao}`} style={ESTILO_CAMPO} />
              <div style={{ maxHeight: 160, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                {itens.map((i) => (
                  <button
                    key={i.item_orcado_id}
                    type="button"
                    onClick={async () => { await montagem.salvar(atividade, { item_orcado: i.item_orcado_id }, 'item orçado'); setBuscando(false) }}
                    style={{ textAlign: 'left', background: 'transparent', border: 'none', borderBottom: '1px solid var(--line-2)', padding: '4px 2px', fontSize: 12, cursor: 'pointer', color: 'var(--ink)' }}
                  >
                    <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{i.codigo_eap}</span> {i.descricao}
                  </button>
                ))}
              </div>
            </>
          )}
          {erro && <span style={{ fontSize: 11, color: 'var(--danger-ink)' }}>{erro}</span>}
          <Btn tam="sm" onClick={() => setBuscando(false)}>Fechar</Btn>
        </div>
      )}
    </div>
  )
}

/** A etapa da obra escolhida — ou **criada aqui mesmo**, sem ir ao cadastro. */
function SeletorDeEtapa(
  { atividade, obraId, montagem }: { atividade: Atividade; obraId: number; montagem: Montagem },
) {
  const { data: etapas = [] } = useEtapasDaObra(obraId)
  const criar = useCriarEtapa(obraId)
  const [novaNome, setNovaNome] = useState<string | null>(null)

  async function criarEGuardar() {
    const nome = (novaNome ?? '').trim()
    if (!nome) return
    try {
      const ordem = etapas.reduce((m, e) => Math.max(m, e.ordem), 0) + 1
      const nova = await criar.mutateAsync({ nome, ordem })
      setNovaNome(null)
      await montagem.salvar(atividade, { etapa: nova.etapa_id }, 'etapa da obra')
    } catch (e) {
      montagem.avisar(mensagemDe(e, 'Não foi possível criar a etapa.'))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <Campo rotulo="Etapa da obra">
        <select
          value={atividade.etapa ?? ''}
          aria-label="Etapa da obra"
          style={ESTILO_SELECT}
          onChange={(e) => {
            if (e.target.value === 'nova') { setNovaNome(''); return }
            void montagem.salvar(atividade, { etapa: e.target.value ? Number(e.target.value) : null }, 'etapa da obra')
          }}
        >
          <option value="">sem etapa</option>
          {etapas.map((e) => <option key={e.etapa_id} value={e.etapa_id}>{e.nome_etapa}</option>)}
          <option value="nova">+ Nova etapa…</option>
        </select>
      </Campo>
      {novaNome !== null && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            autoFocus
            value={novaNome}
            placeholder="Nome da etapa"
            onChange={(e) => setNovaNome(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void criarEGuardar()
              if (e.key === 'Escape') setNovaNome(null)
            }}
            style={{ ...ESTILO_CAMPO, flex: 1 }}
          />
          <Btn tam="sm" variant="primary" disabled={criar.isPending || !novaNome.trim()} onClick={() => void criarEGuardar()}>Criar</Btn>
        </div>
      )}
    </div>
  )
}

/* -- Peças ------------------------------------------------------------------ */

const ESTILO_CAMPO = {
  fontSize: 12, padding: '4px 6px', background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', minWidth: 0,
} as const

const ESTILO_SELECT = { ...ESTILO_CAMPO, maxWidth: 190 } as const

const BOTAO_X = {
  background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)',
  padding: '0 4px', fontSize: 14,
} as const

/** Campo que grava ao sair (blur) ou no Enter — como a grade. */
function CampoTexto(
  { valor, aoGravar, rotulo, numerico = false, multilinha = false, largura, estilo }: {
    valor: string
    aoGravar: (v: string) => unknown
    rotulo: string
    numerico?: boolean
    multilinha?: boolean
    largura?: number
    estilo?: React.CSSProperties
  },
) {
  const [rascunho, setRascunho] = useState(valor)
  useEffect(() => { setRascunho(valor) }, [valor])
  const gravar = () => { if (rascunho.trim() !== valor.trim()) void aoGravar(rascunho.trim()) }
  const comum = {
    'aria-label': rotulo,
    value: rascunho,
    onBlur: gravar,
    style: {
      ...ESTILO_CAMPO, width: largura ?? '100%', textAlign: numerico ? 'right' as const : 'left' as const,
      ...estilo,
    },
  }
  if (multilinha) {
    return <textarea {...comum} rows={2} onChange={(e) => setRascunho(e.target.value)} style={{ ...comum.style, resize: 'vertical' }} />
  }
  return (
    <input
      {...comum}
      inputMode={numerico ? 'decimal' : undefined}
      onChange={(e) => setRascunho(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        if (e.key === 'Escape') { setRascunho(valor); (e.target as HTMLInputElement).blur() }
      }}
    />
  )
}

function data(iso: string | null): string {
  return iso ? dateToBR(iso) : '—'
}

/** Nunca zero onde ninguém mediu: o rótulo diz o que falta. */
function semApuracao(porque: string) {
  return <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }} title={porque}>{porque}</span>
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 7 }}>
        {titulo}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</div>
    </div>
  )
}

function Subtitulo({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 11, fontWeight: 650, color: 'var(--ink-2)', marginTop: 2 }}>{children}</div>
}

function Vazio({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 11.5, color: 'var(--ink-3)', fontStyle: 'italic' }}>{children}</div>
}

function Campo({ rotulo, children, coluna = false }: { rotulo: string; children: React.ReactNode; coluna?: boolean }) {
  return (
    <label
      style={{
        display: 'flex', flexDirection: coluna ? 'column' : 'row', alignItems: coluna ? 'stretch' : 'center',
        gap: coluna ? 4 : 10, justifyContent: 'space-between',
      }}
    >
      <span style={{ fontSize: 12, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      {children}
    </label>
  )
}

function Linha(
  { rotulo, valor, nota, tom }: { rotulo: string; valor: React.ReactNode; nota?: string; tom?: string },
) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, justifyContent: 'space-between' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      <span style={{ textAlign: 'right', minWidth: 0 }}>
        <span style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12.5, color: tom ?? 'var(--ink)' }}>
          {valor}
        </span>
        {nota && <span style={{ display: 'block', fontSize: 10.5, color: 'var(--ink-3)' }}>{nota}</span>}
      </span>
    </div>
  )
}

function LinhaLink({ rotulo, valor, para }: { rotulo: string; valor: string; para: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, justifyContent: 'space-between' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      <Link to={para} style={{ fontSize: 12.5, color: 'var(--brand)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3, textAlign: 'right' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{valor}</span>
        <ArrowUpRight size={12} style={{ flexShrink: 0 }} />
      </Link>
    </div>
  )
}
