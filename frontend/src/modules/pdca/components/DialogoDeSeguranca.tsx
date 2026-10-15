import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, BookOpenCheck, Check, ChevronLeft, Users } from 'lucide-react'
import { BotaoExportar, Btn, CampoInteiro, Card, Empty, Loading, Modal, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR, maxCalendarioISO, maxTodayISO, minCalendarioISO } from '@/utils/dates'
import { useAbrirDds, useDds, useDdsDaObra, useEncerrarDds, useRegistrarPresenca } from '../hooks'
import { Ajuda, Campo, FaixaDeErro, Linha } from './Formulario'
import type { DialogoSeguranca } from '../types'
import { entrada } from '../estilos'
import { primeiraFrase } from '../formato'

/** Os diálogos de segurança da obra — os abertos (lista ainda colhendo nome)
 *  primeiro, porque são os que alguém precisa fechar. */
export function ListaDeDds({
  obraId, aoAbrir,
}: { obraId: number; aoAbrir: (id: number) => void }) {
  const { hasPermission } = useAuth()
  const pode = hasPermission('pdca.dds.registrar')
  const consulta = useDdsDaObra(obraId)
  const [abrindo, setAbrindo] = useState(false)

  const lista = [...(consulta.data ?? [])].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'rascunho' ? -1 : 1
    return b.data.localeCompare(a.data)
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 12.5, color: 'var(--ink-3)', flex: 1, lineHeight: 1.55 }}>
          A roda antes do turno. A lista de presença é o que prova — e ela fecha no
          encerramento, que também escreve no diário da obra.
        </span>
        <BotaoExportar tam="md" recurso="pdca.dds" recorte={{ obra: obraId }} />
        {pode && <Btn variant="primary" onClick={() => setAbrindo(true)}>Novo diálogo</Btn>}
      </div>

      {consulta.isLoading ? (
        <Loading o="os diálogos de segurança" />
      ) : lista.length === 0 ? (
        <Card>
          <Empty>
            <span>Nenhum diálogo de segurança registrado nesta obra.</span>
            {pode && <Btn variant="primary" onClick={() => setAbrindo(true)}>Registrar o primeiro</Btn>}
          </Empty>
        </Card>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {lista.map((d) => (
            <button
              key={d.dds_id}
              type="button"
              onClick={() => aoAbrir(d.dds_id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, width: '100%',
                padding: '11px 14px', borderTop: '1px solid var(--line-2)',
                background: 'transparent', border: 'none', borderTopStyle: 'solid',
                cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ fontSize: 13.5, color: 'var(--ink)', fontWeight: 650 }}>{d.tema}</span>
                  <Pill kind={d.status === 'rascunho' ? 'accent' : 'good'}>{d.status_rotulo}</Pill>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                  {dateToBR(d.data)}{d.responsavel_label && ` · ${d.responsavel_label}`}{d.local_rotulo && ` · ${d.local_rotulo}`}
                </div>
              </div>
              <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', fontSize: 12, color: 'var(--ink-3)' }}>
                <Users size={13} /> {d.presentes}
              </span>
            </button>
          ))}
        </Card>
      )}

      {abrindo && (
        <NovoDds
          obraId={obraId}
          aoFechar={() => setAbrindo(false)}
          aoCriar={(d) => { setAbrindo(false); aoAbrir(d.dds_id) }}
        />
      )}
    </div>
  )
}

/** **O tema é o que faz o registro servir de prova** — "DDS realizado" não é
 *  tema. Por isso é o único campo que o diálogo exige para nascer. */
