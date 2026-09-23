import { Map, X } from 'lucide-react'
import type { Desenho } from '../types'

/**
 * **O localizador da prancha difícil** (D97) — onde estão os desenhos deste
 * arquivo, e como chegar a cada um sem arrastar.
 *
 * **O problema, nas palavras do dono:** *"quando abro o desenho eu vejo tudo que
 * está nos desenhos, mas em desenhos separados; eu quero ver o desenho
 * completo"* — e, sobre o zoom, *"não tem como eu achar nada porque levaria
 * muito tempo arrastando"*.
 *
 * A separação por folha (PRA.1c) foi certa e continua: um arquivo com duas
 * poligonais a 8,5 milhões de unidades uma da outra numa folha só produz uma
 * página de 469 m × 8,5 km, que nenhum navegador rasteriza e onde cada desenho
 * ocupa 0,2% da largura. O que faltava não era desfazê-la — era **a vista de
 * cima**: a planta inteira em miniatura, com cada desenho no lugar em que ele
 * está *no terreno*, para a pessoa ver o conjunto e escolher para onde ir.
 *
 * **O dado já existia e não foi inventado.** `DesenhoProjeto.caixa` guarda a
 * envolvente de cada aglomerado em **unidades de desenho** — a mesma que o
 * agrupador usa para cortar as folhas e que a herança de nome usa para
 * reconhecer o mesmo desenho na revisão seguinte. É por isso que o minimapa
 * mostra a disposição real e não um enfileiramento decorativo: duas plantas lado
 * a lado no CAD aparecem lado a lado aqui.
 *
 * **Desligável, como o snap.** Ele cobre um pedaço da prancha, e quem já sabe
 * onde está não quer isso — a mesma régua do D46: a ajuda que não se desliga
 * vira estorvo no dia seguinte.
 */
