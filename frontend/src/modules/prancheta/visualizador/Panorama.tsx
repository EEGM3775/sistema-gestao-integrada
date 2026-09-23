import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as EventoPonteiro, WheelEvent as EventoRoda } from 'react'
import { Maximize2, Minus, Plus } from 'lucide-react'
import { baixarArquivo } from '@/lib/arquivo'
import type { Desenho } from '../types'

/**
 * **A prancha inteira, com a separação desfeita** (pedido do dono, 15/09/2026).
 *
 * *"O 21 fala sobre arquivos com distâncias muito grandes entre desenhos, onde o
 * desenho é separado. Quero desfazer essa separação."*
 *
 * A separação por folha (PRA.1c) continua existindo e continua certa — é ela que
 * impede a página de 469 m × 8,5 km que nenhum navegador rasteriza, e é dela que
 * dependem a marcação (âncora normalizada pela largura DAQUELA folha), a medição
 * e o snap. O que faltava não era apagá-la do backend: era **a vista em que ela
 * não aparece**. Aqui as folhas voltam a ficar lado a lado, cada uma no lugar em
 * que está no terreno, e o arquivo volta a parecer o que é — um desenho só.
 *
 * **Nada é reconvertido e nada é inventado.** Cada folha já sabe onde está: o
 * `mundo` medido na emissão (`dxf.py::_mundo_da_folha`) diz o canto superior-
 * esquerdo da folha em unidades de desenho e quantas unidades cabem na largura
 * dela. Com esses dois números e o aspecto real da imagem, a posição de cada
 * folha no conjunto é **aritmética sobre dado publicado**, não um enfileiramento
 * decorativo: duas plantas lado a lado no CAD aparecem lado a lado aqui, e as
 * duas poligonais a 8,5 milhões de unidades aparecem a 8,5 milhões de unidades.
 *
 * **É vista de navegação, não de trabalho.** Marcar, medir e o leitor de
 * coordenadas continuam na `Vista2D`, por folha — clicar num desenho aqui abre
 * ele lá. Trazer a marcação para cá exigiria uma segunda régua de normalização
 * convivendo com a primeira, e duas réguas divergem no primeiro ajuste: o
 * sintoma seria o pino a dois dedos de onde alguém o pôs, que é o pior defeito
 * possível numa ferramenta cujo produto é apontar *onde* (a família do D54).
 */

interface Caixa { xmin: number; ymin: number; xmax: number; ymax: number }

/** Onde a FOLHA inteira cai no mundo — margem incluída, que é como ela é pintada. */
interface Posta {
  folha: Desenho
  x: number
  y: number
  largura: number
  altura: number
}

const ZOOM_MIN_REL = 0.2
const ZOOM_MAX_REL = 50_000
/** Os mesmos dois passos da `Vista2D`: roda solta atravessa, `Ctrl` procura. */
const PASSO_RODA = 1.12
const PASSO_FINO = 1.03

/**
 * Quantas folhas se baixam ao mesmo tempo.
 *
 * Não é teto de uso (§5.6 do `payment/planos.py`): é largura de banda do próprio
 * navegador, e o teto de quantas folhas existem já mora lá
 * (`PRANCHETA_TETO_FOLHAS_POR_ARQUIVO`). Quatro de cada vez mantém a fila
 * andando sem abrir 64 requisições de uma vez — e, como o conjunto já aparece
 * desenhado pelas envolventes antes da primeira imagem chegar, a espera não é
 * uma tela vazia.
 */
const BAIXAS_SIMULTANEAS = 4

/**
 * As folhas como object URL — o `<img src>` cru levaria 401.
 *
 * O access token vive em memória e só é anexado pelo interceptor do `apiClient`
 * (D70/F1), então cada folha é buscada por XHR e vira blob local. Elas chegam em
 * ordem e **a vista não espera por todas**: quem chegou já é pintado por cima da
 * envolvente correspondente.
 */
