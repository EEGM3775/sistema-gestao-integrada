import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, Copy, Trash2 } from 'lucide-react'
import { Btn, Card, Empty, Loading, Modal, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import {
  useAtualizarItemDoModelo, useAtualizarModelo, useCriarItemDoModelo, useCriarModelo,
  useDuplicarModelo, useExcluirItemDoModelo, useExcluirModelo, useModelo, useModelos,
} from '../hooks'
import { Ajuda, Campo, Escolhas, FaixaDeErro, Grupo, Linha } from './Formulario'
import type { DominioVerificacao, ItemModeloVerificacao, ModeloVerificacao } from '../types'
import { entrada } from '../estilos'
import { primeiraFrase } from '../formato'

const DOMINIOS: { valor: DominioVerificacao; rotulo: string }[] = [
  { valor: 'qualidade', rotulo: 'Qualidade (FVS)' },
  { valor: 'seguranca', rotulo: 'Segurança' },
  { valor: 'ambiental', rotulo: 'Ambiental' },
  { valor: 'entrega', rotulo: 'Entrega / vistoria' },
]

/** **A biblioteca de fichas em branco da empresa.**
 *
 *  Configuração, e não cadência: por isso mora dentro do posto que a consome,
 *  e não num item de menu. Nasce **vazia** de propósito — o que se confere em
 *  cada serviço é o método do cliente, e um modelo nosso pré-carregado seria
 *  chute com cara de norma. */
export function BibliotecaDeModelos({
  modeloId, aoAbrir, aoVoltar,
}: {
  modeloId: number | null
  aoAbrir: (id: number) => void
  aoVoltar: () => void
}) {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('pdca.verificacao.modelo_edit')
  const modelos = useModelos(true, modeloId == null)
  const [criando, setCriando] = useState(false)

  if (modeloId != null) {
    return <EditorDeModelo modeloId={modeloId} podeEditar={podeEditar} aoVoltar={aoVoltar} aoAbrir={aoAbrir} />
  }

  const lista = modelos.data ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 960 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 12.5, color: 'var(--ink-3)', flex: 1, lineHeight: 1.55 }}>
          O modelo é o método da empresa: o que se confere em cada serviço e com que
          critério. Mudar um modelo não reescreve as fichas que já saíram dele.
        </span>
        {podeEditar && <Btn variant="primary" onClick={() => setCriando(true)}>Novo modelo</Btn>}
      </div>

      {modelos.isLoading ? (
        <Loading o="os modelos da empresa" />
      ) : lista.length === 0 ? (
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              A empresa ainda não tem modelo de ficha.
              {!podeEditar && ' Quem monta modelo é quem tem a permissão de editar modelos de verificação.'}
            </span>
            {podeEditar && <Btn variant="primary" onClick={() => setCriando(true)}>Montar o primeiro modelo</Btn>}
          </Empty>
        </Card>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {lista.map((m) => (
            <button
              key={m.modelo_id}
              type="button"
              onClick={() => aoAbrir(m.modelo_id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, width: '100%',
                padding: '11px 14px', borderTop: '1px solid var(--line-2)',
                background: 'transparent', border: 'none', borderTopStyle: 'solid',
                cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
                opacity: m.ativo ? 1 : 0.65,
              }}
            >
              <span style={{ fontFamily: 'var(--mono)', fontSize: 12.5, color: 'var(--ink-3)', minWidth: 80 }}>
                {m.codigo}
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 13.5, color: 'var(--ink)', fontWeight: 650 }}>{m.nome}</span>
                <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>
                  {m.dominio_rotulo} · {m.itens_count} {m.itens_count === 1 ? 'pergunta' : 'perguntas'}
                  {m.aplicacoes > 0 && ` · aplicado ${m.aplicacoes} ${m.aplicacoes === 1 ? 'vez' : 'vezes'}`}
                </span>
              </span>
              {!m.ativo && <Pill kind="slate">desativado</Pill>}
            </button>
          ))}
        </Card>
      )}

      {criando && (
        <NovoModelo
          aoFechar={() => setCriando(false)}
          aoCriar={(m) => { setCriando(false); aoAbrir(m.modelo_id) }}
        />
      )}
    </div>
  )
}

