import type { ReactNode } from 'react'
import { Box, CheckCheck, Eye, FileWarning, Hammer, Image as ImageIcon, Layers, Lock, Star, Timer } from 'lucide-react'
import { Pill, Spinner } from '@/components/malha'
import { useArquivoBlob } from './hooks'
import { DisciplinasDaPrancha } from './pages/Disciplinas'
import { usePresenca } from './presenca'
import type { Conversao, Documento } from './types'

/**
 * O cartão da prancha — a única peça de navegação do módulo no celular.
 *
 * Tudo aqui é dimensionado para **mão suja e tela ao sol**: alvo de toque de 60
 * px na estrela (o mínimo confortável é 44, e quem usa luva erra os 44), título
 * em 15 px com duas linhas antes de cortar, e a miniatura ocupando metade do
 * cartão porque é por ela que se reconhece a prancha — ninguém lê "ARQ-PLB-001"
 * e enxerga a planta.
 */
export function CartaoPrancha({
  documento,
  favorito,
  onAbrir,
  onFavoritar,
  onPublicar,
  rodape,
}: {
  documento: Documento
  favorito: boolean
  onAbrir: (d: Documento) => void
  onFavoritar: (d: Documento) => void
  /**
   * Publica o rascunho pendente **deste** cartão. Só chega aqui quem tem
   * `prancheta.revisao.publicar`; sem ele a pílula continua explicando o estado,
   * porque o campo precisa saber por que a prancha não abre.
   */
  onPublicar?: (revisaoId: number) => void
  /** Linha extra de contexto (ex.: "há 2 h · 7 aberturas" nas mais vistas). */
  rodape?: ReactNode
}) {
  const vigente = documento.vigente
  const abrivel = !!vigente?.conversao.visualizador
  const presenca = usePresenca(vigente?.revisao_id ?? null)
  const pendente = documento.pendente

  return (
    <div
      style={{
        position: 'relative', background: 'var(--surface)', border: '2px solid var(--line)',
        borderRadius: 'var(--r-md)', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <button
        onClick={() => vigente && onAbrir(documento)}
        disabled={!vigente}
        style={{
          all: 'unset', cursor: vigente ? 'pointer' : 'default', display: 'flex',
          flexDirection: 'column', flex: 1, minHeight: 0,
        }}
      >
        <div style={{ height: 148, width: '100%', background: 'var(--inset)', borderBottom: '2px solid var(--line)', position: 'relative' }}>
          {/* A miniatura do rascunho pendente vale: o arquivo subiu e converteu
              — só não foi publicado. Mostrar o triângulo de defeito sobre uma
              prancha pronta é o mesmo erro do D81, dito com um ícone. */}
          {vigente ? <Previa conversao={vigente.conversao} />
            : pendente ? <Previa conversao={pendente.conversao} />
            : <Icone><FileWarning size={30} /></Icone>}
          {abrivel && (
            <span
              style={{
                position: 'absolute', right: 8, bottom: 8, display: 'inline-flex', alignItems: 'center',
                gap: 5, background: 'var(--glass)', border: '1px solid var(--line)', borderRadius: 999,
                padding: '4px 9px', fontSize: 11.5, fontWeight: 700, color: 'var(--ink-2)',
              }}
            >
              <Eye size={12} /> abrir
            </span>
          )}
        </div>

        <div style={{ padding: '12px 14px 14px', display: 'grid', gap: 8 }}>
          <span className="num" style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-3)' }}>
            {documento.codigo}
          </span>
          <strong style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.3 }}>
            {documento.titulo}
          </strong>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {vigente ? (
              <>
                <Pill kind={abrivel ? 'good' : 'slate'}>{vigente.revisao} vigente</Pill>
                <EstadoDaConversao conversao={vigente.conversao} />
              </>
            ) : pendente ? (
              // **Estado com saída, e não só rótulo.** O acervo em lote nasce
              // todo assim; dizer "sem revisão vigente" e parar aí deixava 141
              // pranchas prontas inacessíveis, com o remédio em outra aba.
              <Pill kind="accent">{pendente.revisao} em rascunho</Pill>
            ) : (
              <Pill kind="accent">sem revisão vigente</Pill>
            )}
            {/* Presença acende sozinha quando o backend do heartbeat existir
                (ver `presenca.ts`). Hoje não ocupa espaço no cartão: um selo
                "em breve" em cada prancha seria ruído, não informação. */}
            {presenca.suportado && presenca.pessoas.length > 0 && (
              <Pill kind="net" pulse>{presenca.pessoas.length} vendo agora</Pill>
            )}
          </div>

          {/* **As disciplinas, e não só uma.** Duas cabem na largura do cartão;
              o resto vira "+N" com os nomes no `title`. É a mesma gramática do
              seletor do envio e da fileira de filtro — bolinha da cor + nome —,
              para os três lugares parecerem o mesmo conceito. */}
          {!!documento.disciplinas?.length && (
            <DisciplinasDaPrancha itens={documento.disciplinas} limite={2} />
          )}

          {documento.etapa_nome && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)' }}>
              <Hammer size={13} /> {documento.etapa_nome}
            </span>
          )}

          {rodape}
        </div>
      </button>

      {/* Fora do botão de abrir, e não dentro: botão aninhado em botão é HTML
          inválido e o clique vira loteria de qual dos dois recebeu. */}
      {!vigente && pendente && onPublicar && (
        <button
          onClick={() => onPublicar(pendente.revisao_id)}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
            minHeight: 46, cursor: 'pointer',
            border: 'none', borderTop: '2px solid var(--line)',
            background: 'var(--accent-soft)', color: 'var(--accent-ink)',
            fontSize: 13, fontWeight: 700,
          }}
        >
          <CheckCheck size={15} /> Publicar {pendente.revisao}
        </button>
      )}

      <button
        onClick={() => onFavoritar(documento)}
        aria-label={favorito ? 'Remover dos favoritos' : 'Marcar como favorita'}
        title={favorito ? 'Remover dos favoritos' : 'Marcar como favorita'}
        style={{
          position: 'absolute', top: 6, right: 6, width: 60, height: 60, display: 'grid',
          placeItems: 'center', cursor: 'pointer', border: 'none', borderRadius: 999,
          background: 'var(--glass)', backdropFilter: 'blur(6px)',
          color: favorito ? 'var(--accent-strong)' : 'var(--ink-3)',
        }}
      >
        <Star size={24} fill={favorito ? 'currentColor' : 'none'} strokeWidth={favorito ? 2 : 1.8} />
      </button>
    </div>
  )
}

