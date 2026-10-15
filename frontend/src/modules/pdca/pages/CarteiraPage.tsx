import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, HardHat, Search } from 'lucide-react'
import { BotaoExportar, Btn, Card, Empty, Loading, Num, Pill, SectionHead } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { contemSemAcento } from '@/utils/texto'
import { dateToBR } from '@/utils/dates'
import { useCarteira } from '../hooks'
import { emDias, percentual } from '../formato'
import { DEGRAUS, POSTO_DA_ORIGEM, portaDoPapel } from '../postos'
import { SemPermissaoAviso } from '../components/SemPermissaoAviso'
import type { Consequencia, LinhaDaCarteira } from '../types'

type Ordem = 'pior' | 'nome' | 'prazo' | 'avanco'

const ORDENS: { codigo: Ordem; rotulo: string }[] = [
  { codigo: 'pior', rotulo: 'O que dói' },
  { codigo: 'prazo', rotulo: 'Atraso' },
  { codigo: 'avanco', rotulo: 'Avanço' },
  { codigo: 'nome', rotulo: 'Nome' },
]

const PESO_DA_CONSEQUENCIA = Object.fromEntries(
  DEGRAUS.map((d, i) => [d.codigo, i]),
) as Record<Consequencia, number>

/** **A porta de fora, e a casa da diretoria.**
 *
 *  As obras lado a lado com avanço contra o combinado, cumprimento da semana,
 *  conformidade e segurança. Daqui se **entra** numa obra — a carteira é
 *  leitura, não posto de trabalho: não se decide sobre várias de uma vez.
 *
 *  Não é painel de vaidade: a ordenação padrão é **pelo que dói**, e o que dói
 *  vem discriminado. Uma comunicação de acidente vencendo e um defeito de
 *  pintura nunca viram "2 pendências". */
