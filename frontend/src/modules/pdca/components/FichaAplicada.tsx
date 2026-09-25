import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowUpRight, Camera, ChevronLeft, Smartphone } from 'lucide-react'
import { Btn, Card, Empty, Loading, Num, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import { percentual, primeiraFrase } from '../formato'
import {
  useAbrirNcsDosReprovados, useConcluirFicha, useFicha, useItensDaFicha, useResponderItem,
} from '../hooks'
import { FotoProtegida } from './FotoProtegida'
import { Escolhas, FaixaDeErro } from './Formulario'
import { entrada } from '../estilos'
import { exigeObservacao, GRAVIDADES, RESPOSTAS, TOM_DA_RESPOSTA } from '../vocabulario'
import type {
  GravidadeNc, ItemVerificacao, ResultadoDaVerificacao, ResultadoItem,
} from '../types'




/** **A ficha aplicada, no escritório.**
 *
 *  A mesma ficha que o campo responde uma pergunta por tela, aqui em lista —
 *  para quem inspeciona com o notebook na mão ou revisa o que chegou. **Cada
 *  resposta grava sozinha**: não há botão de salvar a ficha, porque a
 *  inspeção vale pergunta a pergunta e um "salvar" no fim é o que se esquece.
 *
 *  Concluir devolve os reprovados que ainda não viraram defeito, e o gesto
 *  que os abre está logo ali: o técnico acabou de percorrer a ficha, e
 *  obrigá-lo a redigitar cada defeito é o que faz a NC não ser aberta. */
export function FichaAplicada({
  fichaId, obraId, aoVoltar, aoAbrirNc,
}: {
  fichaId: number
  obraId: number
  aoVoltar: () => void
  aoAbrirNc: (id: number) => void
}) {
  const { hasPermission } = useAuth()
  const ficha = useFicha(fichaId)
  const itens = useItensDaFicha(fichaId)
  const concluir = useConcluirFicha()
  const abrirNcs = useAbrirNcsDosReprovados()
  const [erro, setErro] = useState<string | null>(null)

  const podeAplicar = hasPermission('pdca.verificacao.aplicar')
  const podeAbrirNc = hasPermission('pdca.nc.abrir')

  if (ficha.isLoading || itens.isLoading) return <Loading o="a ficha" />
  if (ficha.isError || !ficha.data) {
    return (
      <Card>
        <Empty>Esta ficha não foi encontrada nesta obra.</Empty>
      </Card>
    )
  }

  const dados = ficha.data
  const aberta = dados.status === 'em_andamento'
  const lista = itens.data ?? []
  const editavel = aberta && podeAplicar
  const semNc = lista.filter((i) => i.resultado === 'nao_conforme' && i.nc == null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 960 }}>
      <button
        type="button" onClick={aoVoltar}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 3, alignSelf: 'flex-start',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 12, color: 'var(--ink-3)',
        }}
      >
        <ChevronLeft size={13} />
        Todas as fichas
      </button>

      <Card>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <Pill kind={aberta ? 'accent' : 'good'}>{dados.status_rotulo}</Pill>
              <Pill kind="slate">{dados.dominio_rotulo}</Pill>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)' }}>
                {dados.modelo_codigo}
              </span>
            </div>
            <h2 style={{ margin: '8px 0 0', fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>
              {dados.modelo_nome}
            </h2>
            <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 4, lineHeight: 1.6 }}>
              {dateToBR(dados.data)}
              {dados.inspetor && ` · ${dados.inspetor}`}
              {[dados.local_rotulo, dados.atividade_nome && `${dados.atividade_codigo} ${dados.atividade_nome}`]
                .filter(Boolean).map((t) => ` · ${t}`).join('')}
            </div>
          </div>
          <Placar resultado={dados.resultado} />
        </div>

        {aberta && podeAplicar && (
          <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap', alignItems: 'center' }}>
            <Btn
              variant="primary"
              disabled={concluir.isPending}
              onClick={async () => {
                setErro(null)
                try {
                  await concluir.mutateAsync(fichaId)
                } catch (e) {
                  setErro(primeiraFrase(e))
                }
              }}
            >
              Concluir a ficha
            </Btn>
            <Link
              to={`/campo/ficha/${fichaId}`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: 'var(--brand)', textDecoration: 'none' }}
            >
              <Smartphone size={14} />
              Responder no celular, uma pergunta por tela
            </Link>
          </div>
        )}
        <div style={{ marginTop: erro ? 10 : 0 }}><FaixaDeErro>{erro}</FaixaDeErro></div>
      </Card>

      {!aberta && (
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.55 }}>
          Ficha concluída — ela virou prova e não recebe mais resposta. Corrigir uma
          inspeção concluída é reinspecionar: aplique o modelo de novo.
        </p>
      )}

      {!aberta && semNc.length > 0 && (
        <ReprovadosSemDefeito
          reprovados={semNc}
          podeAbrir={podeAbrirNc}
          ocupado={abrirNcs.isPending}
          aoAbrir={async () => {
            setErro(null)
            try {
              const r = await abrirNcs.mutateAsync(fichaId)
              if (r.ncs.length === 1) aoAbrirNc(r.ncs[0])
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        />
      )}

      <Card pad={false} style={{ overflow: 'hidden' }}>
        {lista.map((item) => (
          <LinhaDoItem
            key={item.item_verificacao_id}
            item={item}
            editavel={editavel}
            obraId={obraId}
          />
        ))}
        {lista.length === 0 && <Empty>Esta ficha não tem perguntas.</Empty>}
      </Card>
    </div>
  )
}

function Placar({ resultado }: { resultado: ResultadoDaVerificacao | null }) {
  if (!resultado) return null
  const julgados = resultado.conformes + resultado.nao_conformes
  return (
    <div style={{ display: 'flex', gap: 16, textAlign: 'right' }}>
      <div>
        <div style={rotuloPequeno}>Conformidade</div>
        {julgados ? (
          <Num size={20} tone="var(--ink)">{percentual(resultado.conformidade)}</Num>
        ) : (
          <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 4 }}>sem apuração</div>
        )}
      </div>
      <div>
        <div style={rotuloPequeno}>Respondidas</div>
        <Num size={20} tone="var(--ink)">
          {resultado.total - resultado.pendentes}
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>/{resultado.total}</span>
        </Num>
      </div>
      <div>
        <div style={rotuloPequeno}>Reprovadas</div>
        <Num size={20} tone={resultado.nao_conformes ? 'var(--danger-ink)' : 'var(--ink)'}>
          {resultado.nao_conformes}
        </Num>
      </div>
    </div>
  )
}

