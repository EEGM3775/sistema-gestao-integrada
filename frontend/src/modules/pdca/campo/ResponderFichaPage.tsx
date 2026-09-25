import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react'
import { Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { useFileUpload } from '@/hooks/useFileUpload'
import { dateToBR } from '@/utils/dates'
import { percentual, primeiraFrase } from '../formato'
import {
  useAbrirNcsDosReprovados, useConcluirFicha, useFicha, useItensDaFicha, useResponderItem,
} from '../hooks'
import { campoGrande } from '../estilos'
import { Escolhas } from '../components/Formulario'
import {
  Aviso, BotaoDaCamera, BotaoGrande, Cartao, Conjunto, Rotulado, Titulo,
  VoltarParaFrente,
} from './pecas'
import type { GravidadeNc, ItemVerificacao, ResultadoItem } from '../types'
import { exigeObservacao, GRAVIDADES } from '../vocabulario'

/** **Responder a ficha — uma pergunta por tela.**
 *
 *  É a física oposta da grade do escritório: aqui é luva, sol na tela e uma
 *  decisão por vez. "Conforme" grava no toque e passa à próxima; o desvio pede
 *  o que está errado (e quanto pesa, quando reprova) antes de gravar, porque o
 *  servidor recusaria sem isso — e recusar depois do toque se lê como defeito.
 *
 *  **A foto sobe na mesma requisição da resposta**: é o que evita o segundo
 *  gesto no canteiro. No fim, concluir devolve os reprovados, e o defeito se
 *  abre dali mesmo, com a gravidade que foi dada a cada um. */
export default function ResponderFichaPage() {
  const { verificacaoId } = useParams()
  const id = Number(verificacaoId) || undefined
  const ficha = useFicha(id)
  const itens = useItensDaFicha(id)
  const { hasPermission } = useAuth()
  const [indice, setIndice] = useState<number | null>(null)

  const lista = useMemo(() => itens.data ?? [], [itens.data])

  useEffect(() => {
    if (indice != null || lista.length === 0) return
    const primeiraPendente = lista.findIndex((i) => i.resultado === 'pendente')
    setIndice(primeiraPendente === -1 ? lista.length : primeiraPendente)
  }, [lista, indice])

  if (ficha.isLoading || itens.isLoading || (indice == null && lista.length > 0)) {
    return <Loading o="a ficha" />
  }
  if (ficha.isError || !ficha.data) {
    return (
      <div style={{ padding: 14 }}>
        <VoltarParaFrente />
        <Aviso tom="danger">Esta ficha não foi encontrada. Confira o sinal e tente de novo.</Aviso>
      </div>
    )
  }

  const dados = ficha.data
  const aberta = dados.status === 'em_andamento'
  const podeResponder = aberta && hasPermission('pdca.verificacao.aplicar')
  const atual = indice ?? lista.length

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VoltarParaFrente />
      <Titulo sub={`${dateToBR(dados.data)}${dados.local_rotulo ? ` · ${dados.local_rotulo}` : ''}${dados.atividade_nome ? ` · ${dados.atividade_nome}` : ''}`}>
        {dados.modelo_nome}
      </Titulo>

      <Progresso itens={lista} atual={atual} aoIr={setIndice} />

      {!podeResponder && aberta && (
        <Aviso tom="accent">
          Você vê esta ficha, mas não pode respondê-la. Quem libera é o administrador da empresa.
        </Aviso>
      )}

      {atual < lista.length && podeResponder ? (
        <Pergunta
          key={lista[atual].item_verificacao_id}
          item={lista[atual]}
          total={lista.length}
          aoAvancar={() => setIndice(atual + 1)}
          aoVoltar={atual > 0 ? () => setIndice(atual - 1) : undefined}
        />
      ) : (
        <Fechamento fichaId={dados.verificacao_id} itens={lista} aberta={aberta} aoRevisar={setIndice} />
      )}
    </div>
  )
}