function useFolhasEmBlob(folhas: Desenho[]) {
  const [blobs, setBlobs] = useState<Record<number, string>>({})
  // **A dependência é o conteúdo, não o array.** Quem chama monta
  // `revisao.desenhos ?? []` a cada renderização, e um efeito preso à
  // identidade do array baixaria as 64 folhas de novo a cada render — um laço
  // infinito de rede que só apareceria em arquivo grande.
  const chave = folhas.map((f) => `${f.desenho_id}:${f.visualizador ?? ''}`).join('|')

  useEffect(() => {
    let vivo = true
    const criados: string[] = []
    const fila = folhas.filter((f) => f.visualizador)
    let proxima = 0

    const puxar = async (): Promise<void> => {
      while (vivo && proxima < fila.length) {
        const folha = fila[proxima++]
        try {
          const blob = await baixarArquivo(folha.visualizador as string)
          if (!vivo) return
          const url = URL.createObjectURL(blob)
          criados.push(url)
          setBlobs((a) => ({ ...a, [folha.desenho_id]: url }))
        } catch {
          // Folha que não baixa continua no conjunto como envolvente — some do
          // desenho, não do mapa. Sumir por inteiro faria a pessoa procurar num
          // lugar onde nada mais indica que havia algo.
        }
      }
    }

    void Promise.all(
      Array.from({ length: Math.min(BAIXAS_SIMULTANEAS, fila.length) }, puxar),
    )

    return () => {
      vivo = false
      criados.forEach((url) => URL.revokeObjectURL(url))
      setBlobs({})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave])

  return blobs
}

export function Panorama({
  folhas, ordemAberta, aoAbrir,
}: {
  folhas: Desenho[]
  ordemAberta: number
  aoAbrir: (ordem: number) => void
}) {
  const caixaRef = useRef<HTMLDivElement>(null)
  const [t, setT] = useState({ x: 0, y: 0, z: 1 })
  const [zAjuste, setZAjuste] = useState(1)
  const [aspectos, setAspectos] = useState<Record<number, number>>({})
  const [sobre, setSobre] = useState<number | null>(null)
  const blobs = useFolhasEmBlob(folhas)
  const arrasto = useRef<{ x: number; y: number } | null>(null)
  const percorrido = useRef(0)

  // ── onde cada folha cai, em unidade de desenho ───────────────────────────
  const { postas, mundo } = useMemo(() => {
    const postas: Posta[] = []
    const conteudo: Caixa[] = []

    for (const folha of folhas) {
      const caixa = normalizar(folha.caixa)
      if (caixa) conteudo.push(caixa)

      const m = folha.mundo as { origem_x?: number; origem_y?: number; por_folha?: number }
      const aspecto = aspectos[folha.desenho_id]
      if (
        typeof m?.origem_x === 'number' && typeof m?.origem_y === 'number' &&
        typeof m?.por_folha === 'number' && m.por_folha > 0 && aspecto
      ) {
        postas.push({
          folha,
          x: m.origem_x,
          // `origem_y` é o topo, e o eixo do desenho cresce para cima: a folha
          // ocupa daqui para BAIXO.
          y: m.origem_y - m.por_folha * aspecto,
          largura: m.por_folha,
          altura: m.por_folha * aspecto,
        })
      } else if (caixa) {
        // **Plano B declarado**: folha convertida antes de o `mundo` existir, ou
        // motor que não rende coordenada. Aí ela é posta sobre a própria
        // envolvente — a margem da folha fica de fora e o desenho pode encostar
        // na borda. É posição aproximada, e é melhor que sumir do conjunto.
        postas.push({
          folha, x: caixa.xmin, y: caixa.ymin,
          largura: caixa.xmax - caixa.xmin, altura: caixa.ymax - caixa.ymin,
        })
      }
    }

    // O enquadramento segue o CONTEÚDO (as envolventes), não as folhas: a folha
    // inclui margem, e enquadrar por ela deixaria o desenho menor do que cabe.
    const base = conteudo.length ? conteudo : postas.map((p) => ({
      xmin: p.x, ymin: p.y, xmax: p.x + p.largura, ymax: p.y + p.altura,
    }))
    return { postas, mundo: base.length ? envolvente(base) : null }
  }, [folhas, aspectos])

  const largura = mundo ? mundo.xmax - mundo.xmin || 1 : 1
  const altura = mundo ? mundo.ymax - mundo.ymin || 1 : 1

  /** Encaixa o conjunto inteiro na caixa — o estado inicial e o botão "ajustar". */
  const ajustar = useCallback(() => {
    const caixa = caixaRef.current
    if (!caixa || !mundo) return
    const r = caixa.getBoundingClientRect()
    if (!r.width || !r.height) return
    const escala = Math.min(r.width / largura, r.height / altura) * 0.92
    setZAjuste(escala)
    setT({
      z: escala,
      x: (r.width - largura * escala) / 2,
      y: (r.height - altura * escala) / 2,
    })
  }, [largura, altura, mundo])

  // Reenquadra quando a caixa muda de tamanho e quando a última folha mediu o
  // aspecto (até lá o conjunto ainda estava crescendo).
  useEffect(() => {
    const caixa = caixaRef.current
    if (!caixa) return
    const observador = new ResizeObserver(() => ajustar())
    observador.observe(caixa)
    return () => observador.disconnect()
  }, [ajustar])

  const ampliar = useCallback((fator: number, ancora: { x: number; y: number }) => {
    setT((atual) => {
      const z = Math.min(
        zAjuste * ZOOM_MAX_REL,
        Math.max(zAjuste * ZOOM_MIN_REL, atual.z * fator),
      )
      const real = z / atual.z
      return { z, x: ancora.x - (ancora.x - atual.x) * real, y: ancora.y - (ancora.y - atual.y) * real }
    })
  }, [zAjuste])

  const naRoda = (e: EventoRoda<HTMLDivElement>) => {
    const caixa = caixaRef.current
    if (!caixa) return
    const r = caixa.getBoundingClientRect()
    const passo = e.ctrlKey || e.metaKey ? PASSO_FINO : PASSO_RODA
    ampliar(
      e.deltaY < 0 ? passo : 1 / passo,
      { x: e.clientX - r.left, y: e.clientY - r.top },
    )
  }

  const aoDescer = (e: EventoPonteiro<HTMLDivElement>) => {
    arrasto.current = { x: e.clientX, y: e.clientY }
    percorrido.current = 0
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const aoMover = (e: EventoPonteiro<HTMLDivElement>) => {
    const de = arrasto.current
    if (!de) return
    const dx = e.clientX - de.x
    const dy = e.clientY - de.y
    percorrido.current += Math.abs(dx) + Math.abs(dy)
    arrasto.current = { x: e.clientX, y: e.clientY }
    setT((a) => ({ ...a, x: a.x + dx, y: a.y + dy }))
  }
  const aoSubir = (e: EventoPonteiro<HTMLDivElement>) => {
    arrasto.current = null
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* já solto */ }
  }

  const paraTela = (x: number, y: number) => ({
    x: t.x + (x - (mundo?.xmin ?? 0)) * t.z,
    // O SVG cresce para baixo e o desenho para cima: a inversão é o que impede o
    // conjunto de sair espelhado, mandando a pessoa para o canto oposto.
    y: t.y + ((mundo?.ymax ?? 0) - y) * t.z,
  })

  if (!folhas.length) return null

  return (
    <div
      ref={caixaRef}
      onWheel={naRoda}
      onPointerDown={aoDescer}
      onPointerMove={aoMover}
      onPointerUp={aoSubir}
      onPointerCancel={aoSubir}
      style={{
        position: 'relative', width: '100%', height: '100%', overflow: 'hidden',
        background: 'var(--inset)', touchAction: 'none', cursor: arrasto.current ? 'grabbing' : 'grab',
      }}
    >
      {postas.map((p) => {
        const canto = paraTela(p.x, p.y + p.altura)
        const aberta = p.folha.ordem === ordemAberta
        const realcada = sobre === p.folha.desenho_id
        return (
          <div
            key={p.folha.desenho_id}
            onPointerEnter={() => setSobre(p.folha.desenho_id)}
            onPointerLeave={() => setSobre((s) => (s === p.folha.desenho_id ? null : s))}
            // Um arrasto que termina sobre a folha não é um clique nela: sem o
            // limiar, atravessar o conjunto abriria o desenho onde o dedo parou.
            onClick={() => { if (percorrido.current < 6) aoAbrir(p.folha.ordem) }}
            title={`Abrir ${p.folha.rotulo} — ${p.folha.tracos.toLocaleString('pt-BR')} traços`}
            style={{
              position: 'absolute',
              left: canto.x, top: canto.y,
              width: p.largura * t.z, height: p.altura * t.z,
              outline: realcada || aberta
                ? `${Math.max(1, 2 / (t.z / zAjuste))}px solid var(--accent)` : 'none',
              outlineOffset: 2,
              cursor: 'pointer',
            }}
          >
            {/* **A envolvente aparece antes da folha, de propósito.** As 64
                folhas podem pesar dezenas de MB somadas, e esperar por todas
                daria uma tela vazia justamente para o arquivo em que a pessoa
                mais precisa se orientar. O retângulo tracejado é dado real — é a
                mesma `caixa` que o agrupador usou para cortar —, e a folha o
                cobre quando chega. */}
            {blobs[p.folha.desenho_id] ? (
              <img
                src={blobs[p.folha.desenho_id]}
                alt={p.folha.rotulo}
                draggable={false}
                onLoad={(e) => {
                  const img = e.currentTarget
                  if (!img.naturalWidth) return
                  const aspecto = img.naturalHeight / img.naturalWidth
                  setAspectos((a) => (a[p.folha.desenho_id] === aspecto
                    ? a : { ...a, [p.folha.desenho_id]: aspecto }))
                }}
                style={{
                  width: '100%', height: '100%', display: 'block',
                  // Realce por opacidade e não por filtro de cor: a prancha tem
                  // de continuar legível enquanto se escolhe para onde ir.
                  opacity: sobre != null && !realcada ? 0.55 : 1,
                  pointerEvents: 'none',
                }}
              />
            ) : (
              <div style={{
                width: '100%', height: '100%',
                border: '1px dashed var(--line)', borderRadius: 2,
                background: 'color-mix(in srgb, var(--ink-3) 8%, transparent)',
              }} />
            )}
          </div>
        )
      })}

      {/* Quem está aberto, e o quanto se está enxergando. */}
      <div style={{
        position: 'absolute', left: 12, bottom: 12, display: 'flex', gap: 6, alignItems: 'center',
        background: 'var(--glass)', backdropFilter: 'blur(14px)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-sm)', padding: '5px 9px', fontSize: 11.5, color: 'var(--ink-2)',
      }}>
        <span>{`${postas.length} desenhos · ${Math.round((t.z / zAjuste) * 100)}%`}</span>
      </div>

      <div style={{
        position: 'absolute', right: 12, bottom: 12, display: 'flex', gap: 6,
      }}>
        {[
          [<Minus key="-" size={14} />, () => ampliarNoCentro(1 / PASSO_RODA), 'Afastar'],
          [<Plus key="+" size={14} />, () => ampliarNoCentro(PASSO_RODA), 'Aproximar'],
          [<Maximize2 key="f" size={14} />, ajustar, 'Ver tudo'],
        ].map(([icone, acao, rotulo], i) => (
          <button
            key={i}
            onClick={acao as () => void}
            title={rotulo as string}
            aria-label={rotulo as string}
            style={{
              width: 30, height: 30, display: 'grid', placeItems: 'center', cursor: 'pointer',
              background: 'var(--glass)', backdropFilter: 'blur(14px)',
              border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--ink-2)',
            }}
          >
            {icone as React.ReactNode}
          </button>
        ))}
      </div>
    </div>
  )

  function ampliarNoCentro(fator: number) {
    const r = caixaRef.current?.getBoundingClientRect()
    if (!r) return
    ampliar(fator, { x: r.width / 2, y: r.height / 2 })
  }
}

/** A envolvente só serve se as quatro pontas existem e têm área. */
function normalizar(caixa: Record<string, number> | undefined): Caixa | null {
  if (!caixa) return null
  const { xmin, ymin, xmax, ymax } = caixa
  const numeros = [xmin, ymin, xmax, ymax]
  if (numeros.some((n) => typeof n !== 'number' || !Number.isFinite(n))) return null
  if (xmax <= xmin || ymax <= ymin) return null
  return { xmin, ymin, xmax, ymax }
}

function envolvente(caixas: Caixa[]): Caixa {
  return {
    xmin: Math.min(...caixas.map((c) => c.xmin)),
    ymin: Math.min(...caixas.map((c) => c.ymin)),
    xmax: Math.max(...caixas.map((c) => c.xmax)),
    ymax: Math.max(...caixas.map((c) => c.ymax)),
  }
}

export default Panorama
