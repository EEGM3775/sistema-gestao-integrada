/** Lixo — a exclusão reversível da plataforma (D116).
 *
 *  > *"O lixo é uma página à parte. Como é custo para o programa, terá uma
 *  > paywall. O lixo é apagado depois de 15 dias. O lixo pode ser restaurado
 *  > através da página de lixo."* — decisão do dono, 13/09/2026.
 *
 *  **É uma página de plataforma dentro do tenant**, e não um módulo: ela lista
 *  obra, cliente, fornecedor, funcionário, conta e lead no mesmo lugar, porque a
 *  pergunta que a traz aqui ("o que foi apagado?") não respeita fronteira de
 *  módulo. Por isso não há entitlement na rota — o que há é a permissão
 *  `plataforma.lixo.view`, do `gestor_lixo`.
 *
 *  **O relógio é o assunto da tela.** A coluna que mais importa não é o que foi
 *  apagado, é *quanto tempo falta* — depois do prazo do plano não há mais o que
 *  restaurar. Por isso o prazo é a primeira informação depois do nome, e o que
 *  vence em 3 dias ou menos vem marcado.
 */
import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Trash2, AlertTriangle } from 'lucide-react'
import { Btn, Card, Empty, KpiTile, Loading, Modal, Pill, SectionHead } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import * as api from '../api'
import type { ItemDoLixo } from '../api'

const CHAVE = ['lixo'] as const

function dataCurta(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR')
}

/** O prazo em palavras — e vencido não vira zero, que esconderia o caso a investigar. */
function prazo(item: ItemDoLixo) {
  if (item.dias_para_purga === null) return { texto: '—', alerta: false }
  if (item.dias_para_purga < 0) return { texto: 'vencido', alerta: true }
  if (item.dias_para_purga === 0) return { texto: 'hoje', alerta: true }
  return {
    texto: `${item.dias_para_purga} dia${item.dias_para_purga === 1 ? '' : 's'}`,
    alerta: item.dias_para_purga <= 3,
  }
}

