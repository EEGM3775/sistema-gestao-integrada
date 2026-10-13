import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { Btn, CampoMoeda, Card, Empty, Loading, Num, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors } from '@/utils/formErrors'
import { apiDecimalToCents, centsToApiDecimal, formatBRL } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import { usePdca } from '../contexto'
import {
  useSalvarAditivo, useExcluirAditivo, useCancelarAditivo, useAbrirMedicao, useAditivos, useAtestarAditivo,
  useAtestarMedicao, useBoletins, useCancelarMedicao, useContextoDaMedicao,
  useCriarContrato, useCriarItemDoContrato, useDocumentoDaMedicao, useItensDoContrato,
  useLiberacoes, useLiberarRetencao, usePostoDaMedicao, usePrevia,
  useRemoverItemDoContrato, useRetificarMedicao, useSalvarCabecalho,
  useSalvarDeducoes, useSalvarGrade, useSalvarItemDoContrato,
  useSubmeterAditivo, useSubmeterMedicao, useAtivarContrato,
} from '../hooks'
import { ApurarPeriodo } from '../components/ApurarPeriodo'
import { BoletimDeMedicao, type LinhaDeDeducao } from '../components/BoletimDeMedicao'
import { CarteiraDeContratos } from '../components/CarteiraDeContratos'
import { FilaDoDinheiro } from '../components/FilaDoDinheiro'
import { FormularioDeContrato } from '../components/FormularioDeContrato'
import { GradeDeMedicao, type LinhaEditada } from '../components/GradeDeMedicao'
import { PainelDeAditivos } from '../components/PainelDeAditivos'
import { PainelDeRetencao } from '../components/PainelDeRetencao'
import { PlanilhaContratual } from '../components/PlanilhaContratual'
import { FichaDoContrato } from '../components/FichaDoContrato'
import { TrilhaDoContrato } from '../components/TrilhaDoContrato'
import { paradaInicial, type Desvio, type Parada } from '../trilha'
import type { Autosave } from '../autosave'
import type { LinhaDeContrato, StatusMedicao } from '../types'

/** As paradas do caminho que têm tela própria (aprovação e executado abrem a
 *  de medir, onde estão os boletins) e os dois desvios. */
type Vista = 'planilha' | 'vigente' | 'medir' | 'aditivos' | 'retencao'

const CHAVES = new Set<string>(['planilha', 'vigente', 'medir', 'aditivos', 'retencao'])

/** **A vista sai do endereço, e não de um `useState`** — todo link é colável e
 *  a aba nova cai onde estava. Os nomes antigos (`apurar`, `boletins`) caem em
 *  *medir*, que juntou os dois. Sem nada escrito, o boletim do endereço abre;
 *  sem boletim, a tela abre na **próxima parada** do contrato (o mapa). */
function vistaDoEndereco(params: URLSearchParams): Vista | null {
  const pedida = params.get('v')
  if (pedida === 'apurar' || pedida === 'boletins') return 'medir'
  if (pedida && CHAVES.has(pedida)) return pedida as Vista
  return params.get('boletim') ? 'medir' : null
}

/** O erro da API em texto, **sempre**. A recusa de uma lista (os descontos, as
 *  linhas da grade) chega como lista de objetos por linha, e `String()` disso
 *  é "[object Object]" — que foi o que o dono viu ao lançar desconto. */
function textoDoErro(valor: unknown): string {
  if (valor == null) return ''
  if (typeof valor === 'string') return valor.replace(/\*\*/g, '')
  if (Array.isArray(valor)) return valor.map(textoDoErro).filter(Boolean).join(' ')
  if (typeof valor === 'object') return Object.values(valor as Record<string, unknown>).map(textoDoErro).filter(Boolean).join(' ')
  return String(valor)
}

function vistaDaParada(p: Parada): Vista {
  return p === 'planilha' || p === 'vigente' ? p : 'medir'
}

const TOM_DO_STATUS: Record<StatusMedicao, 'good' | 'accent' | 'info' | 'danger' | 'slate'> = {
  rascunho: 'info',
  em_aprovacao: 'accent',
  aprovada: 'good',
  reprovada: 'danger',
  cancelada: 'slate',
  retificada: 'slate',
}

