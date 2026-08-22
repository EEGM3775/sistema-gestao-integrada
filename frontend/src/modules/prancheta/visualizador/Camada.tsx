import type { Marcacao, Medicao, Ponto } from '../types'
import type { Enquadramento } from './Vista2D'
import { rotuloDaMedida, temAncora } from './marcar'
import type { Modo } from './marcar'
import {
  CENTRO, EXTREMIDADE, INTERSECAO, MEIO, NO, NOME_DO_TIPO, PROXIMO, QUADRANTE,
} from './snap'
import type { Achado } from './snap'

/**
 * O que se desenha **por cima** da prancha: pinos, o traço em curso e as medidas
 * já gravadas.
 *
 * É um `<svg>` absoluto sobre a imagem, e não elementos posicionados um a um,
 * porque metade do que se desenha aqui é linha e polígono. O SVG recebe
 * coordenadas de TELA já convertidas pelo enquadramento da `Vista2D` — a matriz
 * de pan/zoom vive num lugar só, e é isso que impede o pino de aparecer a dois
 * dedos de onde alguém o colocou.
 *
 * **Traço de espessura constante na tela**, não no desenho: a marcação é
 * anotação sobre a prancha, não parte dela. Se ela escalasse junto, aproximar
 * para conferir um detalhe faria a linha da medida cobrir o detalhe.
 */
export function Camada({
  enq,
  marcacoes,
  medicoes,
  emCurso,
  modo,
  escala,
  unidade,
  selecionada,
  aoSelecionar,
  mira,
}: {
  enq: Enquadramento
  marcacoes: Marcacao[]
  medicoes: Medicao[]
  /** Vértices do gesto em andamento (medir, calibrar ou posicionar o pino). */
  emCurso: Ponto[]
  modo: Modo
  escala: number | null
  unidade: string
  selecionada: number | null
  aoSelecionar: (id: number | null) => void
  /** O ponto notável onde o próximo clique vai cair (PRA.9). */
  mira?: Achado | null
}) {
  const tela = (p: Ponto) => enq.paraTela(p)

  return (
    <svg
      width="100%"
      height="100%"
      style={{ position: 'absolute', inset: 0, overflow: 'visible' }}
      aria-hidden={false}
      role="presentation"
    >
      {/* --- medidas já gravadas ------------------------------------------- */}
      {medicoes.map((medicao) => (
        <MedidaGravada key={medicao.medicao_id} medicao={medicao} tela={tela} />
      ))}

      {/* --- o gesto em andamento ------------------------------------------ */}
      {emCurso.length > 0 && (
        <EmCurso
          pontos={emCurso}
          modo={modo}
          escala={escala}
          unidade={unidade}
          tela={tela}
        />
      )}

      {/* --- pinos das marcações ------------------------------------------- */}
      {marcacoes.filter(temAncora).map((marcacao) => {
        const p = tela(marcacao.ancora)
        const ativa = selecionada === marcacao.marcacao_id
        return (
          <g
            key={marcacao.marcacao_id}
            transform={`translate(${p.x} ${p.y})`}
            style={{ pointerEvents: 'auto', cursor: 'pointer' }}
            onPointerDown={(e) => {
              // O pino consome o toque: sem isto, tocá-lo no modo de medição
              // plantaria um vértice em cima dele.
              e.stopPropagation()
              aoSelecionar(ativa ? null : marcacao.marcacao_id)
            }}
          >
            <title>{marcacao.titulo}</title>
            {/* Alvo invisível de 44 px — a régua de toque do canteiro (luva,
                andaime). O desenho visível é menor que a área que responde. */}
            <circle r={22} fill="transparent" />
            <circle
              r={ativa ? 13 : 10}
              fill={marcacao.aberta ? 'var(--accent)' : 'var(--good-soft)'}
              stroke={marcacao.aberta ? 'var(--accent-ink)' : 'var(--good-ink)'}
              strokeWidth={2}
            />
            {!marcacao.aberta && (
              <path
                d="M -4 0 L -1 3 L 4 -3"
                fill="none"
                stroke="var(--good-ink)"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}
          </g>
        )
      })}

      {/* --- a mira do snap, por último ------------------------------------
          Depois de tudo porque ela indica o **próximo** clique: coberta por um
          pino ou por uma medida já gravada, ela não cumpriria a única função
          que tem, que é dizer onde o dedo vai cair antes de ele cair. */}
      {mira && (() => {
        const p = tela(mira.ponto)
        return <MiraDeSnap x={p.x} y={p.y} tipo={mira.tipo} />
      })()}
    </svg>
  )
}

function MedidaGravada({
  medicao,
  tela,
}: {
  medicao: Medicao
  tela: (p: Ponto) => { x: number; y: number }
}) {
  const pontos = (medicao.pontos ?? []).map(tela)
  if (pontos.length < 2) return null
  const d = pontos.map((p) => `${p.x},${p.y}`).join(' ')
  const meio = pontos[Math.floor(pontos.length / 2)]

  // Medida tirada com outra régua aparece tracejada e apagada. Não é erro: é o
  // aviso de que ela não pode ser comparada com as de agora.
  const suspeita = medicao.desatualizada

  return (
    <g opacity={suspeita ? 0.55 : 1}>
      {medicao.tipo === 'area' ? (
        <polygon
          points={d}
          fill="var(--info-soft)"
          fillOpacity={0.35}
          stroke="var(--info-ink)"
          strokeWidth={2}
          strokeDasharray={suspeita ? '6 4' : undefined}
        />
      ) : (
        <polyline
          points={d}
          fill="none"
          stroke="var(--info-ink)"
          strokeWidth={2}
          strokeDasharray={suspeita ? '6 4' : undefined}
        />
      )}
      {pontos.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3.5} fill="var(--info-ink)" />
      ))}
      <Etiqueta
        x={meio.x}
        y={meio.y}
        texto={
          medicao.unidade
            ? `${medicao.valor.toFixed(2).replace('.', ',')} ${medicao.unidade}`
            : `${medicao.valor.toFixed(3)} da largura`
        }
        aviso={suspeita}
      />
    </g>
  )
}