function NovoModelo({
  aoFechar, aoCriar,
}: { aoFechar: () => void; aoCriar: (m: ModeloVerificacao) => void }) {
  const criar = useCriarModelo()
  const [codigo, setCodigo] = useState('')
  const [nome, setNome] = useState('')
  const [dominio, setDominio] = useState<DominioVerificacao>('qualidade')
  const [descricao, setDescricao] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  return (
    <Modal
      titulo="Novo modelo de ficha"
      onClose={aoFechar}
      largura={560}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={!codigo.trim() || !nome.trim() || criar.isPending}
            onClick={async () => {
              setErro(null)
              try {
                aoCriar(await criar.mutateAsync({
                  codigo: codigo.trim(), nome: nome.trim(), dominio, descricao: descricao.trim(),
                }))
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            Criar e montar as perguntas
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <FaixaDeErro>{erro}</FaixaDeErro>
        <Linha>
          <Campo rotulo="Código">
            <input value={codigo} onChange={(e) => setCodigo(e.target.value)} style={entrada} autoFocus />
            <Ajuda>O da empresa — ex.: FVS-07.</Ajuda>
          </Campo>
          <Campo rotulo="Nome" larga>
            <input value={nome} onChange={(e) => setNome(e.target.value)} style={entrada} />
          </Campo>
        </Linha>
        <Grupo rotulo="Domínio">
          <Escolhas valor={dominio} aoEscolher={setDominio} opcoes={DOMINIOS} />
        </Grupo>
        <Campo rotulo="Para que serve (opcional)">
          <input value={descricao} onChange={(e) => setDescricao(e.target.value)} style={entrada} />
        </Campo>
      </div>
    </Modal>
  )
}

/** O editor das perguntas. **Grava por campo, ao sair dele** — o modelo é
 *  montado uma pergunta por vez, e um "salvar o modelo" no fim é o que se
 *  perde ao fechar a aba. */
function EditorDeModelo({
  modeloId, podeEditar, aoVoltar, aoAbrir,
}: {
  modeloId: number
  podeEditar: boolean
  aoVoltar: () => void
  aoAbrir: (id: number) => void
}) {
  const modelo = useModelo(modeloId)
  const atualizar = useAtualizarModelo()
  const excluir = useExcluirModelo()
  const duplicar = useDuplicarModelo()
  const criarItem = useCriarItemDoModelo()
  const atualizarItem = useAtualizarItemDoModelo()
  const [erro, setErro] = useState<string | null>(null)
  const [novo, setNovo] = useState('')
  const [copiando, setCopiando] = useState(false)
  const [codigoDaCopia, setCodigoDaCopia] = useState('')

  if (modelo.isLoading) return <Loading o="o modelo" />
  if (modelo.isError || !modelo.data) {
    return <Card><Empty>Este modelo não foi encontrado.</Empty></Card>
  }

  const dados = modelo.data
  const itens = [...(dados.itens ?? [])].sort((a, b) => a.ordem - b.ordem)

  async function executar(acao: () => Promise<unknown>) {
    setErro(null)
    try { await acao() } catch (e) { setErro(primeiraFrase(e)) }
  }

  async function trocar(a: ItemModeloVerificacao, b: ItemModeloVerificacao) {
    await executar(async () => {
      await atualizarItem.mutateAsync({ id: a.item_modelo_id, corpo: { ordem: b.ordem } })
      await atualizarItem.mutateAsync({ id: b.item_modelo_id, corpo: { ordem: a.ordem } })
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 960 }}>
      <button
        type="button" onClick={aoVoltar}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 3, alignSelf: 'flex-start',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 12, color: 'var(--ink-3)',
        }}
      >
        <ChevronLeft size={13} />
        Todos os modelos
      </button>

      <Card>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--ink-3)' }}>{dados.codigo}</span>
          <Pill kind="slate">{dados.dominio_rotulo}</Pill>
          {!dados.ativo && <Pill kind="slate">desativado</Pill>}
          {dados.aplicacoes > 0 && (
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              aplicado {dados.aplicacoes} {dados.aplicacoes === 1 ? 'vez' : 'vezes'}
            </span>
          )}
        </div>

        {podeEditar ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
            <CampoQueGravaAoSair
              rotulo="Nome" valor={dados.nome}
              aoGravar={(nome) => executar(() => atualizar.mutateAsync({ id: modeloId, corpo: { nome } }))}
            />
            <CampoQueGravaAoSair
              rotulo="Para que serve" valor={dados.descricao}
              aoGravar={(descricao) => executar(() => atualizar.mutateAsync({ id: modeloId, corpo: { descricao } }))}
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <Btn
                tam="sm"
                onClick={() => executar(() => atualizar.mutateAsync({ id: modeloId, corpo: { ativo: !dados.ativo } }))}
              >
                {dados.ativo ? 'Desativar' : 'Reativar'}
              </Btn>
              <Btn tam="sm" onClick={() => setCopiando(true)}>
                <Copy size={13} /> Duplicar
              </Btn>
              {dados.aplicacoes === 0 && (
                <Btn
                  tam="sm" variant="perigo"
                  onClick={() => executar(async () => { await excluir.mutateAsync(modeloId); aoVoltar() })}
                >
                  <Trash2 size={13} /> Excluir
                </Btn>
              )}
            </div>
            {dados.aplicacoes > 0 && (
              <Ajuda>
                Um modelo já aplicado não se exclui: as fichas dele perderiam o nome do
                que responderam. Desative — ele sai da escolha e continua legível.
              </Ajuda>
            )}
            {copiando && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                <Campo rotulo="Código da cópia">
                  <input value={codigoDaCopia} onChange={(e) => setCodigoDaCopia(e.target.value)} style={entrada} autoFocus />
                </Campo>
                <Btn tam="sm" onClick={() => setCopiando(false)}>Voltar</Btn>
                <Btn
                  tam="sm" variant="primary" disabled={!codigoDaCopia.trim() || duplicar.isPending}
                  onClick={() => executar(async () => {
                    const copia = await duplicar.mutateAsync({ id: modeloId, codigo: codigoDaCopia.trim() })
                    setCopiando(false)
                    setCodigoDaCopia('')
                    aoAbrir(copia.modelo_id)
                  })}
                >
                  Duplicar
                </Btn>
              </div>
            )}
          </div>
        ) : (
          <>
            <h2 style={{ margin: '10px 0 0', fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>{dados.nome}</h2>
            {dados.descricao && <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--ink-2)' }}>{dados.descricao}</p>}
          </>
        )}
        <div style={{ marginTop: erro ? 10 : 0 }}><FaixaDeErro>{erro}</FaixaDeErro></div>
      </Card>

      <Card pad={false} style={{ overflow: 'hidden' }}>
        {itens.length === 0 && (
          <div style={{ padding: 16, fontSize: 13, color: 'var(--ink-3)' }}>
            Nenhuma pergunta ainda. Escreva a primeira abaixo.
          </div>
        )}
        {itens.map((item, i) => (
          <PerguntaDoModelo
            key={item.item_modelo_id}
            item={item}
            podeEditar={podeEditar}
            anterior={itens[i - 1]}
            seguinte={itens[i + 1]}
            aoTrocar={trocar}
            aoErro={setErro}
          />
        ))}
        {podeEditar && (
          <div style={{ display: 'flex', gap: 8, padding: '12px 14px', borderTop: '1px solid var(--line-2)', background: 'var(--inset)' }}>
            <input
              value={novo}
              onChange={(e) => setNovo(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && novo.trim()) {
                  e.preventDefault()
                  void executar(async () => {
                    await criarItem.mutateAsync({
                      modelo: modeloId, texto: novo.trim(),
                      ordem: (itens[itens.length - 1]?.ordem ?? 0) + 1,
                    })
                    setNovo('')
                  })
                }
              }}
              placeholder="Nova pergunta — ex.: o prumo está dentro de 3 mm por metro?"
              aria-label="Nova pergunta"
              style={entrada}
            />
            <Btn
              variant="primary" disabled={!novo.trim() || criarItem.isPending}
              onClick={() => executar(async () => {
                await criarItem.mutateAsync({
                  modelo: modeloId, texto: novo.trim(),
                  ordem: (itens[itens.length - 1]?.ordem ?? 0) + 1,
                })
                setNovo('')
              })}
            >
              Acrescentar
            </Btn>
          </div>
        )}
      </Card>
    </div>
  )
}