export function Minimapa({
  folhas, ordemAberta, aoAbrir, aoFechar,
}: {
  folhas: Desenho[]
  ordemAberta: number
  aoAbrir: (ordem: number) => void
  aoFechar: () => void
}) {
  const manchas = folhas
    .map((f) => ({ folha: f, caixa: normalizar(f.caixa) }))
    .filter((m) => m.caixa !== null) as { folha: Desenho; caixa: Caixa }[]

  // Sem envolvente não há mapa. Acontece em folha convertida antes da PRA.1c e
  // em motor que não rende geometria — e a resposta honesta é não abrir o painel,
  // em vez de desenhar retângulos inventados sobre coordenada que ninguém mediu.
  if (manchas.length < 2) return null

  const mundo = envolvente(manchas.map((m) => m.caixa))
  const largura = mundo.xmax - mundo.xmin || 1
  const altura = mundo.ymax - mundo.ymin || 1

  return (
    <div
      style={{
        // **Canto, e não meio** (pedido do dono, 15/09/2026: *"ele tem que ser
        // melhor alocado, fica no meio da tela"*). Centralizado no topo, o
        // localizador cobria exatamente a faixa onde mora o carimbo da prancha e
        // o começo do desenho — a ajuda tapava o que ela ajudava a achar. No
        // canto superior esquerdo ele sai da frente e continua à mão; a barra de
        // modos e os botões de zoom vivem embaixo e à direita, então não há
        // disputa por esse canto.
        position: 'absolute', top: 12, left: 12,
        zIndex: 3, width: 'min(300px, calc(100% - 24px))',
        background: 'var(--glass)', backdropFilter: 'blur(14px)',
        border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
        padding: '9px 11px 11px', display: 'grid', gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <Map size={13} style={{ color: 'var(--ink-3)', flex: 'none' }} />
        <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--ink-2)' }}>
          Onde estão os {manchas.length} desenhos
        </span>
        <button
          onClick={aoFechar}
          aria-label="Fechar o localizador"
          style={{
            marginLeft: 'auto', width: 26, height: 26, display: 'grid',
            placeItems: 'center', cursor: 'pointer', background: 'transparent',
            border: 0, color: 'var(--ink-3)',
          }}
        >
          <X size={13} />
        </button>
      </div>

      {/* `preserveAspectRatio` mantém a proporção do terreno: esticar o mapa para
          preencher a caixa poria dois desenhos alinhados no CAD em diagonal
          aqui — e a pessoa concluiria que o arquivo está torto. */}
      {/**
        * **A região clicável** (pedido do dono, 15/09/2026: *"esse minimapa
        * deveria ter uma região clicável, que mostra onde os desenhos que seriam
        * separados estão"*).
        *
        * Antes só o retângulo pintado respondia ao clique, e essa era a metade
        * que não funcionava: uma poligonal de 40 m ao lado de um loteamento de 8
        * km ocupa **menos de um pixel** no mapa, e um alvo de menos de um pixel
        * não é alvo. Agora o mapa inteiro é a região clicável — clicar em
        * qualquer lugar abre o desenho **mais próximo** dali. Não há ponto morto:
        * mirar "perto" passa a bastar, que é o gesto que a mão faz num mapa.
        */}
      <svg
        viewBox={`0 0 ${largura} ${altura}`}
        preserveAspectRatio="xMidYMid meet"
        onClick={(e) => {
          const alvo = e.currentTarget.getBoundingClientRect()
          // O `preserveAspectRatio` centraliza o conteúdo e sobra faixa vazia num
          // dos eixos; sem descontá-la, o clique se desloca proporcionalmente à
          // sobra e o "mais próximo" sai errado justamente nas bordas.
          const escala = Math.min(alvo.width / largura, alvo.height / altura)
          const sobraX = (alvo.width - largura * escala) / 2
          const sobraY = (alvo.height - altura * escala) / 2
          const x = mundo.xmin + (e.clientX - alvo.left - sobraX) / escala
          const y = mundo.ymax - (e.clientY - alvo.top - sobraY) / escala
          const perto = maisProximo(manchas, x, y)
          if (perto) aoAbrir(perto.folha.ordem)
        }}
        style={{
          width: '100%', height: 132, display: 'block', cursor: 'pointer',
          background: 'var(--inset)', borderRadius: 'var(--r-sm)',
        }}
      >
        {manchas.map(({ folha, caixa }, i) => {
          const aberta = folha.ordem === ordemAberta
          // O desenho minúsculo ganha um piso de tamanho para **existir na
          // tela**. É o mesmo motivo do botão de 46 px do resto do módulo: o
          // mapa mostra onde as coisas estão, e o que não se enxerga não está.
          const l = Math.max(caixa.xmax - caixa.xmin, largura * 0.02)
          const a = Math.max(caixa.ymax - caixa.ymin, altura * 0.02)
          const x = caixa.xmin - mundo.xmin
          // O eixo Y do desenho cresce para CIMA e o do SVG para baixo: sem a
          // inversão, o mapa sai espelhado e mandaria a pessoa para o canto
          // oposto ao que ela clicou.
          const y = mundo.ymax - caixa.ymax
          return (
            <g key={folha.desenho_id} style={{ pointerEvents: 'none' }}>
              <rect
                x={x} y={y} width={l} height={a}
                fill={aberta ? 'var(--accent)' : 'var(--ink-3)'}
                fillOpacity={aberta ? 0.85 : 0.35}
                stroke={aberta ? 'var(--accent-strong)' : 'transparent'}
                strokeWidth={largura * 0.004}
              >
                <title>
                  {`${folha.rotulo} — ${folha.tracos.toLocaleString('pt-BR')} traços`}
                </title>
              </rect>
              {/* O número amarra a mancha à pílula de baixo: sem ele, "o de
                  cima à direita" é a única forma de falar de um desenho. */}
              <text
                x={x + l / 2} y={y + a / 2}
                textAnchor="middle" dominantBaseline="central"
                fontSize={Math.min(largura, altura) * 0.055}
                fill={aberta ? 'var(--accent-ink)' : 'var(--ink-2)'}
                style={{ fontWeight: 700 }}
              >
                {i + 1}
              </text>
            </g>
          )
        })}
      </svg>

      {/* A lista existe para o desenho minúsculo continuar alcançável. Uma
          poligonal de 40 m ao lado de um loteamento de 8 km vira um pixel no
          mapa, e um alvo de um pixel não é alvo — é a mesma razão do botão de
          46 px do resto do módulo. */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {manchas.map(({ folha }, i) => (
          <button
            key={folha.desenho_id}
            onClick={() => aoAbrir(folha.ordem)}
            title={`Enquadrar ${folha.rotulo}`}
            style={{
              cursor: 'pointer', border: '1px solid var(--line)',
              borderRadius: 999, padding: '4px 10px', fontSize: 11,
              fontWeight: folha.ordem === ordemAberta ? 700 : 500,
              background: folha.ordem === ordemAberta ? 'var(--accent-soft)' : 'var(--surface)',
              color: folha.ordem === ordemAberta ? 'var(--accent-ink)' : 'var(--ink-2)',
            }}
          >
            <span style={{ opacity: 0.65, marginRight: 5 }}>{i + 1}</span>
            {folha.rotulo}
          </button>
        ))}
      </div>
    </div>
  )
}

interface Caixa { xmin: number; ymin: number; xmax: number; ymax: number }

/** A envolvente só serve se as quatro pontas existem e têm área. */
function normalizar(caixa: Record<string, number> | undefined): Caixa | null {
  if (!caixa) return null
  const { xmin, ymin, xmax, ymax } = caixa
  const numeros = [xmin, ymin, xmax, ymax]
  if (numeros.some((n) => typeof n !== 'number' || !Number.isFinite(n))) return null
  if (xmax <= xmin || ymax <= ymin) return null
  return { xmin, ymin, xmax, ymax }
}

/**
 * O desenho mais perto de um ponto — o que faz o mapa inteiro ser clicável.
 *
 * Distância **à caixa**, não ao centro dela: com um loteamento de 8 km ao lado
 * de uma poligonal de 40 m, o centro do grande fica longe de quase toda a área
 * que ele mesmo ocupa, e clicar em cima dele abriria o pequeno. Dentro da caixa
 * a distância é zero, que é a resposta certa.
 */
function maisProximo<T extends { caixa: Caixa }>(manchas: T[], x: number, y: number): T | null {
  let melhor: T | null = null
  let menor = Infinity
  for (const mancha of manchas) {
    const { xmin, ymin, xmax, ymax } = mancha.caixa
    const dx = Math.max(xmin - x, 0, x - xmax)
    const dy = Math.max(ymin - y, 0, y - ymax)
    const d = dx * dx + dy * dy
    if (d < menor) { menor = d; melhor = mancha }
  }
  return melhor
}

function envolvente(caixas: Caixa[]): Caixa {
  return {
    xmin: Math.min(...caixas.map((c) => c.xmin)),
    ymin: Math.min(...caixas.map((c) => c.ymin)),
    xmax: Math.max(...caixas.map((c) => c.xmax)),
    ymax: Math.max(...caixas.map((c) => c.ymax)),
  }
}