function EmCurso({
  pontos,
  modo,
  escala,
  unidade,
  tela,
}: {
  pontos: Ponto[]
  modo: Modo
  escala: number | null
  unidade: string
  tela: (p: Ponto) => { x: number; y: number }
}) {
  const naTela = pontos.map(tela)
  const d = naTela.map((p) => `${p.x},${p.y}`).join(' ')
  const rotulo = rotuloDaMedida(pontos, modo, escala, unidade)
  const ultimo = naTela[naTela.length - 1]

  return (
    <g>
      {naTela.length > 1 &&
        (modo === 'area' ? (
          <polygon points={d} fill="var(--accent-soft)" fillOpacity={0.3}
                   stroke="var(--accent-ink)" strokeWidth={2} />
        ) : (
          <polyline points={d} fill="none" stroke="var(--accent-ink)" strokeWidth={2} />
        ))}
      {naTela.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={5} fill="var(--accent)"
                stroke="var(--accent-ink)" strokeWidth={1.5} />
      ))}
      {rotulo && <Etiqueta x={ultimo.x} y={ultimo.y - 14} texto={rotulo} destaque />}
    </g>
  )
}

/**
 * Rótulo legível sobre qualquer prancha.
 *
 * Retângulo sólido atrás do texto porque o fundo é o desenho do cliente — texto
 * solto sobre hachura de projeto estrutural é ilegível, e o número é o produto.
 */
function Etiqueta({
  x, y, texto, destaque, aviso,
}: {
  x: number
  y: number
  texto: string
  destaque?: boolean
  aviso?: boolean
}) {
  const largura = texto.length * 6.7 + 14
  const fundo = destaque ? 'var(--accent)' : 'var(--surface)'
  const tinta = destaque ? 'var(--accent-ink)' : aviso ? 'var(--ink-3)' : 'var(--ink)'
  return (
    <g transform={`translate(${x} ${y})`} style={{ pointerEvents: 'none' }}>
      <rect
        x={-largura / 2} y={-22} width={largura} height={20} rx={5}
        fill={fundo} stroke="var(--line)" strokeWidth={1}
      />
      <text
        x={0} y={-8} textAnchor="middle"
        style={{ font: '600 11.5px var(--mono, monospace)', fill: tinta }}
      >
        {texto}
      </text>
    </g>
  )
}

/**
 * A mira do snap — a forma diz QUAL ponto o clique vai pegar.
 *
 * **Forma e não cor**, seguindo a convenção do AutoCAD que todo projetista já
 * lê sem aprender: quadrado é extremidade, triângulo é meio, círculo é centro,
 * losango é quadrante, X é interseção. Distinguir por cor sozinha excluiria
 * quem tem daltonismo — e, no canteiro, a tela sob sol perde saturação muito
 * antes de perder forma.
 *
 * Desenhada em tamanho de TELA, como todo o resto desta camada: a mira é
 * instrumento, não parte do desenho. Se escalasse com o zoom, aproximar para
 * conferir um canto faria a mira cobrir exatamente o canto.
 */
function MiraDeSnap({ x, y, tipo }: { x: number; y: number; tipo: number }) {
  const r = 7
  const cor = 'var(--accent)'
  const traco = { fill: 'none', stroke: cor, strokeWidth: 2 } as const

  return (
    <g transform={`translate(${x} ${y})`} style={{ pointerEvents: 'none' }}>
      {/* Halo claro por baixo: a prancha é traço preto sobre branco, e uma mira
          fina sobre uma parede grossa desaparece sem isto. */}
      <circle r={r + 3} fill="var(--surface)" opacity={0.55} />
      {tipo === EXTREMIDADE && <rect x={-r} y={-r} width={r * 2} height={r * 2} {...traco} />}
      {tipo === MEIO && (
        <polygon points={`0,${-r} ${r},${r} ${-r},${r}`} {...traco} />
      )}
      {tipo === CENTRO && <circle r={r} {...traco} />}
      {tipo === QUADRANTE && (
        <polygon points={`0,${-r} ${r},0 0,${r} ${-r},0`} {...traco} />
      )}
      {tipo === INTERSECAO && (
        <path d={`M${-r},${-r} L${r},${r} M${r},${-r} L${-r},${r}`} {...traco} />
      )}
      {tipo === NO && (
        <>
          <circle r={r} {...traco} />
          <circle r={1.5} fill={cor} />
        </>
      )}
      {/* Ampulheta = "próximo", a mesma forma do AutoCAD. Tinha de ser diferente
          do triângulo do meio: os dois caem sobre a linha, e um glifo só para os
          dois faria a pessoa medir do meio achando que mediu do ponto onde
          apontou — erro que a mira não denuncia, porque ela acendeu. */}
      {tipo === PROXIMO && (
        <polygon points={`${-r},${-r} ${r},${-r} ${-r},${r} ${r},${r}`} {...traco} />
      )}
      <title>{NOME_DO_TIPO[tipo]}</title>
    </g>
  )
}
