import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Building2, ChevronRight, FileSpreadsheet, Plus, Search, Trash2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import ModalNovoOrcamento from '../components/ModalNovoOrcamento'
import { Btn, CAPS, Card, Empty, inp, Loading, mono, Pill } from '../ui'
import { Modal } from '@/components/malha'
import { AvisoDaLixeira } from '@/components/AvisoDaLixeira'
import { brl, dataBR, mesBR, STATUS_ESTADO } from '../lib'
import { useBasesResumo, useCriarOrcamento, useObras, useOrcamentos, useRemoverOrcamento } from '../hooks'
import type { Orcamento } from '../types'

import { contemSemAcento } from '@/utils/texto'

/** A entrada do Orçar: **obra primeiro**, planilha depois.
 *
 *  Antes a página abria direto na grade e a obra era um `<select>` no
 *  cabeçalho. Dois defeitos vinham juntos: não havia "voltar" (o seletor não é
 *  um lugar, é um filtro) e a tela nascia vazia para quem ainda não sabia qual
 *  planilha queria. Aqui a navegação tem níveis — obras → orçamentos da obra →
 *  planilha —, cada um com endereço próprio, que é o que faz o botão voltar do
 *  navegador, o link colável e a trilha funcionarem sem ninguém programar nada.
 *
 *  O mesmo componente desenha os dois primeiros níveis: a diferença entre eles
 *  é uma linha de `useParams`, e separar em dois arquivos duplicaria a
 *  contagem, o filtro e a trilha.
 */
export default function ObrasOrcamentosPage() {
  const { obraId: param } = useParams()
  const obraId = param ? Number(param) : undefined
  const navigate = useNavigate()
  const { hasPermission } = useAuth()

  const { data: obras, isLoading: carregandoObras } = useObras()
  const { data: lista, isLoading: carregandoOrcamentos } = useOrcamentos({ page_size: 200, ordering: '-versao' })
  const { data: bases } = useBasesResumo()
  const criarOrcamento = useCriarOrcamento()

  const [busca, setBusca] = useState('')
  const [criando, setCriando] = useState(false)

  const orcamentos = useMemo(() => lista?.results ?? [], [lista])
  const podeCriar = hasPermission('orcamento.orcamento.edit')

  const porObra = useMemo(() => {
    const mapa = new Map<number, Orcamento[]>()
    for (const o of orcamentos) {
      const atual = mapa.get(o.obra)
      if (atual) atual.push(o)
      else mapa.set(o.obra, [o])
    }
    for (const grupo of mapa.values()) grupo.sort((a, b) => b.versao - a.versao)
    return mapa
  }, [orcamentos])

  const obra = obraId != null ? obras?.find(o => o.obra_id === obraId) : undefined
  const carregando = carregandoObras || carregandoOrcamentos

  const trilha = (
    <nav style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12.5, minWidth: 0 }}>
      {obraId == null ? (
        <span style={{ fontWeight: 650, color: 'var(--ink-2)' }}>Obras</span>
      ) : (
        <>
          <Link to="/app/orcamento/orcar" style={{ color: 'var(--ink-3)', textDecoration: 'none', fontWeight: 650 }}>
            Obras
          </Link>
          <ChevronRight size={13} style={{ color: 'var(--ink-3)', flex: 'none' }} />
          <span style={{
            fontWeight: 650, color: 'var(--ink)', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 320,
          }}>
            {obra?.nome_obra ?? `Obra ${obraId}`}
          </span>
        </>
      )}
    </nav>
  )

  const acoes = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div style={{ position: 'relative' }}>
        <Search size={13} style={{ position: 'absolute', left: 8, top: 7, color: 'var(--ink-3)' }} />
        <input
          value={busca}
          onChange={e => setBusca(e.target.value)}
          placeholder={obraId == null ? 'Filtrar obras' : 'Filtrar orçamentos'}
          style={{ ...inp, width: 176, paddingLeft: 27, padding: '5px 9px 5px 27px', fontSize: 12 }}
        />
      </div>
      {podeCriar && (
        <Btn tam="sm" variant="primary" onClick={() => setCriando(true)}><Plus size={13} />Novo orçamento</Btn>
      )}
    </div>
  )

  return (
    <PaginaShell pagina="orcar" seletor={trilha} acoes={acoes}>
      {carregando ? (
        <Loading texto="Carregando as obras…" />
      ) : obraId == null ? (
        <ListaDeObras
          obras={(obras ?? []).filter(o => contemSemAcento(o.nome_obra, busca.trim()))}
          porObra={porObra}
          vazio={(obras ?? []).length === 0}
          podeCriar={podeCriar}
          onCriar={() => setCriando(true)}
          onAbrir={id => navigate(`/app/orcamento/orcar/obra/${id}`)}
        />
      ) : (
        <ListaDeOrcamentos
          orcamentos={(porObra.get(obraId) ?? []).filter(o =>
            contemSemAcento(o.descricao, busca.trim()))}
          semNenhum={(porObra.get(obraId) ?? []).length === 0}
          podeCriar={podeCriar}
          onCriar={() => setCriando(true)}
          onAbrir={id => navigate(`/app/orcamento/orcar/orcamento/${id}`)}
        />
      )}

      {criando && (
        <ModalNovoOrcamento
          obras={obras ?? []}
          bases={bases ?? []}
          existentes={orcamentos}
          obraFixa={obraId}
          salvando={criarOrcamento.isPending}
          onFechar={() => setCriando(false)}
          onCriar={async dados => {
            const criado = await criarOrcamento.mutateAsync(dados)
            setCriando(false)
            navigate(`/app/orcamento/orcar/orcamento/${criado.orcamento_id}`)
          }}
        />
      )}
    </PaginaShell>
  )
}