function PerguntaDoModelo({
  item, podeEditar, anterior, seguinte, aoTrocar, aoErro,
}: {
  item: ItemModeloVerificacao
  podeEditar: boolean
  anterior?: ItemModeloVerificacao
  seguinte?: ItemModeloVerificacao
  aoTrocar: (a: ItemModeloVerificacao, b: ItemModeloVerificacao) => void
  aoErro: (e: string | null) => void
}) {
  const atualizar = useAtualizarItemDoModelo()
  const excluir = useExcluirItemDoModelo()

  async function gravar(corpo: Partial<ItemModeloVerificacao>) {
    aoErro(null)
    try { await atualizar.mutateAsync({ id: item.item_modelo_id, corpo }) } catch (e) { aoErro(primeiraFrase(e)) }
  }

  if (!podeEditar) {
    return (
      <div style={{ display: 'flex', gap: 12, padding: '11px 14px', borderTop: '1px solid var(--line-2)' }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-3)', minWidth: 22 }}>{item.ordem}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13.5, color: 'var(--ink)' }}>
            {item.texto}{item.obrigatorio && <span style={{ color: 'var(--danger-ink)' }}> *</span>}
          </div>
          {item.criterio && <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>Critério: {item.criterio}</div>}
        </div>
        {item.exige_foto && <Pill kind="slate">pede foto</Pill>}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 10, padding: '11px 14px', borderTop: '1px solid var(--line-2)', alignItems: 'flex-start' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 4 }}>
        <IconeBotao rotulo="Subir" disabled={!anterior} onClick={() => anterior && aoTrocar(item, anterior)}><ArrowUp size={13} /></IconeBotao>
        <IconeBotao rotulo="Descer" disabled={!seguinte} onClick={() => seguinte && aoTrocar(item, seguinte)}><ArrowDown size={13} /></IconeBotao>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <CampoQueGravaAoSair rotulo={`Pergunta ${item.ordem}`} valor={item.texto} aoGravar={(texto) => gravar({ texto })} />
        <CampoQueGravaAoSair rotulo="Critério de aceite" valor={item.criterio} aoGravar={(criterio) => gravar({ criterio })} />
        <div style={{ display: 'flex', gap: 14, fontSize: 12.5, color: 'var(--ink-2)' }}>
          <label style={{ display: 'flex', gap: 5, alignItems: 'center', cursor: 'pointer' }}>
            <input type="checkbox" checked={item.obrigatorio} onChange={(e) => gravar({ obrigatorio: e.target.checked })} />
            Obrigatória
          </label>
          <label style={{ display: 'flex', gap: 5, alignItems: 'center', cursor: 'pointer' }}>
            <input type="checkbox" checked={item.exige_foto} onChange={(e) => gravar({ exige_foto: e.target.checked })} />
            Pede foto
          </label>
        </div>
      </div>
      <IconeBotao
        rotulo={`Tirar a pergunta ${item.ordem}`}
        onClick={async () => {
          aoErro(null)
          try { await excluir.mutateAsync(item.item_modelo_id) } catch (e) { aoErro(primeiraFrase(e)) }
        }}
      >
        <Trash2 size={14} />
      </IconeBotao>
    </div>
  )
}

function IconeBotao({
  rotulo, disabled, onClick, children,
}: { rotulo: string; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button" aria-label={rotulo} title={rotulo} disabled={disabled} onClick={onClick}
      style={{
        display: 'grid', placeItems: 'center', width: 26, height: 26,
        background: 'none', border: '1px solid transparent', borderRadius: 6,
        cursor: disabled ? 'default' : 'pointer', color: 'var(--ink-3)',
        opacity: disabled ? 0.35 : 1,
      }}
    >
      {children}
    </button>
  )
}

/** Um campo de texto que grava **ao sair dele** e só se mudou — o `onBlur`
 *  sem essa conferência regravaria o texto a cada tab. */
function CampoQueGravaAoSair({
  rotulo, valor, aoGravar,
}: { rotulo: string; valor: string; aoGravar: (v: string) => void }) {
  const [texto, setTexto] = useState(valor)
  useEffect(() => { setTexto(valor) }, [valor])
  return (
    <Campo rotulo={rotulo}>
      <input
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onBlur={() => { if (texto.trim() !== valor.trim()) aoGravar(texto.trim()) }}
        style={entrada}
      />
    </Campo>
  )
}