function NovoDds({
  obraId, aoFechar, aoCriar,
}: { obraId: number; aoFechar: () => void; aoCriar: (d: DialogoSeguranca) => void }) {
  const abrir = useAbrirDds()
  const [tema, setTema] = useState('')
  const [assunto, setAssunto] = useState('')
  const [data, setData] = useState(maxTodayISO())
  const [duracao, setDuracao] = useState(10)
  const [responsavel, setResponsavel] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  return (
    <Modal
      titulo="Novo diálogo de segurança"
      onClose={aoFechar}
      largura={560}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary" disabled={!tema.trim() || !data || abrir.isPending}
            onClick={async () => {
              setErro(null)
              try {
                aoCriar(await abrir.mutateAsync({
                  obra: obraId, data, tema: tema.trim(), assunto: assunto.trim(),
                  duracao_min: duracao || null, responsavel_nome: responsavel.trim(),
                }))
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            Abrir e colher a lista
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <FaixaDeErro>{erro}</FaixaDeErro>
        <Campo rotulo="Tema">
          <input value={tema} onChange={(e) => setTema(e.target.value)} style={entrada} autoFocus
            placeholder="Ex.: trabalho em altura na periferia da laje" />
        </Campo>
        <Campo rotulo="O que se falou (opcional)">
          <textarea rows={2} value={assunto} onChange={(e) => setAssunto(e.target.value)}
            style={{ ...entrada, resize: 'vertical' }} />
        </Campo>
        <Linha>
          <Campo rotulo="Data">
            <input type="date" value={data} min={minCalendarioISO} max={maxCalendarioISO}
              onChange={(e) => setData(e.target.value)} style={entrada} />
          </Campo>
          <Campo rotulo="Duração (min)">
            <CampoInteiro valor={duracao} aoMudar={setDuracao} min={0} aria-label="Duração em minutos" />
          </Campo>
          <Campo rotulo="Quem conduziu" larga>
            <input value={responsavel} onChange={(e) => setResponsavel(e.target.value)} style={entrada} />
          </Campo>
        </Linha>
      </div>
    </Modal>
  )
}

/** **O diálogo aberto**: a lista de presença e o encerramento.
 *
 *  A lista chega em lote — a tela acumula os nomes e grava de uma vez — e
 *  fecha com o encerramento: nome acrescentado depois é o que faz a lista
 *  deixar de provar quem estava lá. Encerrar sem ninguém presente é recusado
 *  pelo servidor, e a frase dele aparece aqui. */
export function DocumentoDoDds({
  ddsId, aoVoltar,
}: { ddsId: number; aoVoltar: () => void }) {
  const { hasPermission } = useAuth()
  const dds = useDds(ddsId)
  const presenca = useRegistrarPresenca()
  const encerrar = useEncerrarDds()
  const [nomes, setNomes] = useState('')
  const [noDiario, setNoDiario] = useState(true)
  const [erro, setErro] = useState<string | null>(null)
  const [resultado, setResultado] = useState<{ publicado: boolean } | null>(null)

  if (dds.isLoading) return <Loading o="o diálogo" />
  if (dds.isError || !dds.data) return <Card><Empty>Este diálogo não foi encontrado nesta obra.</Empty></Card>

  const d = dds.data
  const aberto = d.status === 'rascunho'
  const pode = aberto && hasPermission('pdca.dds.registrar')
  const novos = nomes.split('\n').map((n) => n.trim()).filter(Boolean)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 820 }}>
      <button
        type="button" onClick={aoVoltar}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 3, alignSelf: 'flex-start',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 12, color: 'var(--ink-3)',
        }}
      >
        <ChevronLeft size={13} />
        Todos os diálogos
      </button>

      <Card>
        <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
          <Pill kind={aberto ? 'accent' : 'good'}>{d.status_rotulo}</Pill>
          <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
            {dateToBR(d.data)}{d.duracao_min ? ` · ${d.duracao_min} min` : ''}
            {d.responsavel_label && ` · conduzido por ${d.responsavel_label}`}
          </span>
        </div>
        <h2 style={{ margin: '8px 0 0', fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>{d.tema}</h2>
        {d.assunto && <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>{d.assunto}</p>}
        {d.diario != null && (
          <Link
            to="/app/diario"
            style={{ display: 'inline-flex', gap: 5, alignItems: 'center', marginTop: 10, fontSize: 12.5, color: 'var(--brand)', textDecoration: 'none', fontWeight: 650 }}
          >
            <BookOpenCheck size={14} /> Escrito no diário da obra de {dateToBR(d.data)} <ArrowUpRight size={12} />
          </Link>
        )}
      </Card>

      <Card>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Lista de presença</span>
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{d.presentes} presentes</span>
        </div>
        {d.participantes.length === 0 ? (
          <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>Ninguém na lista ainda.</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '4px 16px' }}>
            {d.participantes.map((p) => (
              <div key={p.participante_id} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, color: p.presente ? 'var(--ink)' : 'var(--ink-3)' }}>
                <Check size={13} style={{ color: p.presente ? 'var(--good-ink)' : 'var(--line)' }} />
                {p.funcionario_nome || p.nome}
                {!p.presente && ' (ausente)'}
              </div>
            ))}
          </div>
        )}

        {pode && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--line-2)' }}>
            <Campo rotulo="Acrescentar nomes">
              <textarea
                rows={4} value={nomes} onChange={(e) => setNomes(e.target.value)}
                style={{ ...entrada, resize: 'vertical' }}
                placeholder={'Um nome por linha\nJoão Pereira\nMaria Souza'}
              />
              <Ajuda>Um por linha. A lista fecha quando o diálogo for encerrado.</Ajuda>
            </Campo>
            <Btn
              tam="sm" style={{ alignSelf: 'flex-start' }}
              disabled={novos.length === 0 || presenca.isPending}
              onClick={async () => {
                setErro(null)
                try {
                  await presenca.mutateAsync({ id: ddsId, participantes: novos.map((nome) => ({ nome, presente: true })) })
                  setNomes('')
                } catch (e) {
                  setErro(primeiraFrase(e))
                }
              }}
            >
              <Users size={13} />
              {novos.length > 1 ? `Acrescentar ${novos.length} nomes` : 'Acrescentar à lista'}
            </Btn>
          </div>
        )}
      </Card>

      {pode && (
        <Card>
          <label style={{ display: 'flex', gap: 7, alignItems: 'center', fontSize: 13, color: 'var(--ink-2)', cursor: 'pointer' }}>
            <input type="checkbox" checked={noDiario} onChange={(e) => setNoDiario(e.target.checked)} />
            Escrever este diálogo no diário da obra
          </label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
            <Btn
              variant="primary" disabled={encerrar.isPending}
              onClick={async () => {
                setErro(null)
                try {
                  const r = await encerrar.mutateAsync({ id: ddsId, publicar: noDiario })
                  setResultado({ publicado: r.publicado_no_diario })
                } catch (e) {
                  setErro(primeiraFrase(e))
                }
              }}
            >
              Encerrar o diálogo
            </Btn>
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>A lista fecha junto.</span>
          </div>
        </Card>
      )}

      {resultado && noDiario && !resultado.publicado && (
        <div style={{ fontSize: 12.5, color: 'var(--accent-ink)' }}>
          O diálogo foi encerrado, mas não foi escrito no diário — o módulo de diário
          não está disponível para esta obra.
        </div>
      )}
      <FaixaDeErro>{erro}</FaixaDeErro>
    </div>
  )
}