export default function LixoPage() {
  const { hasPermission } = useAuth()
  const qc = useQueryClient()
  const [tipo, setTipo] = useState('')
  const [estado, setEstado] = useState<'ativo' | 'todos'>('ativo')
  const [aPurgar, setAPurgar] = useState<ItemDoLixo | null>(null)
  const [confirmacao, setConfirmacao] = useState('')

  const podeRestaurar = hasPermission('plataforma.lixo.restaurar')
  const podePurgar = hasPermission('plataforma.lixo.purgar')

  const params = useMemo(() => {
    const p: Record<string, unknown> = {}
    if (tipo) p.alvo_tipo__model = tipo
    if (estado === 'todos') p.estado = 'todos'
    return p
  }, [tipo, estado])

  const lista = useQuery({
    queryKey: [...CHAVE, 'lista', params],
    queryFn: () => api.listar(params),
    placeholderData: keepPreviousData,
  })
  const resumo = useQuery({ queryKey: [...CHAVE, 'resumo'], queryFn: api.resumo })

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: CHAVE })
  }

  const mRestaurar = useMutation({ mutationFn: api.restaurar, onSuccess: invalidar })
  const mPurgar = useMutation({
    mutationFn: api.purgar,
    onSuccess: () => {
      invalidar()
      setAPurgar(null)
      setConfirmacao('')
    },
  })

  const itens = lista.data?.results ?? []
  const r = resumo.data

  return (
    <div style={{ height: '100%', overflowY: 'auto' }}>
      <div style={{ padding: '22px 26px 40px', maxWidth: 1180 }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 680, color: 'var(--ink)', margin: 0 }}>Lixo</h1>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 5, maxWidth: 780 }}>
            O que foi excluído permanece aqui ate o final do prazo contratado pelo plano.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
          <KpiTile label="Na lixeira" valor={r?.total ?? 0} base="itens recuperáveis" />
          {/* Normalmente zero. Diferente de zero por muito tempo significa que a
              varredura parou — e silêncio de varredura foi o defeito do D21. */}
          {!!r?.vencidos_nao_purgados && (
            <KpiTile label="Vencidos, ainda aqui" valor={r.vencidos_nao_purgados} base="a varredura não levou" />
          )}
          {!!r?.com_falha && <KpiTile label="Com falha na purga" valor={r.com_falha} base="o banco recusou" />}
        </div>

        <Card>
          <SectionHead
            sub="Restaurar devolve o registro inteiro, com tudo que dependia dele."
            right={
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <select
                  value={tipo}
                  onChange={e => setTipo(e.target.value)}
                  style={estiloCampo}
                >
                  <option value="">Todos os tipos</option>
                  {(r?.por_tipo ?? []).map(t => (
                    <option key={t.modelo} value={t.modelo.split('.')[1]}>
                      {t.modelo.split('.')[1]} ({t.quantidade})
                    </option>
                  ))}
                </select>
                <select
                  value={estado}
                  onChange={e => setEstado(e.target.value as 'ativo' | 'todos')}
                  style={estiloCampo}
                >
                  <option value="ativo">Na lixeira</option>
                  <option value="todos">Histórico completo</option>
                </select>
              </div>
            }
          >
            Itens excluídos
          </SectionHead>

          {lista.isLoading ? (
            <Loading o="a lixeira" />
          ) : itens.length === 0 ? (
            <Empty>
              Nada na lixeira. O que for excluído aparece aqui e pode ser restaurado
              dentro do prazo do plano.
            </Empty>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--ink-3)' }}>
                    <th style={th}>Item</th>
                    <th style={th}>Tipo</th>
                    <th style={th}>Purga em</th>
                    <th style={th}>Excluído por</th>
                    <th style={th}>Quando</th>
                    <th style={th} />
                  </tr>
                </thead>
                <tbody>
                  {itens.map(item => {
                    const p = prazo(item)
                    return (
                      <tr key={item.lixo_id} style={{ borderTop: '1px solid var(--line)' }}>
                        <td style={td}>
                          <div style={{ color: 'var(--ink)', fontWeight: 560 }}>
                            {item.rotulo || `#${item.alvo_id}`}
                          </div>
                          {item.motivo && (
                            <div style={{ color: 'var(--ink-3)', fontSize: 12, marginTop: 2 }}>
                              {item.motivo}
                            </div>
                          )}
                          {/* A recusa da purga aparece ao lado do item, e não num
                              log — quem pode resolver é quem está olhando aqui. */}
                          {item.falha_na_purga && (
                            <div
                              style={{
                                color: 'var(--danger)', fontSize: 12, marginTop: 4,
                                display: 'flex', gap: 5, alignItems: 'flex-start',
                              }}
                            >
                              <AlertTriangle size={13} style={{ marginTop: 1, flexShrink: 0 }} />
                              <span>Não foi possível apagar: {item.falha_na_purga}</span>
                            </div>
                          )}
                        </td>
                        <td style={td}>{item.modelo_rotulo}</td>
                        <td style={td}>
                          {item.estado === 'no_lixo' ? (
                            <Pill kind={p.alerta ? 'danger' : 'slate'}>{p.texto}</Pill>
                          ) : (
                            <Pill kind="slate">
                              {item.estado === 'restaurado' ? 'restaurado' : 'purgado'}
                            </Pill>
                          )}
                        </td>
                        <td style={td}>{item.excluido_por_nome || '—'}</td>
                        <td style={td}>{dataCurta(item.excluido_em)}</td>
                        <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {item.estado === 'no_lixo' && (
                            <div style={{ display: 'inline-flex', gap: 6 }}>
                              {podeRestaurar && (
                                <Btn
                                  tam="sm"
                                  variant="primary"
                                  disabled={mRestaurar.isPending}
                                  onClick={() => mRestaurar.mutate(item.lixo_id)}
                                >
                                  <RotateCcw size={13} /> Restaurar
                                </Btn>
                              )}
                              {podePurgar && (
                                <Btn tam="sm" variant="perigo" onClick={() => setAPurgar(item)}>
                                  <Trash2 size={13} />
                                </Btn>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {aPurgar && (
        <Modal
          titulo="Apagar definitivamente"
          onClose={() => {
            setAPurgar(null)
            setConfirmacao('')
          }}
          largura={470}
          rodape={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn
                onClick={() => {
                  setAPurgar(null)
                  setConfirmacao('')
                }}
              >
                Cancelar
              </Btn>
              {/* A digitação do nome é a trava: este botão apaga antes do prazo
                  que o plano prometeu, e não há desfazer do outro lado. */}
              <Btn
                variant="perigo"
                disabled={confirmacao.trim() !== aPurgar.rotulo || mPurgar.isPending}
                onClick={() => mPurgar.mutate(aPurgar.lixo_id)}
              >
                Apagar para sempre
              </Btn>
            </div>
          }
        >
          <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>
            <b>{aPurgar.rotulo}</b> seria apagado sozinho em{' '}
            <b>{prazo(aPurgar).texto}</b>. Apagar agora é irreversível — e leva junto o
            que depende deste registro.
          </p>
          <p style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
            Para confirmar, digite o nome do item:
          </p>
          <input
            value={confirmacao}
            onChange={e => setConfirmacao(e.target.value)}
            placeholder={aPurgar.rotulo}
            style={{ ...estiloCampo, width: '100%' }}
          />
          {mPurgar.isError && (
            <p style={{ color: 'var(--danger)', fontSize: 12.5 }}>
              Não foi possível apagar. Veja o motivo na linha do item.
            </p>
          )}
        </Modal>
      )}
    </div>
  )
}

const th: React.CSSProperties = { padding: '8px 10px', fontWeight: 560, fontSize: 12 }
const td: React.CSSProperties = { padding: '10px', color: 'var(--ink-2)', verticalAlign: 'top' }
const estiloCampo: React.CSSProperties = {
  background: 'var(--surface-2)',
  color: 'var(--ink)',
  border: '1px solid var(--line)',
  borderRadius: 7,
  padding: '6px 9px',
  fontSize: 12.5,
}