const rotuloPequeno = {
  fontSize: 9.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
} as const

/** Os reprovados que ainda não viraram defeito — **com o peso que cada um
 *  recebeu na hora**, por quem o viu. O gesto abre todos de uma vez, e nenhum
 *  seletor de gravidade aparece aqui: um peso só para todos faria o
 *  desalinhamento da porta pesar igual à falta da maçaneta. */
function ReprovadosSemDefeito({
  reprovados, podeAbrir, ocupado, aoAbrir,
}: {
  reprovados: ItemVerificacao[]
  podeAbrir: boolean
  ocupado: boolean
  aoAbrir: () => void
}) {
  const quantos = reprovados.length
  return (
    <div
      style={{
        padding: '12px 14px', borderRadius: 'var(--r-md)',
        background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        display: 'flex', flexDirection: 'column', gap: 10,
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <AlertTriangle size={17} />
        <span style={{ flex: 1, fontSize: 13, lineHeight: 1.5, minWidth: 220 }}>
          {quantos === 1 ? '1 pergunta reprovou' : `${quantos} perguntas reprovaram`} e ainda não
          {quantos === 1 ? ' virou defeito' : ' viraram defeito'}. Sem isso, ninguém trata.
        </span>
        {podeAbrir ? (
          <Btn variant="perigo" disabled={ocupado} onClick={aoAbrir}>
            {quantos === 1 ? 'Abrir o defeito' : `Abrir os ${quantos} defeitos`}
          </Btn>
        ) : (
          <span style={{ fontSize: 12 }}>Quem abre defeito é quem tem a permissão de abrir não-conformidade.</span>
        )}
      </div>
      <ul style={{ margin: 0, paddingLeft: 30, fontSize: 12.5, lineHeight: 1.6 }}>
        {reprovados.map((r) => (
          <li key={r.item_verificacao_id}>
            {r.ordem}. {r.texto}
            {r.gravidade_rotulo && <strong> — {r.gravidade_rotulo.split(' — ')[0]}</strong>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Uma pergunta. "Conforme" grava no toque; desvio abre a observação (e a
 *  gravidade, quando reprova) e grava no botão — sem o texto, o servidor
 *  recusaria, e a recusa depois do toque se lê como defeito da tela. */
function LinhaDoItem({
  item, editavel, obraId,
}: { item: ItemVerificacao; editavel: boolean; obraId: number }) {
  const responder = useResponderItem()
  const [rascunho, setRascunho] = useState<{
    resultado: ResultadoItem; observacao: string; gravidade: GravidadeNc | null
  } | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  async function gravar(resultado: ResultadoItem, observacao: string, gravidade: GravidadeNc | null) {
    setErro(null)
    try {
      await responder.mutateAsync({
        id: item.item_verificacao_id,
        corpo: { resultado, observacao, gravidade: resultado === 'nao_conforme' ? gravidade : null },
      })
      setRascunho(null)
    } catch (e) {
      setErro(primeiraFrase(e))
    }
  }

  function escolher(resultado: ResultadoItem) {
    if (exigeObservacao(resultado)) {
      setRascunho({
        resultado,
        observacao: item.resultado === resultado ? item.observacao : '',
        gravidade: item.resultado === resultado ? item.gravidade : null,
      })
      return
    }
    void gravar(resultado, '', null)
  }

  const atual = rascunho?.resultado ?? item.resultado

  return (
    <div style={{ padding: '12px 14px', borderTop: '1px solid var(--line-2)' }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-3)', minWidth: 22, paddingTop: 1 }}>
          {item.ordem}
        </span>
        <div style={{ flex: 1, minWidth: 240 }}>
          <div style={{ fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.45 }}>
            {item.texto}
            {item.obrigatorio && <span style={{ color: 'var(--danger-ink)' }} title="Obrigatória"> *</span>}
          </div>
          {item.criterio && (
            <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2, lineHeight: 1.5 }}>
              Critério: {item.criterio}
            </div>
          )}
          {item.exige_foto && !item.foto && (
            <div style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 3 }}>
              <Camera size={12} /> Esta pergunta pede foto — responda pelo celular para fotografar.
            </div>
          )}
          {!editavel && item.observacao && (
            <div style={{ fontSize: 12.5, color: 'var(--ink-2)', marginTop: 4 }}>“{item.observacao}”</div>
          )}
          {item.nc != null && (
            <Link
              to={`/app/pdca/o/${obraId}/qualidade?nc=${item.nc}`}
              style={{ display: 'inline-flex', gap: 4, alignItems: 'center', fontSize: 12, color: 'var(--brand)', marginTop: 4, textDecoration: 'none', fontWeight: 650 }}
            >
              Virou o defeito NC {item.nc} <ArrowUpRight size={12} />
            </Link>
          )}
        </div>

        {editavel ? (
          <Escolhas
            rotulo={`Resposta da pergunta ${item.ordem}`}
            valor={atual === 'pendente' && !rascunho ? null : atual}
            aoEscolher={escolher}
            opcoes={RESPOSTAS.filter((r) => r.valor !== 'pendente' || item.resultado !== 'pendente')}
          />
        ) : (
          <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
            <Pill kind={TOM_DA_RESPOSTA[item.resultado]}>{item.resultado_rotulo}</Pill>
            {item.gravidade && <Pill kind="slate">{item.gravidade_rotulo.split(' — ')[0]}</Pill>}
          </div>
        )}
      </div>

      {item.foto && (
        <div style={{ marginTop: 8, paddingLeft: 34 }}>
          <FotoProtegida url={item.foto} alt={`Foto da pergunta ${item.ordem}`} altura={120} />
        </div>
      )}

      {editavel && !rascunho && item.observacao && item.resultado !== 'conforme' && (
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)', marginTop: 6, paddingLeft: 34 }}>
          “{item.observacao}”
          {item.gravidade && <span style={{ color: 'var(--ink-3)' }}> · {item.gravidade_rotulo.split(' — ')[0]}</span>}
        </div>
      )}

      {rascunho && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10, paddingLeft: 34 }}>
          {rascunho.resultado === 'nao_conforme' && (
            <Escolhas
              rotulo={`Gravidade da pergunta ${item.ordem}`}
              valor={rascunho.gravidade}
              aoEscolher={(g) => setRascunho({ ...rascunho, gravidade: g })}
              opcoes={GRAVIDADES.map((g) => ({ valor: g.valor, rotulo: `${g.rotulo} — ${g.explica}`, tom: g.tom }))}
            />
          )}
          <input
            autoFocus
            value={rascunho.observacao}
            onChange={(e) => setRascunho({ ...rascunho, observacao: e.target.value })}
            placeholder={rascunho.resultado === 'nao_conforme' ? 'O que está errado' : 'Por que não se aplica aqui'}
            aria-label={`Observação da pergunta ${item.ordem}`}
            style={entrada}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <Btn tam="sm" onClick={() => { setRascunho(null); setErro(null) }}>Voltar</Btn>
            <Btn
              tam="sm" variant="primary"
              disabled={
                !rascunho.observacao.trim()
                || (rascunho.resultado === 'nao_conforme' && !rascunho.gravidade)
                || responder.isPending
              }
              onClick={() => gravar(rascunho.resultado, rascunho.observacao.trim(), rascunho.gravidade)}
            >
              Gravar resposta
            </Btn>
          </div>
        </div>
      )}

      {erro && <div style={{ marginTop: 8, paddingLeft: 34 }}><FaixaDeErro>{erro}</FaixaDeErro></div>}
    </div>
  )
}