/** **O posto do dinheiro.** Quanto se deve, por que, e quem autoriza.
 *
 *  Abre na carteira de contratos com a fila ao lado — porque a primeira
 *  pergunta do mês não é "qual contrato", é "o que está parado". Entrar num
 *  contrato troca a página pelas cinco vistas dele, e o contrato e o boletim
 *  vivem no endereço (`?contrato=&boletim=`): todo link é colável, e a aba
 *  nova abre onde estava. */
export default function MedicaoPage() {
  const { obraId, selecionar } = usePdca()
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const [erro, setErro] = useState<string | null>(null)
  const [previaPedida, setPreviaPedida] = useState<{ inicio: string; fim: string } | null>(null)
  const [contratoNovo, setContratoNovo] = useState(false)
  /** O autosave da grade vive no componente dela; o botão de submeter vive
   *  aqui. Esta referência é a ponte — **submeter grava antes de submeter**, e
   *  desiste do envio se a gravação falhar (D137). */
  const autosaveDaGrade = useRef<Autosave | null>(null)
  const [pendente, setPendente] = useState(false)
  const registrarAutosave = useCallback((a: Autosave | null) => {
    autosaveDaGrade.current = a
    setPendente(a?.estado === 'pendente' || a?.estado === 'erro')
  }, [])

  const contratoId = Number(params.get('contrato')) || null
  const boletimId = Number(params.get('boletim')) || null
  const vistaPedida = vistaDoEndereco(params)

  function setVista(qual: Vista) {
    const novo = new URLSearchParams(params)
    novo.set('v', qual)
    setParams(novo, { replace: true })
  }

  /** Ir a uma parada do mapa fecha o boletim aberto — numa escrita só. */
  function irPara(qual: Vista) {
    const novo = new URLSearchParams(params)
    novo.delete('boletim')
    novo.set('v', qual)
    setParams(novo, { replace: true })
  }

  const posto = usePostoDaMedicao(obraId)

  const podeApurar = hasPermission('pdca.medicao.apurar')
  const podeAtestar = hasPermission('pdca.medicao.atestar')
  const podeEditarContrato = hasPermission('pdca.contrato.edit')
  const podeEditarAditivo = hasPermission('pdca.aditivo.edit')
  const podeAprovarAditivo = hasPermission('pdca.aditivo.aprovar')

  const contrato: LinhaDeContrato | undefined = useMemo(
    () => posto.data?.contratos.linhas.find((l) => l.contrato === contratoId),
    [posto.data, contratoId],
  )
  /** Sem vista no endereço, a tela abre na **próxima parada** do contrato. */
  const vista: Vista = vistaPedida ?? (contrato ? vistaDaParada(paradaInicial(contrato)) : 'medir')

  const itens = useItensDoContrato(
    contratoId ?? undefined, vista === 'planilha' || vista === 'aditivos',
  )
  const boletins = useBoletins(contratoId ?? undefined)
  const aditivos = useAditivos(contratoId ?? undefined, vista === 'aditivos')
  const liberacoes = useLiberacoes(contratoId ?? undefined, vista === 'retencao')
  const contexto = useContextoDaMedicao(boletimId ?? undefined)
  const documento = useDocumentoDaMedicao(boletimId ?? undefined)
  const previa = usePrevia(
    contratoId ?? undefined,
    previaPedida?.inicio ?? '',
    previaPedida?.fim ?? '',
    previaPedida != null,
  )

  const criarContrato = useCriarContrato(obraId)
  const abrirMedicao = useAbrirMedicao(obraId)
  const salvarGrade = useSalvarGrade(obraId)
  const salvarDeducoes = useSalvarDeducoes(obraId)
  const salvarCabecalho = useSalvarCabecalho(obraId)
  const submeter = useSubmeterMedicao(obraId)
  const atestar = useAtestarMedicao(obraId)
  const cancelar = useCancelarMedicao(obraId)
  const retificar = useRetificarMedicao(obraId)
  const criarItem = useCriarItemDoContrato(obraId)
  const salvarItem = useSalvarItemDoContrato(obraId)
  const removerItem = useRemoverItemDoContrato(obraId)
  const salvarAditivo = useSalvarAditivo(obraId)
  const excluirAditivo = useExcluirAditivo(obraId)
  const cancelarAditivo = useCancelarAditivo(obraId)
  const submeterAditivo = useSubmeterAditivo(obraId)
  const atestarAditivo = useAtestarAditivo(obraId)
  const liberarRetencao = useLiberarRetencao(obraId)
  const ativarContrato = useAtivarContrato(obraId)

  /** Sair do contrato limpa o boletim junto — um `?boletim=` de outro contrato
   *  abriria um documento que não pertence à tela em que a pessoa está. */
  /** Trocar de contrato é **uma escrita só no endereço**: contrato, boletim e
   *  vista saem juntos. Duas chamadas seguidas partiriam do mesmo `params` do
   *  render e a segunda apagaria o contrato que a primeira acabou de pôr. */
  function escolherContrato(
    id: number | null, medicao?: number, aVista?: Vista,
  ) {
    const novo = new URLSearchParams(params)
    if (id == null) {
      novo.delete('contrato')
      novo.delete('boletim')
      novo.delete('v')
    } else {
      novo.set('contrato', String(id))
      if (medicao != null) {
        novo.set('boletim', String(medicao))
        novo.set('v', aVista ?? 'medir')
      } else {
        novo.delete('boletim')
        // Sem vista pedida, o contrato abre na próxima parada do caminho.
        if (aVista) novo.set('v', aVista)
        else novo.delete('v')
      }
    }
    setParams(novo, { replace: true })
    setErro(null)
    setPreviaPedida(null)
  }

  /** O aviso de erro é do gesto que falhou, não da tela: mudar de vista o
   *  apaga, senão ele fica acusando um problema que não é mais o de agora. */
  useEffect(() => { setErro(null) }, [vista])

  function escolherBoletim(id: number | null) {
    const novo = new URLSearchParams(params)
    if (id == null) novo.delete('boletim')
    else novo.set('boletim', String(id))
    novo.set('v', 'medir')
    setParams(novo, { replace: true })
    setErro(null)
  }

  async function executar(acao: () => Promise<unknown>) {
    setErro(null)
    try {
      await acao()
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(textoDoErro(erros._form ?? Object.values(erros)[0]) || 'Não foi possível concluir.')
    }
  }

  if (posto.isLoading) return <Loading o="os contratos da obra" />

  if (posto.isError) {
    return (
      <div style={{ padding: 26 }}>
        <Card>
          <Empty>
            Não foi possível carregar o posto da medição. Verifique a conexão e
            tente de novo.
          </Empty>
        </Card>
      </div>
    )
  }

  const dados = posto.data!

  /* ---------------------------------------------------------------- porta */

  if (!contrato) {
    return (
      <div
        style={{
          padding: '20px 22px 34px', display: 'flex', flexDirection: 'column',
          gap: 22, maxWidth: 1180,
        }}
      >
        <Cabecalho titulo="Medição" sub="mensal · fecha o mês" />
        {contratoId != null && (
          <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
            O contrato do endereço não está entre os desta obra — talvez ele
            tenha sido encerrado. Escolha um da lista.
          </p>
        )}
        <FilaDoDinheiro
          fila={dados.fila}
          aoEscolher={({ contrato: id, medicao }) => escolherContrato(id, medicao)}
        />
        <CarteiraDeContratos
          carteira={dados.contratos}
          contratoAtual={null}
          aoEscolher={(id) => escolherContrato(id)}
          aoCriar={podeEditarContrato ? () => setContratoNovo(true) : undefined}
        />

        {contratoNovo && (
          <FormularioDeContrato
            obraId={obraId}
            salvando={criarContrato.isPending}
            erro={erro}
            aoFechar={() => { setContratoNovo(false); setErro(null) }}
            aoSalvar={(corpo) =>
              executar(async () => {
                const novo = await criarContrato.mutateAsync(corpo)
                setContratoNovo(false)
                // Entra no contrato recém-criado, na planilha: sem itens ele
                // não mede nada, e essa é a próxima coisa a fazer.
                escolherContrato(novo.contrato_id, undefined, 'planilha')
              })}
          />
        )}
      </div>
    )
  }

  /* ------------------------------------------------------------ o contrato */

  const saldo = contrato.saldo

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          padding: '12px 18px', borderBottom: '1px solid var(--line)',
          background: 'var(--surface)', flexShrink: 0,
        }}
      >
        <button
          type="button"
          onClick={() => escolherContrato(null)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            fontSize: 12, color: 'var(--ink-3)',
          }}
        >
          <ChevronLeft size={14} />
          Contratos
        </button>

        <span style={{ width: 1, height: 20, background: 'var(--line)' }} />

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
            {contrato.numero}
          </span>
          <span
            style={{
              fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 260,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {contrato.fornecedor_nome}
          </span>
          <Pill kind={contrato.status === 'vigente' ? 'good' : 'slate'}>
            {contrato.status_rotulo}
          </Pill>
        </div>

        <span style={{ flex: 1 }} />

        {/* O saldo no cabeçalho, em todas as vistas: é o número contra o qual
            toda decisão deste posto se confere. */}
        <div style={{ display: 'flex', gap: 16 }}>
          <Resumo rotulo="Contratado" valor={saldo.valor_contratado} />
          <Resumo rotulo="Aprovado" valor={saldo.medido_aprovado} tom="var(--good-ink)" />
          <Resumo rotulo="Saldo" valor={saldo.saldo} />
        </div>
      </div>

      <TrilhaDoContrato
        contrato={contrato}
        aqui={vista === 'aditivos' || vista === 'retencao' ? null : (vista as Parada)}
        aoIr={(p) => irPara(vistaDaParada(p))}
        desvioAqui={vista === 'aditivos' || vista === 'retencao' ? (vista as Desvio) : null}
        aoDesviar={(d) => setVista(d)}
      />

      {erro && (
        <div
          style={{
            padding: '9px 18px', background: 'var(--danger-soft)',
            color: 'var(--danger-ink)', fontSize: 12.5, flexShrink: 0,
          }}
        >
          {erro}
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <div style={{ padding: '18px 20px 34px', maxWidth: 1240 }}>
          {vista === 'vigente' && (
            <PainelDaAssinatura
              contrato={contrato}
              pode={podeEditarContrato}
              ocupado={ativarContrato.isPending}
              aoAtivar={() => executar(async () => {
                await ativarContrato.mutateAsync(contrato.contrato)
                irPara('medir')
              })}
            />
          )}

          {vista === 'medir' && (
            boletimId && contexto.data && documento.data ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                <button
                  type="button"
                  onClick={() => escolherBoletim(null)}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 3,
                    alignSelf: 'flex-start', background: 'none', border: 'none',
                    padding: 0, cursor: 'pointer', fontSize: 12, color: 'var(--ink-3)',
                  }}
                >
                  <ChevronLeft size={13} />
                  Todos os boletins
                </button>

                <BoletimDeMedicao
                  medicao={documento.data}
                  obraId={obraId}
                  podeApurar={podeApurar}
                  podeAtestar={podeAtestar}
                  ocupado={
                    submeter.isPending || atestar.isPending
                    || cancelar.isPending || retificar.isPending
                  }
                  gravacaoPendente={pendente}
                  aoSubmeter={(obs) =>
                    executar(async () => {
                      // **Grava antes de enviar.** O servidor congela o que
                      // está gravado, não o que está na tela: sem este passo,
                      // digitar 200 linhas e clicar em enviar aprovaria os
                      // números antigos, em silêncio, com título a pagar no
                      // fim.
                      const gravado = await (
                        autosaveDaGrade.current?.salvarAgora() ?? Promise.resolve(true)
                      )
                      if (!gravado) {
                        throw new Error(
                          'A última digitação não chegou a ser gravada, então o '
                          + 'envio foi cancelado — o que iria para atesto não é '
                          + 'o que está na tela. Confira a grade e tente de novo.',
                        )
                      }
                      return submeter.mutateAsync({ id: boletimId, observacao: obs })
                    })}
                  aoAtestar={(aprovar, obs) =>
                    executar(() => atestar.mutateAsync({
                      id: boletimId, aprovar, observacao: obs,
                    }))}
                  aoCancelar={(motivo) =>
                    executar(async () => {
                      const original = documento.data?.retifica ?? null
                      await cancelar.mutateAsync({ id: boletimId, motivo })
                      // A retificadora descartada é apagada: o documento some, e
                      // a tela volta para a medição que ela corrigiria.
                      if (original != null) escolherBoletim(original)
                    })}
                  aoRetificar={(motivo) =>
                    executar(async () => {
                      const nova = await retificar.mutateAsync({ id: boletimId, motivo })
                      escolherBoletim(nova.medicao_id)
                    })}
                  aoSalvarDeducoes={(linhas: LinhaDeDeducao[]) =>
                    executar(() => salvarDeducoes.mutateAsync({
                      id: boletimId,
                      deducoes: linhas.map((l) => ({
                        tipo: l.tipo,
                        descricao: l.descricao,
                        valor: centsToApiDecimal(l.centavos),
                      })),
                    }))}
                />

                {/* O regime de administração não tem grade: o que se mede é o
                    custo reembolsável, e sem esta porta o regime inteiro
                    ficava sem tela. */}
                {contrato.regime === 'administracao' ? (
                  <CustoReembolsavel
                    valor={documento.data.custo_reembolsavel}
                    editavel={documento.data.status === 'rascunho' && podeApurar}
                    ocupado={salvarCabecalho.isPending}
                    aoSalvar={(valor) =>
                      executar(() => salvarCabecalho.mutateAsync({
                        id: boletimId, corpo: { custo_reembolsavel: valor },
                      }))}
                  />
                ) : (
                  <GradeDeMedicao
                    contexto={contexto.data}
                    somenteLeitura={!contexto.data.editavel || !podeApurar}
                    /* Congelamento e falta de permissão são dois estados
                       diferentes; uma frase só para os dois mentiria num. */
                    motivoDaLeitura={
                      !contexto.data.editavel
                        ? 'o boletim saiu do rascunho e os números estão '
                          + 'congelados. Para corrigir um boletim aprovado, '
                          + 'abra a retificadora.'
                        : 'lançar quantidade é de quem apura a medição, e essa '
                          + 'permissão não está no seu acesso. Quem libera é o '
                          + 'administrador da empresa.'
                    }
                    aoVerAtividade={(id) => selecionar({ tipo: 'atividade', id })}
                    aoRegistrarAutosave={registrarAutosave}
                    aoSalvar={(linhas: LinhaEditada[]) =>
                      salvarGrade.mutateAsync({
                        id: boletimId,
                        linhas: linhas.map((l) => ({
                          item_contrato_id: l.item_contrato_id,
                          quantidade: l.quantidade.replace(',', '.') || '0',
                          quantidade_estocada:
                            l.quantidade_estocada.replace(',', '.') || '0',
                          observacao: l.observacao,
                        })),
                      })}
                  />
                )}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
                {contrato.status === 'rascunho' ? (
                  <Card>
                    <Empty>
                      <span style={{ lineHeight: 1.6 }}>
                        Mede-se o contrato vigente. Esta parada abre quando o contrato estiver assinado.
                      </span>
                      <Btn onClick={() => irPara('vigente')}>Ir para Vigente</Btn>
                    </Empty>
                  </Card>
                ) : (
                  <ApurarPeriodo
                    contrato={contrato}
                    previa={previa.data}
                    carregando={previa.isLoading && previaPedida != null}
                    ocupado={abrirMedicao.isPending}
                    podeApurar={podeApurar}
                    aoVer={(inicio, fim) => setPreviaPedida({ inicio, fim })}
                    aoAbrirBoletim={(inicio, fim) =>
                      executar(async () => {
                        const nova = await abrirMedicao.mutateAsync({
                          contrato: contrato.contrato, inicio, fim,
                        })
                        escolherBoletim(nova.medicao_id)
                      })}
                  />
                )}
                {(boletins.data ?? []).length > 0 && (
                  <ListaDeBoletins
                    boletins={boletins.data ?? []}
                    carregando={boletins.isLoading}
                    aoAbrir={escolherBoletim}
                  />
                )}
              </div>
            )
          )}

          {/* A primeira parada é o **Contrato** inteiro (achado do dono,
              11/10/2026): cadastro, dinheiro até o ERP, história e itens — e a
              planilha para editar, embaixo. A chave do endereço continua
              `planilha` para os links antigos não quebrarem. */}
          {vista === 'planilha' && (
            <FichaDoContrato
              contrato={contrato}
              aoAbrirMedicao={escolherBoletim}
              aoVerAditivos={() => setVista('aditivos')}
              planilha={
                <PlanilhaContratual
                  contrato={contrato}
                  itens={itens.data ?? []}
                  carregando={itens.isLoading}
                  salvando={
                    salvarItem.isPending || criarItem.isPending || removerItem.isPending
                  }
                  aoCriar={podeEditarContrato
                    ? (corpo) => executar(() => criarItem.mutateAsync(corpo))
                    : undefined}
                  aoSalvar={podeEditarContrato
                    ? (id, corpo) => executar(() => salvarItem.mutateAsync({ id, corpo }))
                    : undefined}
                  aoRemover={podeEditarContrato
                    ? (id) => executar(() => removerItem.mutateAsync(id))
                    : undefined}
                />
              }
            />
          )}

          {vista === 'aditivos' && (
            <PainelDeAditivos
              contrato={contrato}
              aditivos={aditivos.data ?? []}
              carregando={aditivos.isLoading}
              itens={itens.data ?? []}
              carregandoItens={itens.isLoading}
              erro={erro}
              ocupado={
                salvarAditivo.isPending || submeterAditivo.isPending
                || atestarAditivo.isPending || excluirAditivo.isPending
                || cancelarAditivo.isPending
              }
              podeEditar={podeEditarAditivo}
              podeAprovar={podeAprovarAditivo}
              aoSalvar={async ({ id, cabecalho, itens: linhas, enviar }) => {
                setErro(null)
                try {
                  const salvo = await salvarAditivo.mutateAsync({
                    id, contrato: contrato.contrato, cabecalho, itens: linhas,
                  })
                  if (enviar) await submeterAditivo.mutateAsync(salvo.aditivo_id)
                  return true
                } catch (e) {
                  const erros = parseApiErrors(e)
                  setErro(textoDoErro(erros._form ?? Object.values(erros)[0]) || 'Não foi possível gravar o aditivo.')
                  return false
                }
              }}
              aoExcluir={(id) => executar(() => excluirAditivo.mutateAsync(id))}
              aoRetirar={(id, motivo) => executar(() => cancelarAditivo.mutateAsync({ id, motivo }))}
              aoSubmeter={(id) => executar(() => submeterAditivo.mutateAsync(id))}
              aoAtestar={(id, aprovar, observacao) =>
                executar(() => atestarAditivo.mutateAsync({ id, aprovar, observacao }))}
            />
          )}

          {vista === 'retencao' && (
            <PainelDeRetencao
              contrato={contrato}
              liberacoes={liberacoes.data ?? []}
              carregando={liberacoes.isLoading}
              ocupado={liberarRetencao.isPending}
              podeLiberar={podeAtestar}
              aoLiberar={(corpo) =>
                executar(() => liberarRetencao.mutateAsync({
                  id: contrato.contrato, corpo,
                }))}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function Cabecalho({ titulo, sub }: { titulo: string; sub: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
      <span style={{ fontSize: 17, fontWeight: 750, color: 'var(--ink)' }}>{titulo}</span>
      <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{sub}</span>
    </div>
  )
}

function Resumo({
  rotulo, valor, tom = 'var(--ink)',
}: { rotulo: string; valor: string; tom?: string }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div
        style={{
          fontSize: 9.5, letterSpacing: '0.08em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700,
        }}
      >
        {rotulo}
      </div>
      <Num size={13} tone={tom}>{formatBRL(apiDecimalToCents(valor))}</Num>
    </div>
  )
}

/** **Vigente** — o contrato como foi combinado, e o gesto que o põe em vigor.
 *  Sem ele o contrato ficava "em rascunho eternamente" (achado do dono,
 *  10/10/2026): o status só mudava pela API. */
function PainelDaAssinatura({ contrato, pode, ocupado, aoAtivar }: {
  contrato: LinhaDeContrato
  pode: boolean
  ocupado: boolean
  aoAtivar: () => void
}) {
  const s = contrato.saldo
  const linha = (rotulo: string, valor: React.ReactNode) => (
    <div style={{ display: 'flex', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--line-2)', fontSize: 13 }}>
      <span style={{ width: 170, color: 'var(--ink-3)' }}>{rotulo}</span>
      <span style={{ color: 'var(--ink)' }}>{valor}</span>
    </div>
  )
  const rascunho = contrato.status === 'rascunho'
  const pronto = s.itens > 0 || (contrato.regime !== 'unitario' && apiDecimalToCents(s.valor_contratado) > 0)
  return (
    <Card style={{ maxWidth: 680 }}>
      <div style={{ fontSize: 15, fontWeight: 750, color: 'var(--ink)', marginBottom: 6 }}>
        {contrato.numero} · {contrato.objeto}
      </div>
      {linha('Empreiteiro', contrato.fornecedor_nome)}
      {linha('Regime', contrato.regime_rotulo)}
      {linha('Valor contratado', <Num size={13} tone="var(--ink)">{formatBRL(apiDecimalToCents(s.valor_contratado))}</Num>)}
      {linha('Planilha', `${s.itens} ${s.itens === 1 ? 'item' : 'itens'}`)}
      {linha('Prazo', `${dateToBR(contrato.data_inicio)}${contrato.data_fim ? ` a ${dateToBR(contrato.data_fim)}` : ''}`)}
      {linha('Situação', <Pill kind={rascunho ? 'slate' : 'good'}>{contrato.status_rotulo}</Pill>)}
      {rascunho && pode && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
          <Btn variant="primary" disabled={ocupado || !pronto} onClick={aoAtivar}>
            {ocupado ? 'Ativando…' : 'Tornar vigente'}
          </Btn>
          {!pronto && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>abre depois da planilha</span>}
        </div>
      )}
    </Card>
  )
}

function ListaDeBoletins({
  boletins, carregando, aoAbrir,
}: {
  boletins: import('../types').Medicao[]
  carregando: boolean
  aoAbrir: (id: number) => void
}) {
  if (carregando) return <Loading o="os boletins do contrato" />

  const numeroDe = new Map(boletins.map((b) => [b.medicao_id, b.numero]))
  // Retificadora reprovada ou cancelada não substitui nada (a descartada nem
  // existe mais — é apagada).
  const retificadaPor = new Map(
    boletins
      .filter((b) => b.retifica != null && b.status !== 'cancelada' && b.status !== 'reprovada')
      .map((b) => [b.retifica as number, b]),
  )

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      {boletins.map((boletim) => {
        const substituida = boletim.status === 'retificada'
        const por = retificadaPor.get(boletim.medicao_id)
        const dif = boletim.totais.diferenca_liquido
        return (
        <button
          key={boletim.medicao_id}
          type="button"
          onClick={() => aoAbrir(boletim.medicao_id)}
          style={{
            display: 'flex', alignItems: 'center', gap: 12, width: '100%',
            padding: '11px 14px', borderBottom: '1px solid var(--line-2)',
            background: 'transparent', border: 'none', cursor: 'pointer',
            textAlign: 'left', color: 'inherit', font: 'inherit',
            opacity: substituida ? 0.62 : 1,
          }}
        >
          <Num size={14} tone="var(--ink-3)" style={{ minWidth: 28 }}>
            {boletim.numero}
          </Num>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, color: 'var(--ink)' }}>
                {dateToBR(boletim.periodo_inicio)} a {dateToBR(boletim.periodo_fim)}
              </span>
              <Pill kind={TOM_DO_STATUS[boletim.status]}>{boletim.status_rotulo}</Pill>
              {boletim.retifica != null && (
                <Pill kind="info">
                  retificadora{numeroDe.get(boletim.retifica) != null
                    ? ` da nº ${numeroDe.get(boletim.retifica)}` : ''}
                </Pill>
              )}
              {por && (
                <Pill kind={substituida ? 'slate' : 'accent'}>
                  {substituida ? `substituída pela nº ${por.numero}` : `em correção pela nº ${por.numero}`}
                </Pill>
              )}
            </div>
            {/* **O que compõe o número**, para ninguém ter de abrir o boletim
                e fazer a conta: o saldo do contrato é consumido pelo bruto, e
                o que se paga é o líquido. A retificadora é a medição corrigida
                inteira; a substituída fica legível, mas fora das somas. */}
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
              {substituida && 'fora das somas · '}
              bruto {formatBRL(apiDecimalToCents(boletim.totais.bruto))}
              {apiDecimalToCents(boletim.totais.retencao) !== 0 && <> · retenção − {formatBRL(apiDecimalToCents(boletim.totais.retencao))}</>}
              {apiDecimalToCents(boletim.totais.total_deducoes) !== 0 && <> · descontos − {formatBRL(apiDecimalToCents(boletim.totais.total_deducoes))}</>}
              {boletim.escada?.nivel && <> · espera {boletim.escada.nivel}</>}
              {dif != null && apiDecimalToCents(dif) !== 0 && (
                <> · {apiDecimalToCents(dif) > 0 ? '+' : '−'} {formatBRL(Math.abs(apiDecimalToCents(dif)))} sobre a original</>
              )}
            </div>
          </div>
          <Num
            size={13}
            tone={substituida ? 'var(--ink-3)' : 'var(--ink)'}
            style={substituida ? { textDecoration: 'line-through' } : undefined}
          >
            {formatBRL(apiDecimalToCents(boletim.totais.liquido))}
          </Num>
        </button>
        )
      })}
    </Card>
  )
}