/** Nível 1 — as obras, com o que cada uma já tem de planilha. */
function ListaDeObras({ obras, porObra, vazio, podeCriar, onCriar, onAbrir }: {
  obras: { obra_id: number; nome_obra: string }[]
  porObra: Map<number, Orcamento[]>
  vazio: boolean
  podeCriar: boolean
  onCriar: () => void
  onAbrir: (id: number) => void
}) {
  if (vazio) {
    return (
      <div style={{ padding: 26 }}>
        <Empty>
          Nenhuma obra cadastrada ainda. O orçamento pertence a uma obra — cadastre a obra primeiro
          e a planilha nasce em cima dela.
        </Empty>
      </div>
    )
  }
  if (!obras.length) {
    return <div style={{ padding: 26 }}><Empty>Nenhuma obra com esse nome.</Empty></div>
  }

  return (
    <div style={{ padding: '16px 20px', overflowY: 'auto', display: 'grid', gap: 8 }}>
      {obras.map(o => {
        const doGrupo = porObra.get(o.obra_id) ?? []
        // O que vale como régua é o **aprovado de maior versão**; sem aprovado,
        // mostrar o rascunho mais recente e dizer que é rascunho. Exibir o
        // rascunho como se fosse o valor da obra seria número fabricado.
        const vigente = doGrupo.find(x => x.status === 'aprovado') ?? doGrupo[0]
        return (
          <Card
            key={o.obra_id}
            className="orc-lift"
            onClick={() => onAbrir(o.obra_id)}
            style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 16px', cursor: 'pointer' }}
          >
            <Building2 size={17} style={{ color: 'var(--ink-3)', flex: 'none' }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 14, fontWeight: 650, color: 'var(--ink)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>{o.nome_obra}</div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                {doGrupo.length === 0
                  ? 'nenhum orçamento ainda'
                  : `${doGrupo.length} orçamento${doGrupo.length > 1 ? 's' : ''} · última v${doGrupo[0].versao}`}
                {vigente?.data_base ? ` · data-base ${mesBR(vigente.data_base)}` : ''}
              </div>
            </div>
            {vigente && (
              <Pill kind={STATUS_ESTADO[vigente.status].kind} pulse={STATUS_ESTADO[vigente.status].pulse}>
                {STATUS_ESTADO[vigente.status].label}
              </Pill>
            )}
            <div style={{ textAlign: 'right', minWidth: 128 }}>
              <div style={{ ...CAPS, fontSize: 9 }}>
                {vigente ? (vigente.status === 'aprovado' ? 'valor aprovado' : 'valor em rascunho') : ''}
              </div>
              <div style={{ ...mono, fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
                {vigente ? brl(vigente.valor_total) : '—'}
              </div>
            </div>
            <ChevronRight size={15} style={{ color: 'var(--ink-3)', flex: 'none' }} />
          </Card>
        )
      })}
      {podeCriar && (
        <button
          onClick={onCriar}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
            border: '1px dashed var(--line)', background: 'none', borderRadius: 'var(--r-md)',
            padding: '11px 14px', cursor: 'pointer', color: 'var(--ink-3)', fontSize: 12.5, fontWeight: 650,
          }}
        ><Plus size={14} />Novo orçamento</button>
      )}
    </div>
  )
}

