import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  AlertTriangle, Check, CheckCircle2, Clock3, Download, Lock, Paperclip, RefreshCw, Upload,
  User, X,
} from 'lucide-react'
import { Btn, Empty, Loading, Pill, Spinner } from '@/components/malha'
import { baixarParaDisco } from '../api'
import {
  useAtualizarPrancha,
  useDisciplinasDoDocumento,
  usePublicar,
  useReprocessar,
  useRevisoes,
} from '../hooks'
import { EscolhaDeDisciplinas } from '../pages/Disciplinas'
import type { Derivada, Documento, Revisao } from '../types'
import { usePapel } from '../visao'

/**
 * **A história da prancha, dentro da prancha.**
 *
 * Esta gaveta é onde três abas foram parar, e a razão de terem cabido numa só é
 * que as três falavam do mesmo objeto por eixos diferentes:
 *
 * - **Histórico** era esta lista, filtrada por obra em vez de por documento. A
 *   pergunta real nunca foi "o que mudou na obra" — foi *"esta prancha aqui, quem
 *   mandou e quando?"*, e ela só se faz com a prancha aberta na frente.
 * - **Conversões** era esta mesma lista com `filter(falhou)`. O estado da
 *   derivada é atributo da revisão, não um lugar: aqui ele aparece na linha, com
 *   a frase de **quem resolve** — que é o melhor que aquela aba tinha e é o que
 *   sobreviveu inteiro.
 * - **Acervo** era um índice de documentos cujas linhas abriam um modal que já
 *   era esta gaveta. A grade indexa; o modal virou isto.
 *
 * Nada foi cortado: rótulo, situação, formato, quem enviou, quem publicou, as
 * duas datas, a observação do projetista, o motor com a versão e o motivo do erro
 * continuam todos aqui — mais perto de quem pode fazer algo a respeito.
 */