/** O regime de administração: o que se mede é o **custo**, não a quantidade.
 *
 *  O número é declarado por quem apura — a apropriação automática de custo não
 *  existe —, e por isso a tela pede a instrução em vez de explicar a si mesma:
 *  o que a pessoa precisa saber é *o que escrever aqui*. */
function CustoReembolsavel({
  valor, editavel, ocupado, aoSalvar,
}: {
  valor: string | null
  editavel: boolean
  ocupado?: boolean
  aoSalvar: (valor: string) => void
}) {
  const [centavos, setCentavos] = useState(apiDecimalToCents(valor))

  useEffect(() => { setCentavos(apiDecimalToCents(valor)) }, [valor])

  return (
    <Card>
      <div
        style={{
          fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700, marginBottom: 8,
        }}
      >
        Custo reembolsável do período
      </div>
      <p style={{ margin: '0 0 12px', fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.6 }}>
        Confira com a folha, as notas e o material aplicado no período. A taxa
        de administração do contrato entra por cima deste valor.
      </p>
      {editavel ? (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', maxWidth: 360 }}>
          <div style={{ flex: 1 }}>
            <CampoMoeda
              centavos={centavos}
              aoMudar={setCentavos}
              aria-label="Custo reembolsável do período"
            />
          </div>
          <Btn
            tam="sm"
            variant="primary"
            disabled={ocupado || centavos === apiDecimalToCents(valor)}
            onClick={() => aoSalvar(centsToApiDecimal(centavos))}
          >
            Gravar
          </Btn>
        </div>
      ) : (
        <Num size={16} tone="var(--ink)">{formatBRL(apiDecimalToCents(valor))}</Num>
      )}
    </Card>
  )
}
