import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, FileSignature, HandCoins, Plus, ShieldAlert } from 'lucide-react'
import { Btn, Card, Empty, Loading, Num, Pill } from '@/components/malha'
import type { PillKind } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { useContratos, useMedicoes, useObras } from '../hooks'
import { ModalContrato } from '../components/FormContrato'
import type { Contrato, StatusContrato } from '../types'

/**
 * **Os contratos de uma obra** — a porta da medição.
 *
 * *(Decisão do dono, 15/09/2026: "medição tem que ficar dentro de pdca".)* A
 * primeira escrita desta tela era cross-obra, com entrada própria na barra
 * lateral; agora ela é **da obra**, como o cronograma, e é alcançada pelo cartão
 * da obra na `ObrasPage`. A unidade de trabalho do módulo é a obra (§5.1), e
 * esta tela deixou de ser a exceção.
 *
 * A régua do projeto (frontend.md §1.6) pede **fila de decisão** antes de lista,
 * e aqui ela tem conteúdo real: a medição parada esperando atesto é o documento
 * que segura o pagamento do empreiteiro. A fila **desta obra** vem primeiro; a
 * fila da empresa inteira — que é a pergunta que não pertence a uma obra — vive
 * na raiz do módulo.
 */

const CORES: Record<StatusContrato, PillKind> = {
  vigente: 'good',
  rascunho: 'accent',
  suspenso: 'info',
  encerrado: 'slate',
  cancelado: 'slate',
}

const dinheiro = (v: string | number | null) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

export default function ContratosPage() {
  const navegar = useNavigate()
  const { obraId } = useParams()
  const obra = Number(obraId)
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('pdca.contrato.edit')
  const podeVerMedicao = hasPermission('pdca.medicao.view')

  const [criando, setCriando] = useState(false)

  const obras = useObras()
  const contratos = useContratos({ obra })

  /** A fila de decisão **desta obra**. Carregada apenas para quem pode ver
   *  medição — quem não pode não deve nem receber a contagem. */
  const emAprovacao = useMedicoes(
    { status: 'em_aprovacao', contrato__obra: obra }, podeVerMedicao,
  )

  const lista = contratos.data?.results ?? []
  const fila = emAprovacao.data?.results ?? []
  const nomeDaObra = useMemo(
    () => (obras.data ?? []).find(o => o.obra_id === obra)?.nome_obra,
    [obras.data, obra],
  )

  if (obras.isLoading || contratos.isLoading) return <Loading o="os contratos" />

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <Link
        to="/app/pdca"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)', fontSize: 13, textDecoration: 'none' }}
      >
        <ArrowLeft size={14} /> Planejamento
      </Link>

      <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Contratos e medição</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--ink-2)', fontSize: 14 }}>
            {nomeDaObra ?? `Obra ${obra}`}
          </p>
          <p style={{ margin: '8px 0 0', color: 'var(--ink-3)', fontSize: 13, maxWidth: 660 }}>
            O que foi combinado com cada empreiteiro e quanto se paga deste
            período. A medição <strong>nasce do avanço apontado</strong> — o
            sistema propõe a quantidade, você confere e ajusta, e o atesto do
            último degrau gera o título no financeiro.
          </p>
        </div>
        {podeEditar && (
          <Btn variant="brand" onClick={() => setCriando(true)}>
            <Plus size={15} /> Novo contrato
          </Btn>
        )}
      </header>

      {/* --- Fila de decisão ------------------------------------------------
          Primeiro na tela porque é o que segura dinheiro. Some quando está
          vazia: um card permanentemente escrito "nada a decidir" treina o olho
          a ignorar a região onde a decisão vai aparecer. */}
      {fila.length > 0 && (
        <Card style={{ borderColor: 'var(--accent)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <ShieldAlert size={16} style={{ color: 'var(--accent-ink)' }} />
            <strong style={{ fontSize: 14.5 }}>Requer decisão</strong>
            <Pill kind="accent" pulse>{fila.length} medição(ões) na escada</Pill>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {fila.map(m => (
              <button
                key={m.medicao_id}
                onClick={() => navegar(
                  `/app/pdca/obra/${obra}/contratos/${m.contrato}?medicao=${m.medicao_id}`,
                )}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left',
                  padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 8,
                  background: 'var(--surface)', color: 'var(--ink)', cursor: 'pointer',
                  fontSize: 13.5, width: '100%',
                }}
              >
                <span style={{ fontWeight: 600 }}>
                  Medição {m.numero} · {m.contrato_numero}
                </span>
                <span style={{ color: 'var(--ink-2)' }}>{m.fornecedor_nome}</span>
                <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
                  {/* De quem se espera a decisão — "em aprovação" sozinho não
                      ajuda ninguém a saber se a bola está com ele. */}
                  {m.escada?.nivel && (
                    <span style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>
                      parada em <strong>{m.escada.nivel}</strong>
                    </span>
                  )}
                  <Num>{dinheiro(m.totais.liquido)}</Num>
                </span>
              </button>
            ))}
          </div>
        </Card>
      )}

      {lista.length === 0 ? (
        <Empty>
          Esta obra não tem contrato cadastrado. O contrato é o que permite medir
          e pagar empreiteiro — sem ele o avanço apontado fica só como
          acompanhamento físico.
        </Empty>
      ) : (
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))' }}>
          {lista.map(c => (
            <CartaoContrato
              key={c.contrato_id}
              contrato={c}
              onAbrir={() => navegar(`/app/pdca/obra/${obra}/contratos/${c.contrato_id}`)}
            />
          ))}
        </div>
      )}

      {criando && (
        <ModalContrato
          obras={obras.data ?? []}
          obraFixa={obra}
          onClose={() => setCriando(false)}
          onPronto={id => {
            setCriando(false)
            navegar(`/app/pdca/obra/${obra}/contratos/${id}`)
          }}
        />
      )}
    </div>
  )
}