export function GavetaDeRevisoes({
  documento,
  revisaoAberta,
  aoFechar,
  say,
}: {
  documento: Documento
  /** A revisão que está desenhada na tela — ganha a marca de "você está vendo esta". */
  revisaoAberta: number
  aoFechar: () => void
  say: (m: string) => void
}) {
  const papel = usePapel()
  const { data, isLoading } = useRevisoes(documento.documento_id)
  const revisoes = data?.results ?? []

  return (
    <div
      style={{
        position: 'absolute', top: 0, right: 0, bottom: 0, zIndex: 7,
        width: 'min(420px, 94vw)', display: 'flex', flexDirection: 'column',
        background: 'var(--surface)', borderLeft: '1px solid var(--line)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '12px 14px',
          borderBottom: '1px solid var(--line)', flex: 'none',
        }}
      >
        <Clock3 size={16} style={{ color: 'var(--accent-ink)' }} />
        <div style={{ minWidth: 0 }}>
          <strong style={{ display: 'block', fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>
            Entregas desta prancha
          </strong>
          <span className="num" style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            {documento.codigo} · {documento.total_revisoes} revis
            {documento.total_revisoes === 1 ? 'ão' : 'ões'}
          </span>
        </div>
        <button
          onClick={aoFechar}
          aria-label="Fechar"
          style={{
            marginLeft: 'auto', width: 40, height: 40, display: 'grid', placeItems: 'center',
            cursor: 'pointer', background: 'transparent', border: 0, color: 'var(--ink-3)',
          }}
        >
          <X size={17} />
        </button>
      </header>

      <div style={{ overflowY: 'auto', padding: 12, display: 'grid', gap: 12 }}>
        {/* **Atualizar vem primeiro**, e é o gesto que substituiu o formulário de
            duas etapas: escolhe-se o arquivo e acabou. O rótulo sai do nome ou do
            maior que já existe — ninguém digita "R03". */}
        {papel.podeGerir && (
          <AtualizarArquivo documento={documento} say={say} />
        )}

        {/* Reclassificar mora aqui porque é **abrindo** a prancha que se descobre
            que ela também é elétrica — mandar a pessoa a uma tela de cadastro
            para corrigir o que ela está vendo é o caminho para não corrigir. */}
        {papel.podeGerir && <ReclassificarPrancha documento={documento} say={say} />}

        {isLoading && <Loading o="as entregas" />}
        {!isLoading && !revisoes.length && (
          <Empty>Esta prancha ainda não tem entrega registrada.</Empty>
        )}

        {revisoes.map((r) => (
          <Entrega
            key={r.revisao_id}
            revisao={r}
            obra={documento.obra}
            aberta={r.revisao_id === revisaoAberta}
            say={say}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * O botão que virou o fluxo do avesso.
 *
 * Antes: criar documento num formulário → escolher documento → digitar "R01" →
 * enviar. Agora: escolher o arquivo. O servidor lê o rótulo do nome quando ele
 * traz um (`ARQ-001_R02.dwg`) e senão continua do maior — a numeração é dele,
 * porque só ele sabe o que já existe sem uma corrida entre duas abas abertas.
 */
function AtualizarArquivo({ documento, say }: { documento: Documento; say: (m: string) => void }) {
  const atualizar = useAtualizarPrancha(documento.obra)
  const entrada = useRef<HTMLInputElement>(null)
  const [observacao, setObservacao] = useState('')

  const escolher = (arquivo: File | null) => {
    if (!arquivo) return
    atualizar.mutate(
      { documento: documento.documento_id, arquivo, observacao },
      {
        onSuccess: (r) => {
          setObservacao('')
          // O aviso do backend (arquivo pesado demais para o motor livre) vem
          // antes da boa notícia — é a lição do D47: dizer agora poupa a pessoa
          // de descobrir pela fila de conversão, minutos depois.
          say(
            r.aviso
              ? `${r.aviso} (${r.revisao} recebida, em rascunho.)`
              : `${r.revisao} recebida, em rascunho — publicar é o ato que muda o campo.`,
          )
        },
        onError: (e: unknown) => {
          const erro = e as { response?: { status?: number; data?: { detail?: string } } }
          // 402 é parede comercial (formato fora do plano); 400 é formato que
          // nenhum plano abre. Mandar comprar o que o produto não lê seria pior
          // do que recusar, então as frases são diferentes.
          say(
            erro?.response?.status === 402
              ? erro.response?.data?.detail ?? 'Seu plano não abre este formato.'
              : erro?.response?.data?.detail ?? 'Arquivo recusado — confira extensão e tamanho.',
          )
        },
      },
    )
    if (entrada.current) entrada.current.value = ''
  }

  return (
    <div
      style={{
        display: 'grid', gap: 8, padding: 12, borderRadius: 'var(--r-md)',
        background: 'var(--inset)', border: '1px solid var(--line)',
      }}
    >
      <input
        ref={entrada}
        type="file"
        hidden
        onChange={(e) => escolher(e.target.files?.[0] ?? null)}
      />
      <Btn
        variant="primary"
        disabled={atualizar.isPending}
        onClick={() => entrada.current?.click()}
        style={{ minHeight: 46, justifyContent: 'center' }}
      >
        {atualizar.isPending ? <Spinner /> : <Upload size={15} />}
        {atualizar.isPending ? 'Enviando…' : 'Atualizar arquivo'}
      </Btn>
      <input
        value={observacao}
        onChange={(e) => setObservacao(e.target.value)}
        placeholder="O que mudou nesta entrega? (opcional)"
        maxLength={500}
        style={{
          minHeight: 40, padding: '8px 10px', fontSize: 12.5, color: 'var(--ink)',
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)',
        }}
      />
      <span style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        A entrega nova entra como revisão própria — o arquivo de uma revisão nunca é
        trocado, e é isso que deixa comparar o que está em campo com o que chegou.
      </span>
    </div>
  )
}

/**
 * As disciplinas desta prancha, editáveis no lugar onde se descobre a correção.
 *
 * Só grava quando **muda**, e por um motivo prático: a gaveta abre e fecha o
 * tempo todo, e um PATCH a cada abertura encheria o log de auditoria com
 * alterações que ninguém fez.
 */
function ReclassificarPrancha({
  documento, say,
}: {
  documento: Documento
  say: (m: string) => void
}) {
  const definir = useDisciplinasDoDocumento(documento.obra)
  const atuais = (documento.disciplinas ?? []).map((d) => d.codigo)
  const [rascunho, setRascunho] = useState<string[]>(atuais)

  // O acervo é a fonte: se alguém reclassificar noutra aba, a gaveta acompanha
  // em vez de guardar um retrato do instante em que abriu (a lição do `abertoId`).
  useEffect(() => { setRascunho(atuais) }, [atuais.join(',')])

  const mudou = rascunho.join(',') !== atuais.join(',')

  return (
    <div
      style={{
        display: 'grid', gap: 9, padding: 12, borderRadius: 'var(--r-md)',
        background: 'var(--surface)', border: '1px solid var(--line)',
      }}
    >
      <EscolhaDeDisciplinas
        valor={rascunho}
        aoMudar={setRascunho}
        rotulo="Disciplinas desta prancha"
        compacto
      />
      {mudou && (
        <Btn
          tam="sm"
          variant="primary"
          disabled={definir.isPending}
          onClick={() => definir.mutate(
            { documento: documento.documento_id, codigos: rascunho },
            {
              onSuccess: () => say('Prancha reclassificada.'),
              onError: () => say('Não foi possível reclassificar agora.'),
            },
          )}
        >
          {definir.isPending ? <Spinner /> : <Check size={13} />} Salvar disciplinas
        </Btn>
      )}
    </div>
  )
}

/** Uma entrega: o que se sabe dela, e o que dá para fazer com ela. */
function Entrega({
  revisao, obra, aberta, say,
}: {
  revisao: Revisao
  obra: number
  aberta: boolean
  say: (m: string) => void
}) {
  const papel = usePapel()
  const publicar = usePublicar(obra)
  const reprocessar = useReprocessar(obra)

  const cor = revisao.situacao === 'vigente'
    ? 'var(--good)' : revisao.situacao === 'rascunho' ? 'var(--accent)' : 'var(--line)'

  return (
    <div
      style={{
        display: 'grid', gap: 9, padding: '11px 13px', borderRadius: 'var(--r-md)',
        background: aberta ? 'color-mix(in srgb,var(--accent) 8%,var(--surface))' : 'var(--surface)',
        border: `1px solid ${aberta ? 'var(--accent)' : 'var(--line)'}`,
        borderLeft: `4px solid ${cor}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
        <strong className="num" style={{ fontSize: 14, color: 'var(--ink)' }}>{revisao.revisao}</strong>
        <Pill kind={revisao.situacao === 'vigente' ? 'good' : revisao.situacao === 'rascunho' ? 'accent' : 'slate'}>
          {revisao.situacao_rotulo}
        </Pill>
        <Pill kind="slate">{revisao.formato_rotulo}</Pill>
        {aberta && <Pill kind="info">na tela</Pill>}
      </div>

      {/* Quem entregou e quem decidiu são linhas separadas porque na maioria das
          obras não é a mesma pessoa — e a segunda é o ato de alçada. */}
      <div style={{ display: 'grid', gap: 4, fontSize: 12.5, color: 'var(--ink-2)' }}>
        <Linha icone={<Upload size={13} />}>
          Enviada por <strong>{revisao.enviado_por_nome ?? 'origem não registrada'}</strong>
          {' '}em {quando(revisao.enviado_em)}
        </Linha>

        {revisao.publicado_em ? (
          <Linha icone={<CheckCircle2 size={13} style={{ color: 'var(--good)' }} />}>
            Publicada por <strong>{revisao.publicado_por_nome ?? 'usuário removido'}</strong>
            {' '}em {quando(revisao.publicado_em)}
            {revisao.situacao === 'superada' && ' · depois substituída'}
          </Linha>
        ) : (
          <Linha icone={<Clock3 size={13} />}>
            <span style={{ color: 'var(--ink-3)' }}>Ainda não publicada — não vale em campo</span>
          </Linha>
        )}

        {revisao.data_emissao && (
          <Linha icone={<User size={13} />}>
            Emitida pelo projetista em {somenteData(revisao.data_emissao)}
          </Linha>
        )}
      </div>

      {revisao.observacao && (
        <p
          style={{
            margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5,
            background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: '8px 10px',
          }}
        >
          “{revisao.observacao}”
        </p>
      )}

      {/* O que a aba Conversões dizia, dito na linha da revisão que falhou. */}
      {revisao.derivadas.map((d) => <EstadoDaDerivada key={d.derivada_id} derivada={d} />)}

      <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
        {revisao.arquivo_url && (
          <Btn
            tam="sm"
            onClick={() => baixarParaDisco(
              revisao.arquivo_url as string, `${revisao.documento_codigo}-${revisao.revisao}`,
            )}
          >
            <Download size={13} /> Original
          </Btn>
        )}
        {papel.podeReprocessar && (
          <Btn
            tam="sm"
            disabled={reprocessar.isPending}
            onClick={() => reprocessar.mutate(revisao.revisao_id, {
              onSuccess: (d) => say(d.detail),
              onError: () => say('Nenhum motor do seu plano converte este formato — não há o que reprocessar.'),
            })}
          >
            <RefreshCw size={13} /> Reconverter
          </Btn>
        )}
        {papel.podePublicar && revisao.situacao === 'rascunho' && (
          <Btn
            tam="sm"
            variant="primary"
            disabled={publicar.isPending}
            onClick={() => publicar.mutate(revisao.revisao_id, {
              onSuccess: () => say(`${revisao.revisao} publicada. O campo passa a executar esta revisão.`),
              onError: () => say('Não foi possível publicar esta revisão.'),
            })}
          >
            <CheckCircle2 size={13} /> Publicar
          </Btn>
        )}
      </div>
    </div>
  )
}

/**
 * O estado de uma derivada, com a **saída** junto.
 *
 * Herda inteira a separação que a aba Conversões fazia — comprar, consertar,
 * reenviar, nada a fazer —, porque fundi-las mandaria o operador abrir chamado
 * por um upsell, ou o dono comprar plano por causa de um binário que falta no
 * servidor. A diferença é que agora a frase aparece **na revisão que falhou**, e
 * não numa fila que só quem sabia da aba encontrava.
 */
function EstadoDaDerivada({ derivada }: { derivada: Derivada }) {
  if (derivada.estado === 'pronto') {
    return (
      <span className="num" style={{ fontSize: 11, color: 'var(--ink-3)' }}>
        {derivada.tipo_rotulo} · {derivada.motor} {derivada.motor_versao}
      </span>
    )
  }

  if (derivada.estado !== 'erro') {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--ink-3)' }}>
        <Spinner size={12} /> {derivada.tipo_rotulo}: {derivada.estado_rotulo}
      </span>
    )
  }

  const [icone, saida] = derivada.exige_upgrade
    ? [<Lock key="i" size={12} />, 'Resolve-se comprando: o motor de alta fidelidade abre este arquivo.']
    : derivada.erro_motivo === 'referencia_ausente'
      ? [<Paperclip key="i" size={12} />, 'Resolve-se reenviando: a geometria está em arquivos externos (XREF) que não subiram junto.']
      : derivada.problema_no_arquivo
        ? [<AlertTriangle key="i" size={12} />, 'Não há o que converter: o arquivo não traz desenho dentro. Ele continua baixável na íntegra.']
        : [<AlertTriangle key="i" size={12} />, 'Resolve-se consertando: a falha é do servidor, não do seu arquivo nem do seu plano.']

  return (
    <div
      style={{
        display: 'grid', gap: 3, padding: '7px 9px', borderRadius: 'var(--r-sm)',
        background: derivada.exige_upgrade ? 'var(--accent-soft)' : 'var(--inset)',
        border: `1px solid ${derivada.exige_upgrade ? 'var(--accent)' : 'var(--line)'}`,
      }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 700, color: 'var(--ink)' }}>
        {icone} {derivada.tipo_rotulo}: {derivada.erro_motivo_rotulo || derivada.estado_rotulo}
      </span>
      <span style={{ fontSize: 11, color: 'var(--ink-2)', lineHeight: 1.45 }}>{saida}</span>
      {derivada.erro_detalhe && (
        <span className="num" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>{derivada.erro_detalhe}</span>
      )}
    </div>
  )
}

function Linha({ icone, children }: { icone: ReactNode; children: ReactNode }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 7 }}>
      <span style={{ color: 'var(--ink-3)', flex: 'none', marginTop: 1 }}>{icone}</span>
      <span>{children}</span>
    </span>
  )
}

function quando(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function somenteData(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}