export default function CarteiraPage() {
  const [busca, setBusca] = useState('')
  const [ordem, setOrdem] = useState<Ordem>('pior')
  const navigate = useNavigate()
  const carteira = useCarteira()
  const { roles, hasPermission } = useAuth()
  const portaDoCampo = portaDoPapel(roles, hasPermission) === 'campo'

  const linhas = useMemo(() => {
    const visiveis = (carteira.data?.obras ?? []).filter(
      (o) => !busca.trim() || contemSemAcento(o.nome, busca),
    )
    const copia = [...visiveis]
    copia.sort((a, b) => {
      if (ordem === 'nome') return a.nome.localeCompare(b.nome, 'pt-BR')
      if (ordem === 'prazo') return atraso(b) - atraso(a)
      if (ordem === 'avanco') return (a.avanco?.fisico ?? 101) - (b.avanco?.fisico ?? 101)
      return dorDe(a) - dorDe(b) || a.nome.localeCompare(b.nome, 'pt-BR')
    })
    return copia
  }, [carteira.data, busca, ordem])

  if (carteira.isLoading) return <Loading o="a carteira de obras" />

  /** **Falha não é vazio.** Sem esta separação a tela dizia "esta empresa ainda
   *  não tem obras cadastradas" quando o que houve foi a chamada não voltar — e
   *  mandar o usuário procurar um cadastro que existe é pior que não responder. */
  if (carteira.isError) {
    return (
      <div style={{ padding: '24px 26px', maxWidth: 620 }}>
        <SectionHead>Carteira de obras</SectionHead>
        <Card>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'flex-start' }}>
            <span style={{ fontSize: 13.5, color: 'var(--ink-2)', lineHeight: 1.6 }}>
              Não foi possível carregar as obras. Nada do que você fez se perdeu —
              é a consulta que não voltou.
            </span>
            <Btn variant="primary" onClick={() => carteira.refetch()}>
              Tentar de novo
            </Btn>
          </div>
        </Card>
      </div>
    )
  }

  const dados = carteira.data!

  return (
    <div style={{ padding: '24px 26px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionHead
        sub="Qual obra precisa de você esta semana. Clique para entrar — o trabalho acontece dentro de uma."
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BotaoExportar recurso="pdca.carteira" />
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                background: 'var(--surface)', border: '1px solid var(--line)',
                borderRadius: 'var(--r-sm)', padding: '6px 10px', minWidth: 210,
              }}
            >
              <Search size={14} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar obra"
                style={{
                  border: 'none', outline: 'none', background: 'transparent',
                  color: 'var(--ink)', fontSize: 13, width: '100%',
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: 2 }}>
              {ORDENS.map((o) => (
                <button
                  key={o.codigo}
                  type="button"
                  onClick={() => setOrdem(o.codigo)}
                  style={{
                    fontSize: 11.5, fontWeight: 650, padding: '5px 9px',
                    borderRadius: 'var(--r-sm)', cursor: 'pointer',
                    border: '1px solid',
                    borderColor: ordem === o.codigo ? 'var(--accent)' : 'var(--line)',
                    background: ordem === o.codigo ? 'var(--accent-soft)' : 'var(--surface)',
                    color: ordem === o.codigo ? 'var(--accent-ink)' : 'var(--ink-3)',
                  }}
                >
                  {o.rotulo}
                </button>
              ))}
            </div>
          </div>
        }
      >
        Carteira de obras
      </SectionHead>

      {portaDoCampo && <PassagemParaOCampo />}

      {dados.sem_permissao.length > 0 && <SemPermissaoAviso itens={dados.sem_permissao} />}

      {dados.truncada && (
        <div
          style={{
            fontSize: 12.5, color: 'var(--ink-2)', padding: '9px 13px',
            background: 'var(--inset)', border: '1px dashed var(--line)',
            borderRadius: 'var(--r-sm)', lineHeight: 1.5,
          }}
        >
          Esta empresa tem <strong>{dados.total} obras</strong> e a carteira
          desenha {dados.teto} por vez. Use a busca para chegar às demais.
        </div>
      )}

      {linhas.length === 0 ? (
        <Empty>
          {busca.trim()
            ? 'Nenhuma obra com esse nome.'
            : 'Esta empresa ainda não tem obras cadastradas.'}
        </Empty>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {linhas.map((linha) => (
            <LinhaDaObra
              key={linha.obra}
              linha={linha}
              aoEntrar={(posto) => navigate(
                posto ? `/app/pdca/o/${linha.obra}/${posto}` : `/app/pdca/o/${linha.obra}`,
              )}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** **A porta do encarregado é o campo** (§3.3 da planta) — *a minha frente
 *  de hoje*, que não é de obra nenhuma em particular. Ela não substitui a
 *  carteira (o papel escolhe a porta, nunca esconde o resto): fica à vista
 *  aqui, que é onde se chega antes de escolher obra, e sem ela a superfície de
 *  campo só era alcançável digitando o endereço. */
function PassagemParaOCampo() {
  return (
    <Link
      to="/campo"
      style={{
        display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none',
        padding: '12px 16px', borderRadius: 'var(--r-md)',
        background: 'var(--accent-soft)', border: '1px solid var(--accent)',
      }}
    >
      <HardHat size={20} style={{ color: 'var(--accent-ink)', flexShrink: 0 }} />
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 14, fontWeight: 680, color: 'var(--ink)' }}>
          A sua frente de hoje
        </span>
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          Apontar o que andou, dizer que a trava saiu, responder a ficha — a versão de canteiro.
        </span>
      </span>
      <ArrowRight size={16} style={{ color: 'var(--accent-ink)', flexShrink: 0 }} />
    </Link>
  )
}

function dorDe(linha: LinhaDaCarteira): number {
  if (!linha.pior_pendencia) return 99
  return PESO_DA_CONSEQUENCIA[linha.pior_pendencia.consequencia] ?? 98
}

function atraso(linha: LinhaDaCarteira): number {
  return linha.prazo?.desvio_dias ?? -9999
}

function LinhaDaObra({
  linha, aoEntrar,
}: { linha: LinhaDaCarteira; aoEntrar: (posto?: string) => void }) {
  const desvio = linha.prazo?.desvio_dias

  return (
    <Card pad={false}>
      <div
        style={{
          display: 'flex', alignItems: 'stretch', gap: 0,
          borderLeft: `3px solid ${corDaDor(linha)}`,
          borderTopLeftRadius: 'var(--r-md)', borderBottomLeftRadius: 'var(--r-md)',
        }}
      >
        <button
          type="button"
          onClick={() => aoEntrar()}
          style={{
            flex: '1 1 280px', minWidth: 0, textAlign: 'left', cursor: 'pointer',
            background: 'none', border: 'none', padding: '13px 16px',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}
        >
          <span
            style={{
              fontSize: 14.5, fontWeight: 680, color: 'var(--ink)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {linha.nome}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <Pill kind="slate">{linha.status_rotulo}</Pill>
            {linha.prazo?.termino && (
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                Termina em {dateToBR(linha.prazo.termino)}
              </span>
            )}
            {!linha.prazo?.tem_plano && (
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                Sem cronograma publicado
              </span>
            )}
          </span>
        </button>

        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 22, flexShrink: 0,
            padding: '13px 16px', flexWrap: 'wrap',
          }}
        >
          <Medida
            rotulo="Avanço"
            valor={percentual(linha.avanco?.fisico)}
          />
          <Medida
            rotulo="Prazo"
            valor={
              desvio == null
                ? null
                : desvio === 0
                  ? 'no prazo'
                  : `${desvio > 0 ? '+' : '−'}${emDias(desvio)}`
            }
            tom={desvio == null ? undefined : desvio > 0 ? 'var(--danger-ink)' : 'var(--good-ink)'}
          />
          <Medida rotulo="PPC" valor={percentual(linha.ppc?.ppc)} />
          <Medida
            rotulo="Conformidade"
            valor={percentual(linha.conformidade?.conformidade, 2)}
          />
          <Medida
            rotulo="Sem afastamento"
            valor={
              linha.seguranca?.dias_sem_afastamento != null
                ? emDias(linha.seguranca.dias_sem_afastamento, 'hoje')
                : null
            }
          />
        </div>
      </div>

      {linha.pendencias.length > 0 && (
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap',
            padding: '9px 16px', borderTop: '1px solid var(--line-2)',
            background: 'var(--inset)',
          }}
        >
          {linha.pendencias.map((p) => (
            <button
              key={p.codigo}
              type="button"
              onClick={() => aoEntrar(POSTO_DA_ORIGEM[postoDe(p.codigo)])}
              title={`Abrir o posto que trata: ${p.rotulo.toLowerCase()}`}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
            >
              <Pill kind={pillDe(p.consequencia)}>
                {p.rotulo} · {p.quantas}
              </Pill>
            </button>
          ))}
          <span style={{ marginLeft: 'auto', display: 'inline-flex' }}>
            <button
              type="button"
              onClick={() => aoEntrar('controle')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 12, fontWeight: 650, color: 'var(--brand)',
              }}
            >
              Abrir a fila desta obra
              <ArrowRight size={13} />
            </button>
          </span>
        </div>
      )}
    </Card>
  )
}

function Medida({ rotulo, valor, tom }: { rotulo: string; valor: string | null; tom?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 66 }}>
      <span
        style={{
          fontSize: 9.5, letterSpacing: '0.07em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700,
        }}
      >
        {rotulo}
      </span>
      {valor == null ? (
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontStyle: 'italic' }}>
          sem apuração
        </span>
      ) : (
        <Num size={15} tone={tom ?? 'var(--ink)'} align="left">
          {valor}
        </Num>
      )}
    </div>
  )
}

function corDaDor(linha: LinhaDaCarteira): string {
  const c = linha.pior_pendencia?.consequencia
  if (c === 'prazo_legal' || c === 'seguranca') return 'var(--danger-ink)'
  if (c === 'dinheiro') return 'var(--accent)'
  if (c === 'compromisso') return 'var(--info-ink)'
  if (c === 'retrabalho') return 'var(--line)'
  return 'transparent'
}

function pillDe(c: Consequencia): 'danger' | 'accent' | 'info' | 'slate' {
  return DEGRAUS.find((d) => d.codigo === c)?.pill ?? 'slate'
}

/** De que contagem da carteira para que assunto — o mesmo mapa da fila. */
function postoDe(codigo: string): keyof typeof POSTO_DA_ORIGEM {
  if (codigo.startsWith('cat') || codigo.startsWith('ocorrencias')) return 'seguranca'
  if (codigo.startsWith('medicoes')) return 'medicao'
  if (codigo.startsWith('semanas')) return 'programacao'
  if (codigo.startsWith('restricoes')) return 'restricao'
  return 'qualidade'
}