/** Miniatura real quando existe; ícone do estado quando não — nunca um vazio mudo. */
export function Previa({ conversao }: { conversao: Conversao }) {
  const { objeto, carregando } = useArquivoBlob(conversao.miniatura ?? null)

  if (conversao.miniatura && carregando) return <Icone><Spinner size={20} /></Icone>
  if (objeto) {
    return <img src={objeto} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
  }
  // O relógio serve aos dois: `convertendo` está na fila, `nao_agendada` devia
  // estar. Nenhum dos dois é o triângulo de defeito — não há nada errado com o
  // arquivo (D81).
  if (conversao.estado === 'convertendo' || conversao.estado === 'nao_agendada') {
    return <Icone><Timer size={30} /></Icone>
  }
  if (conversao.exige_upgrade) return <Icone><Lock size={30} /></Icone>
  if (conversao.tipo === 'modelo_3d') return <Icone><Box size={30} /></Icone>
  if (conversao.estado === 'erro' || conversao.estado === 'sem_motor') return <Icone><FileWarning size={30} /></Icone>
  return <Icone><ImageIcon size={30} /></Icone>
}

function Icone({ children }: { children: ReactNode }) {
  return <div style={{ height: '100%', display: 'grid', placeItems: 'center', color: 'var(--ink-3)' }}>{children}</div>
}

/**
 * O estado da conversão dito com a palavra certa. `exige_upgrade` vira "plano",
 * e não "erro": a saída de um é comprar, a do outro é chamado — e trocar as duas
 * é o defeito que a planta §9 nomeia.
 */
export function EstadoDaConversao({ conversao }: { conversao: Conversao }) {
  switch (conversao.estado) {
    case 'pronta':
      return conversao.tipo === 'modelo_3d'
        ? <Pill kind="net"><Box size={11} /> modelo 3D</Pill>
        : <Pill kind="info"><Layers size={11} /> abre aqui</Pill>
    case 'nativa':
      return <Pill kind="info">abre aqui</Pill>
    case 'convertendo':
      return <Pill kind="slate" pulse>convertendo</Pill>
    case 'erro':
      return conversao.exige_upgrade
        ? <Pill kind="accent"><Lock size={11} /> exige motor premium</Pill>
        : <Pill kind="danger">conversão falhou</Pill>
    case 'outro_modulo':
      return <Pill kind="slate">lido pelo {conversao.dono === 'modulomaps' ? 'Mapas' : 'módulo dono'}</Pill>
    // Fila, não lacuna: o cartão dá o mesmo recado que o visualizador (D81) — o
    // pendente é da plataforma, e some sozinho quando a conversão roda.
    case 'nao_agendada':
      return <Pill kind="slate">conversão não enfileirada</Pill>
    default:
      return <Pill kind="slate">sem visualizador</Pill>
  }
}

/**
 * Slot de presença do visualizador. Enquanto o heartbeat não existe, ele diz
 * "em breve" em vez de mostrar você mesmo como se fosse companhia — que é o que
 * qualquer simulação local produziria (`presenca.ts`).
 */
export function PresencaChip({ revisaoId }: { revisaoId: number | null }) {
  const presenca = usePresenca(revisaoId)

  if (!presenca.suportado) {
    return (
      <span
        title="Ver quem mais está com esta prancha aberta depende de um sinal do servidor, que ainda não existe."
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600,
          color: 'var(--ink-3)', background: 'var(--inset)', border: '1px dashed var(--line)',
          borderRadius: 999, padding: '4px 10px',
        }}
      >
        <Eye size={13} /> quem está vendo · em breve
      </span>
    )
  }

  if (!presenca.pessoas.length) {
    return <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>só você agora</span>
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ display: 'inline-flex' }}>
        {presenca.pessoas.slice(0, 4).map((p, i) => (
          <span
            key={p.nome}
            title={p.nome}
            style={{
              width: 30, height: 30, borderRadius: 999, display: 'grid', placeItems: 'center',
              background: 'var(--net-soft)', color: 'var(--net-ink)', fontSize: 11, fontWeight: 700,
              border: '2px solid var(--surface)', marginLeft: i ? -10 : 0,
            }}
          >
            {p.iniciais}
          </span>
        ))}
      </span>
      <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
        {presenca.pessoas.length} vendo agora
      </span>
    </span>
  )
}