function Progresso({
  itens, atual, aoIr,
}: { itens: ItemVerificacao[]; atual: number; aoIr: (i: number) => void }) {
  const respondidas = itens.filter((i) => i.resultado !== 'pendente').length
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 6 }}>
        <span>{atual < itens.length ? `Pergunta ${atual + 1} de ${itens.length}` : 'Revisão'}</span>
        <span>{respondidas} respondidas</span>
      </div>
      <div style={{ display: 'flex', gap: 3 }}>
        {itens.map((item, i) => (
          <button
            key={item.item_verificacao_id}
            type="button"
            aria-label={`Ir para a pergunta ${i + 1}`}
            onClick={() => aoIr(i)}
            style={{
              flex: 1, height: 8, borderRadius: 3, border: 'none', padding: 0, cursor: 'pointer',
              outline: i === atual ? '2px solid var(--ink)' : 'none', outlineOffset: 1,
              background: item.resultado === 'conforme' ? 'var(--good-ink)'
                : item.resultado === 'nao_conforme' ? 'var(--danger-ink)'
                  : item.resultado === 'nao_aplicavel' ? 'var(--ink-3)' : 'var(--line)',
            }}
          />
        ))}
      </div>
    </div>
  )
}

function Pergunta({
  item, total, aoAvancar, aoVoltar,
}: {
  item: ItemVerificacao
  total: number
  aoAvancar: () => void
  aoVoltar?: () => void
}) {
  const responder = useResponderItem()
  const { validate } = useFileUpload()
  const [escolha, setEscolha] = useState<ResultadoItem | null>(
    item.resultado === 'pendente' ? null : item.resultado,
  )
  const [observacao, setObservacao] = useState(item.observacao)
  const [gravidade, setGravidade] = useState<GravidadeNc | null>(item.gravidade)
  const [foto, setFoto] = useState<File | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  async function gravar(resultado: ResultadoItem) {
    setErro(null)
    if (foto) {
      const problema = validate(foto)
      if (problema) { setErro(problema); return }
    }
    try {
      await responder.mutateAsync({
        id: item.item_verificacao_id,
        corpo: {
          resultado,
          observacao: observacao.trim(),
          gravidade: resultado === 'nao_conforme' ? gravidade : null,
        },
        foto,
      })
      aoAvancar()
    } catch (e) {
      setErro(primeiraFrase(e))
    }
  }

  function tocar(resultado: ResultadoItem) {
    setEscolha(resultado)
    if (!exigeObservacao(resultado) && !(item.exige_foto && !foto && !item.foto)) {
      void gravar(resultado)
    }
  }

  const desvio = escolha != null && exigeObservacao(escolha)
  const faltaFoto = item.exige_foto && !foto && !item.foto
  const pronto = escolha != null
    && (!desvio || observacao.trim())
    && (escolha !== 'nao_conforme' || gravidade)

  return (
    <Cartao>
      <div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
          {item.ordem}/{total}{item.obrigatorio && ' · obrigatória'}
        </div>
        <div style={{ fontSize: 19, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.4, marginTop: 4 }}>
          {item.texto}
        </div>
        {item.criterio && (
          <div style={{ fontSize: 14, color: 'var(--ink-2)', marginTop: 6, lineHeight: 1.5 }}>
            {item.criterio}
          </div>
        )}
      </div>

      <Escolhas
        tamanho="lg"
        rotulo="Resposta"
        valor={escolha}
        aoEscolher={tocar}
        opcoes={[
          { valor: 'conforme', rotulo: 'Conforme', tom: 'good' },
          { valor: 'nao_conforme', rotulo: 'Não conforme', tom: 'danger' },
          { valor: 'nao_aplicavel', rotulo: 'Não se aplica', tom: 'slate' },
        ]}
      />

      {escolha === 'nao_conforme' && (
        <Conjunto rotulo="Quanto pesa">
          <Escolhas
            tamanho="lg"
            rotulo="Gravidade"
            valor={gravidade}
            aoEscolher={setGravidade}
            opcoes={GRAVIDADES.map((g) => ({ valor: g.valor, rotulo: `${g.rotulo} — ${g.explica}`, tom: g.tom }))}
          />
        </Conjunto>
      )}

      {desvio && (
        <Rotulado rotulo={escolha === 'nao_conforme' ? 'O que está errado' : 'Por que não se aplica aqui'}>
          <textarea
            rows={3} value={observacao} autoFocus
            onChange={(e) => setObservacao(e.target.value)}
            style={{ ...campoGrande, resize: 'vertical' }}
          />
        </Rotulado>
      )}

      {(desvio || item.exige_foto) && (
        <div>
          {item.exige_foto && (
            <div style={{ fontSize: 13, color: 'var(--accent-ink)', marginBottom: 7 }}>
              Esta pergunta pede foto.
            </div>
          )}
          <BotaoDaCamera foto={foto} aoMudar={setFoto} />
        </div>
      )}

      <Aviso tom="danger">{erro}</Aviso>

      {(desvio || (escolha && faltaFoto)) && (
        <BotaoGrande
          onClick={() => escolha && gravar(escolha)}
          disabled={!pronto || responder.isPending}
        >
          {responder.isPending ? 'Gravando…' : 'Gravar e seguir'}
        </BotaoGrande>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <button
          type="button" onClick={aoVoltar} disabled={!aoVoltar}
          style={navegacao(!aoVoltar)}
        >
          <ChevronLeft size={17} /> Anterior
        </button>
        <button type="button" onClick={aoAvancar} style={navegacao(false)}>
          {item.resultado === 'pendente' ? 'Pular por enquanto' : 'Próxima'} <ChevronRight size={17} />
        </button>
      </div>
    </Cartao>
  )
}

const navegacao = (inativo: boolean) => ({
  display: 'inline-flex', alignItems: 'center', gap: 4, minHeight: 44, padding: '0 6px',
  background: 'none', border: 'none', cursor: inativo ? 'default' : 'pointer',
  color: 'var(--ink-3)', fontSize: 14, fontFamily: 'inherit', opacity: inativo ? 0.3 : 1,
}) as const

function Fechamento({
  fichaId, itens, aberta, aoRevisar,
}: {
  fichaId: number
  itens: ItemVerificacao[]
  aberta: boolean
  aoRevisar: (i: number) => void
}) {
  const { hasPermission } = useAuth()
  const navigate = useNavigate()
  const concluir = useConcluirFicha()
  const abrirNcs = useAbrirNcsDosReprovados()
  const [erro, setErro] = useState<string | null>(null)
  const [feito, setFeito] = useState<string | null>(null)

  const conformes = itens.filter((i) => i.resultado === 'conforme').length
  const reprovados = itens.filter((i) => i.resultado === 'nao_conforme')
  const pendentesObrigatorias = itens.filter((i) => i.obrigatorio && i.resultado === 'pendente')
  const semNc = reprovados.filter((i) => i.nc == null)
  const julgados = conformes + reprovados.length
  const conformidade = julgados ? (conformes * 100) / julgados : null

  return (
    <Cartao>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Pill kind="good">{conformes} conformes</Pill>
        <Pill kind={reprovados.length ? 'danger' : 'slate'}>{reprovados.length} não conformes</Pill>
        {conformidade != null && <Pill kind="slate">{percentual(conformidade)} de conformidade</Pill>}
      </div>

      {aberta && pendentesObrigatorias.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Aviso tom="accent">
            Faltam {pendentesObrigatorias.length} perguntas obrigatórias. A ficha só se
            conclui com elas respondidas — ou marcadas como não se aplica, dizendo por quê.
          </Aviso>
          <BotaoGrande tom="neutro" onClick={() => aoRevisar(itens.indexOf(pendentesObrigatorias[0]))}>
            Ir para a primeira que falta
          </BotaoGrande>
        </div>
      )}

      <Aviso tom="danger">{erro}</Aviso>
      <Aviso tom="good">{feito}</Aviso>

      {aberta && hasPermission('pdca.verificacao.aplicar') && pendentesObrigatorias.length === 0 && (
        <BotaoGrande
          disabled={concluir.isPending}
          onClick={async () => {
            setErro(null)
            try {
              await concluir.mutateAsync(fichaId)
              setFeito('Ficha concluída. O escritório já está vendo.')
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        >
          {concluir.isPending ? 'Concluindo…' : 'Concluir a ficha'}
        </BotaoGrande>
      )}

      {!aberta && semNc.length > 0 && (
        hasPermission('pdca.nc.abrir') ? (
          <BotaoGrande
            tom="danger"
            disabled={abrirNcs.isPending}
            onClick={async () => {
              setErro(null)
              try {
                const r = await abrirNcs.mutateAsync(fichaId)
                setFeito(r.abertas === 1 ? 'Defeito aberto — já está na fila do escritório.' : `${r.abertas} defeitos abertos — já estão na fila do escritório.`)
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            <AlertTriangle size={19} />
            {semNc.length === 1 ? 'Abrir o defeito do que reprovou' : `Abrir os ${semNc.length} defeitos`}
          </BotaoGrande>
        ) : (
          <Aviso tom="accent">
            {semNc.length} {semNc.length === 1 ? 'pergunta reprovou' : 'perguntas reprovaram'}. Avise o
            escritório para abrir o defeito.
          </Aviso>
        )
      )}

      <BotaoGrande tom="neutro" onClick={() => navigate('/campo')}>Voltar para a minha frente</BotaoGrande>
    </Cartao>
  )
}