/** Nível 2 — as versões daquela obra, que é onde se escolhe qual planilha abrir. */
function ListaDeOrcamentos({ orcamentos, semNenhum, podeCriar, onCriar, onAbrir }: {
  orcamentos: Orcamento[]
  semNenhum: boolean
  podeCriar: boolean
  onCriar: () => void
  onAbrir: (id: number) => void
}) {
  // Hooks antes dos `return` antecipados — a regra dos hooks não admite que a
  // quantidade chamada mude entre renders.
  const [aExcluir, setAExcluir] = useState<Orcamento | null>(null)
  const remover = useRemoverOrcamento()

  if (semNenhum) {
    return (
      <div style={{ padding: 26 }}>
        <Empty acao={podeCriar
          ? <Btn variant="primary" onClick={onCriar}><Plus size={14} />Criar o primeiro orçamento</Btn>
          : undefined}>
          Esta obra ainda não tem orçamento. Escolha a base de preço e a planilha nasce em rascunho —
          só quando for <b>aprovada</b> ela passa a valer como régua para o Estoque e o Suprimentos.
        </Empty>
      </div>
    )
  }
  if (!orcamentos.length) {
    return <div style={{ padding: 26 }}><Empty>Nenhum orçamento com esse nome.</Empty></div>
  }

  return (
    <div style={{ padding: '16px 20px', overflowY: 'auto', display: 'grid', gap: 8 }}>
      {orcamentos.map(o => (
        <Card
          key={o.orcamento_id}
          className="orc-lift"
          onClick={() => onAbrir(o.orcamento_id)}
          style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 16px', cursor: 'pointer' }}
        >
          <FileSpreadsheet size={17} style={{ color: 'var(--ink-3)', flex: 'none' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 14, fontWeight: 650, color: 'var(--ink)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {o.descricao} <span style={{ ...mono, fontSize: 12, color: 'var(--ink-3)' }}>v{o.versao}</span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              base {o.base_rotulo ?? 'não vinculada'} · data-base {mesBR(o.data_base)} ·
              {' '}{o.total_itens} linha{o.total_itens === 1 ? '' : 's'} · atualizado {dataBR(o.atualizado_em)}
            </div>
          </div>
          <Pill kind={STATUS_ESTADO[o.status].kind} pulse={STATUS_ESTADO[o.status].pulse}>
            {STATUS_ESTADO[o.status].label}
          </Pill>
          <div style={{ textAlign: 'right', minWidth: 128 }}>
            <div style={{ ...CAPS, fontSize: 9 }}>total com BDI</div>
            <div style={{ ...mono, fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{brl(o.valor_total)}</div>
          </div>
          {/* O botão só existe onde a regra do servidor deixa sair: rascunho,
              cancelado e superado. O aprovado não ganha botão trancado — ele
              **rege** a obra, e oferecer a porta para depois recusar é pior que
              não oferecer. Quem quiser excluí-lo cancela primeiro, e aí o botão
              aparece sozinho. A regra vive no backend (`STATUS_QUE_SAEM`); isto
              aqui é só não mostrar o que ele recusaria. */}
          {podeCriar && o.status !== 'aprovado' && (
            <button
              title="Excluir orçamento"
              onClick={e => { e.stopPropagation(); setAExcluir(o) }}
              style={{
                border: 'none', background: 'none', cursor: 'pointer',
                color: 'var(--ink-3)', padding: 4, display: 'flex', flex: 'none',
              }}
            ><Trash2 size={15} /></button>
          )}
          <ChevronRight size={15} style={{ color: 'var(--ink-3)', flex: 'none' }} />
        </Card>
      ))}
      {podeCriar && (
        <button
          onClick={onCriar}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
            border: '1px dashed var(--line)', background: 'none', borderRadius: 'var(--r-md)',
            padding: '11px 14px', cursor: 'pointer', color: 'var(--ink-3)', fontSize: 12.5, fontWeight: 650,
          }}
        ><Plus size={14} />Nova versão nesta obra</button>
      )}

      {aExcluir && (
        <Modal
          titulo="Excluir orçamento?"
          onClose={() => setAExcluir(null)}
          largura={470}
          rodape={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn onClick={() => setAExcluir(null)}>Cancelar</Btn>
              <Btn
                variant="perigo"
                disabled={remover.isPending}
                onClick={() => remover.mutate(aExcluir.orcamento_id, {
                  onSuccess: () => setAExcluir(null),
                })}
              >
                {remover.isPending ? 'Excluindo…' : 'Excluir'}
              </Btn>
            </div>
          }
        >
          <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>
            <b>{aExcluir.descricao}</b>{' '}
            <span style={{ ...mono, fontSize: 12 }}>v{aExcluir.versao}</span>{' '}
            sai das listagens, com as {aExcluir.total_itens} linha
            {aExcluir.total_itens === 1 ? '' : 's'} dela.
          </p>
          <p style={{ fontSize: 13, color: 'var(--ink-2)' }}>
            <AvisoDaLixeira oQue="A planilha" />
          </p>
          {remover.isError && (
            <p style={{ color: 'var(--danger)', fontSize: 12.5 }}>
              Não foi possível excluir. Se o orçamento foi aprovado, cancele-o antes.
            </p>
          )}
        </Modal>
      )}
    </div>
  )
}
