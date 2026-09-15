import { useMemo, useState } from 'react'
import {
  AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Plus, ShieldCheck, Trash2,
  UserCheck,
} from 'lucide-react'
import { Btn, Card, Empty, Loading, Modal, Pill } from '@/components/malha'
import { useAprovacoes, type Degrau, type Fluxo } from '../hooks/useAprovacoes'

/**
 * **Administração → Aprovações** — quantas assinaturas o dinheiro atravessa.
 *
 * *(Fecha a [D130](../../../../docs/pendencias.md): a máquina nasceu na PDCA.0
 * com API completa e nenhuma tela. Enquanto ela não tinha cliente real isso era
 * um seam esperando uso; com a PDCA.3 ela passou a decidir se um título a pagar
 * existe, e a ausência da tela virou um documento parado sem caminho.)*
 *
 * **Por que mora na Administração, e não dentro do módulo que ela aprova.** É a
 * mesma classe de ato que `admin/papeis`: definir alçada é decidir quem manda no
 * dinheiro, como definir papel é decidir quem vê o quê. Uma persona de fábrica
 * com esse verbo poderia rebaixar a escada que a controla — por isso a
 * permissão é `plataforma.fluxo_aprovacao.edit`, do administrador do tenant.
 *
 * **O que esta tela existe para tornar descobrível**, e que era invisível até
 * ela: o **autoatesto**. A regra padrão é *quem executa não aprova*, e ela
 * protege a empresa; mas na obra pequena o mesmo engenheiro apura e assina, e a
 * planta chama isso de *"escolha escrita do cliente"*. Escrita é aqui.
 */