function CartaoContrato({ contrato, onAbrir }: { contrato: Contrato; onAbrir: () => void }) {
  const temRetencao = Number(contrato.retencao_percentual) > 0
  return (
    <Card>
      <button
        onClick={onAbrir}
        style={{
          all: 'unset', cursor: 'pointer', display: 'flex', flexDirection: 'column',
          gap: 10, width: '100%',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <FileSignature size={15} style={{ color: 'var(--ink-3)' }} />
          <strong style={{ fontSize: 15 }}>{contrato.numero}</strong>
          <Pill kind={CORES[contrato.status]}>{contrato.status_rotulo}</Pill>
          {contrato.regime_publico && <Pill kind="info">Regime público</Pill>}
        </div>

        <div style={{ color: 'var(--ink-2)', fontSize: 13.5 }}>
          {contrato.fornecedor_nome}
        </div>
        <div style={{
          color: 'var(--ink-3)', fontSize: 12.5, display: '-webkit-box',
          WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {contrato.objeto}
        </div>

        <div style={{
          display: 'flex', gap: 14, alignItems: 'baseline', flexWrap: 'wrap',
          paddingTop: 8, borderTop: '1px solid var(--line)',
        }}>
          <Rotulo t="Regime">{contrato.regime_rotulo}</Rotulo>
          <Rotulo t="Itens">{contrato.itens_count}</Rotulo>
          <Rotulo t="Medições">{contrato.medicoes_count}</Rotulo>
          {temRetencao && (
            <span
              title={
                contrato.retencao_condicao_liberacao
                  ? `Libera em: ${contrato.retencao_condicao_liberacao}`
                  : 'Condição de liberação não preenchida neste contrato.'
              }
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--ink-2)', fontSize: 12.5 }}
            >
              <HandCoins size={13} />
              {Number(contrato.retencao_percentual)}% · {contrato.retencao_natureza_rotulo}
            </span>
          )}
        </div>
      </button>
    </Card>
  )
}

function Rotulo({ t, children }: { t: string; children: React.ReactNode }) {
  return (
    <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
      <span style={{ color: 'var(--ink-3)' }}>{t}: </span>{children}
    </span>
  )
}