export default function AprovacoesPage() {
  const {
    fluxos, alvos, catalogo, carregando, erro,
    criarFluxo, atualizarFluxo, excluirFluxo,
    criarDegrau, excluirDegrau, reordenarDegraus, validar,
  } = useAprovacoes()

  const [criando, setCriando] = useState(false)
  const [degrauEm, setDegrauEm] = useState<Fluxo | null>(null)
  const [diagnostico, setDiagnostico] = useState<Record<number, string[]>>({})
  const [falha, setFalha] = useState<string | null>(null)

  /** Os códigos de permissão que existem, achatados do catálogo da IAM. Sem ele
   *  (403 para quem não é admin) o seletor do degrau vira texto livre, em vez de
   *  a tela inteira quebrar. */
  const permissoes = useMemo(() => {
    const todas: { code: string; nome: string; modulo: string }[] = []
    for (const m of catalogo?.modulos ?? []) {
      for (const p of m.permissoes) {
        todas.push({ code: p.code, nome: p.nome, modulo: m.modulo })
      }
    }
    return todas.sort((a, b) => a.code.localeCompare(b.code))
  }, [catalogo])

  async function comErro(acao: () => Promise<unknown>) {
    setFalha(null)
    try { await acao() } catch (e) {
      const corpo = (e as { response?: { data?: unknown } })?.response?.data
      setFalha(
        typeof corpo === 'string' ? corpo
          : corpo ? JSON.stringify(corpo) : 'Não deu para concluir.',
      )
    }
  }

  if (carregando) return <Loading o="as escadas de aprovação" />

  return (
    <div style={{ padding: '26px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Aprovações</h1>
          <p style={{ margin: '6px 0 0', color: 'var(--ink-2)', fontSize: 14, maxWidth: 680 }}>
            Quantas assinaturas um documento atravessa antes de virar dinheiro.
            Cada degrau exige uma <strong>permissão</strong>, e não uma pessoa —
            assim a escada continua de pé quando alguém sai de férias ou muda de
            função. Documento sem escada configurada é aprovado em um passo, por
            quem tiver o verbo de atestar.
          </p>
        </div>
        <Btn variant="brand" onClick={() => setCriando(true)}>
          <Plus size={15} /> Nova escada
        </Btn>
      </header>

      {erro && (
        <div style={avisoErro}>{erro}</div>
      )}
      {falha && <div style={avisoErro}>{falha}</div>}

      {fluxos.length === 0 && !erro ? (
        <Empty>
          Nenhuma escada configurada. Enquanto não houver, cada documento é
          aprovado <strong>em um passo</strong> — o que é legítimo para a empresa
          pequena, mas não separa quem apura de quem decide.
        </Empty>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {fluxos.map(fluxo => (
            <Card key={fluxo.fluxo_id}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <ShieldCheck size={16} style={{ color: 'var(--ink-3)' }} />
                    <strong style={{ fontSize: 16 }}>{fluxo.nome}</strong>
                    <Pill kind={fluxo.ativo ? 'good' : 'slate'}>
                      {fluxo.ativo ? 'Ativo' : 'Inativo'}
                    </Pill>
                    {fluxo.padrao && <Pill kind="info">Padrão deste documento</Pill>}
                    {fluxo.permite_autoatesto && (
                      <Pill kind="accent">Autoatesto permitido</Pill>
                    )}
                  </div>
                  <p style={{ margin: '5px 0 0', color: 'var(--ink-2)', fontSize: 13 }}>
                    Aprova: <strong>{fluxo.alvo_rotulo}</strong> · código{' '}
                    <code style={{ fontFamily: 'var(--mono)' }}>{fluxo.codigo}</code>
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <Btn
                    tam="sm"
                    id={`conferir-${fluxo.fluxo_id}`}
                    onClick={() => comErro(async () => {
                      const r = await validar(fluxo.fluxo_id)
                      setDiagnostico(d => ({
                        ...d,
                        [fluxo.fluxo_id]: r.valido ? [] : r.problemas,
                      }))
                    })}
                  >
                    Conferir
                  </Btn>
                  <Btn tam="sm" onClick={() => setDegrauEm(fluxo)}>
                    <Plus size={14} /> Degrau
                  </Btn>
                  <Btn
                    tam="sm" variant="perigo"
                    onClick={() => comErro(() => excluirFluxo(fluxo.fluxo_id))}
                  >
                    <Trash2 size={14} />
                  </Btn>
                </div>
              </div>

              {diagnostico[fluxo.fluxo_id] !== undefined && (
                <div style={{
                  marginTop: 10, padding: '8px 10px', borderRadius: 8, fontSize: 12.5,
                  background: diagnostico[fluxo.fluxo_id].length
                    ? 'var(--danger-soft)' : 'var(--good-soft)',
                  color: diagnostico[fluxo.fluxo_id].length
                    ? 'var(--danger-ink)' : 'var(--good-ink)',
                }}>
                  {diagnostico[fluxo.fluxo_id].length ? (
                    <>
                      <AlertTriangle size={13} style={{ verticalAlign: '-2px' }} />{' '}
                      {diagnostico[fluxo.fluxo_id].join(' · ')}
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={13} style={{ verticalAlign: '-2px' }} />{' '}
                      A escada está utilizável.
                    </>
                  )}
                </div>
              )}

              {/* --- O interruptor que esta tela existe para tornar visível --- */}
              <label style={{
                display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 12,
                padding: '10px 12px', borderRadius: 8, background: 'var(--surface-2)',
                cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  // Id estável por fluxo: o `<label>` que o envolve já faz o
                  // clique funcionar no texto inteiro, e o id dá a cada
                  // interruptor um endereço próprio numa tela com várias
                  // escadas — o que um seletor por texto não consegue.
                  id={`autoatesto-${fluxo.fluxo_id}`}
                  checked={fluxo.permite_autoatesto}
                  style={{ marginTop: 3 }}
                  onChange={e => comErro(() => atualizarFluxo(fluxo.fluxo_id, {
                    permite_autoatesto: e.target.checked,
                  }))}
                />
                <span style={{ fontSize: 13, lineHeight: 1.5 }}>
                  <strong>Permitir que quem solicita ateste o próprio pedido</strong>
                  <span style={{ display: 'block', color: 'var(--ink-2)', marginTop: 3 }}>
                    O padrão é <strong>não</strong>: quem executa não aprova, e é
                    essa separação que protege a empresa. Ligue apenas se, na sua
                    operação, a mesma pessoa realmente apura e assina — é o caso da
                    obra pequena com um engenheiro só. A decisão fica registrada
                    aqui, e cada atesto continua guardando autor e data.
                  </span>
                </span>
              </label>

              {/* --- Os degraus --- */}
              <div style={{ marginTop: 12 }}>
                {fluxo.niveis.length === 0 ? (
                  <p style={{ fontSize: 12.5, color: 'var(--danger-ink)', margin: 0 }}>
                    Escada sem degrau nenhum — ela não aprova nada até ganhar o primeiro.
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {[...fluxo.niveis].sort((a, b) => a.ordem - b.ordem).map((d, i, todos) => (
                      <LinhaDegrau
                        key={d.nivel_id}
                        degrau={d}
                        primeiro={i === 0}
                        ultimo={i === todos.length - 1}
                        onSubir={() => comErro(() => {
                          const ids = todos.map(n => n.nivel_id)
                          ;[ids[i - 1], ids[i]] = [ids[i], ids[i - 1]]
                          return reordenarDegraus(fluxo.fluxo_id, ids)
                        })}
                        onDescer={() => comErro(() => {
                          const ids = todos.map(n => n.nivel_id)
                          ;[ids[i], ids[i + 1]] = [ids[i + 1], ids[i]]
                          return reordenarDegraus(fluxo.fluxo_id, ids)
                        })}
                        onExcluir={() => comErro(() => excluirDegrau(d.nivel_id))}
                      />
                    ))}
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {criando && (
        <ModalFluxo
          alvos={alvos}
          onClose={() => setCriando(false)}
          onSalvar={async dados => {
            await comErro(() => criarFluxo(dados))
            setCriando(false)
          }}
        />
      )}

      {degrauEm && (
        <ModalDegrau
          fluxo={degrauEm}
          permissoes={permissoes}
          onClose={() => setDegrauEm(null)}
          onSalvar={async dados => {
            await comErro(() => criarDegrau(dados))
            setDegrauEm(null)
          }}
        />
      )}
    </div>
  )
}

function LinhaDegrau({ degrau, primeiro, ultimo, onSubir, onDescer, onExcluir }: {
  degrau: Degrau; primeiro: boolean; ultimo: boolean
  onSubir: () => void; onDescer: () => void; onExcluir: () => void
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
      border: '1px solid var(--line)', borderRadius: 8, fontSize: 13,
    }}>
      <span style={{
        width: 24, height: 24, borderRadius: 999, background: 'var(--brand)',
        color: 'var(--brand-ink)', display: 'inline-flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 12, fontWeight: 600, flexShrink: 0,
      }}>
        {degrau.ordem}
      </span>
      <strong>{degrau.nome}</strong>
      <span style={{ color: 'var(--ink-2)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <UserCheck size={13} />
        exige <code style={{ fontFamily: 'var(--mono)' }}>{degrau.permissao_exigida}</code>
      </span>
      <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
        <Btn tam="sm" disabled={primeiro} onClick={onSubir}><ArrowUp size={13} /></Btn>
        <Btn tam="sm" disabled={ultimo} onClick={onDescer}><ArrowDown size={13} /></Btn>
        <Btn tam="sm" variant="perigo" onClick={onExcluir}><Trash2 size={13} /></Btn>
      </span>
    </div>
  )
}

function ModalFluxo({ alvos, onClose, onSalvar }: {
  alvos: { id: number; codigo: string; rotulo: string }[]
  onClose: () => void
  onSalvar: (dados: Partial<Fluxo>) => void
}) {
  const [f, setF] = useState({
    codigo: '', nome: '', alvo: alvos[0]?.id ?? 0,
    padrao: true, ativo: true, permite_autoatesto: false, descricao: '',
  })
  return (
    <Modal
      titulo="Nova escada de aprovação"
      onClose={onClose}
      largura={560}
      rodape={
        <>
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn
            variant="brand"
            disabled={!f.nome.trim() || !f.codigo.trim() || !f.alvo}
            onClick={() => onSalvar(f)}
          >
            Criar
          </Btn>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Campo rotulo="Que documento esta escada aprova">
          <select
            value={f.alvo}
            onChange={e => setF({ ...f, alvo: Number(e.target.value) })}
            style={entrada}
          >
            {alvos.map(a => (
              <option key={a.id} value={a.id}>{a.rotulo} ({a.codigo})</option>
            ))}
          </select>
          <p style={ajuda}>
            A lista traz os documentos que o sistema sabe aprovar. Um módulo entra
            aqui quando se candidata a isso — não há catálogo escrito à mão.
          </p>
        </Campo>
        <Campo rotulo="Nome">
          <input
            value={f.nome}
            onChange={e => setF({ ...f, nome: e.target.value })}
            placeholder="Ex.: Aprovação de medição de empreiteiro"
            style={entrada}
          />
        </Campo>
        <Campo rotulo="Código">
          <input
            value={f.codigo}
            onChange={e => setF({ ...f, codigo: e.target.value })}
            placeholder="medicao-obra"
            style={entrada}
          />
          <p style={ajuda}>Curto e sem espaço — é como o sistema se refere a ela.</p>
        </Campo>
        <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13 }}>
          <input
            type="checkbox" checked={f.padrao} style={{ marginTop: 3 }}
            onChange={e => setF({ ...f, padrao: e.target.checked })}
          />
          <span>
            <strong>Usar como padrão para este documento</strong>
            <span style={{ display: 'block', color: 'var(--ink-2)', marginTop: 2 }}>
              É a escada que os documentos novos entram automaticamente. Só uma por
              tipo de documento.
            </span>
          </span>
        </label>
      </div>
    </Modal>
  )
}

function ModalDegrau({ fluxo, permissoes, onClose, onSalvar }: {
  fluxo: Fluxo
  permissoes: { code: string; nome: string; modulo: string }[]
  onClose: () => void
  onSalvar: (dados: Partial<Degrau>) => void
}) {
  const proxima = Math.max(0, ...fluxo.niveis.map(n => n.ordem)) + 1
  const [d, setD] = useState({
    fluxo: fluxo.fluxo_id, ordem: proxima, nome: '',
    permissao_exigida: permissoes[0]?.code ?? '',
  })
  return (
    <Modal
      titulo={`Degrau ${proxima} de "${fluxo.nome}"`}
      onClose={onClose}
      largura={560}
      rodape={
        <>
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn
            variant="brand"
            disabled={!d.nome.trim() || !d.permissao_exigida.trim()}
            onClick={() => onSalvar(d)}
          >
            Acrescentar
          </Btn>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Campo rotulo="Nome do degrau">
          <input
            value={d.nome}
            onChange={e => setD({ ...d, nome: e.target.value })}
            placeholder="Ex.: Gerente de contrato"
            style={entrada}
          />
        </Campo>
        <Campo rotulo="Permissão que este degrau exige">
          {permissoes.length > 0 ? (
            <select
              value={d.permissao_exigida}
              onChange={e => setD({ ...d, permissao_exigida: e.target.value })}
              style={entrada}
            >
              {permissoes.map(p => (
                <option key={p.code} value={p.code}>{p.code} — {p.nome}</option>
              ))}
            </select>
          ) : (
            <input
              value={d.permissao_exigida}
              onChange={e => setD({ ...d, permissao_exigida: e.target.value })}
              placeholder="pdca.medicao.atestar"
              style={entrada}
            />
          )}
          <p style={ajuda}>
            <strong>É uma permissão, não uma pessoa.</strong> Quem tiver este verbo
            assina o degrau — assim a escada continua de pé quando alguém sai de
            férias, e você muda quem assina mexendo no papel, não na escada.
          </p>
        </Campo>
      </div>
    </Modal>
  )
}

const entrada: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5,
}
const ajuda: React.CSSProperties = {
  margin: '5px 0 0', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.45,
}
const avisoErro: React.CSSProperties = {
  padding: '10px 12px', borderRadius: 8, fontSize: 13,
  background: 'var(--danger-soft)', color: 'var(--danger-ink)',
}

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 4 }}>
        {rotulo}
      </label>
      {children}
    </div>
  )
}
