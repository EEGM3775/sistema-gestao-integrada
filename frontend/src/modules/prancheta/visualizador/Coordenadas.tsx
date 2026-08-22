import { useCallback, useEffect, useRef, useState } from 'react'
import { Copy, Crosshair } from 'lucide-react'
import type { Ponto } from '../types'
import { NOME_DO_TIPO } from './snap'
import type { Achado } from './snap'

/**
 * O leitor de coordenadas — a barra de status do CAD, no canto da prancha.
 *
 * **Por que existe.** O AutoCAD mostra onde o cursor está o tempo todo, e isso
 * não é enfeite: é como quem desenha percebe que a tela e o desenho discordam
 * *antes* de gravar uma medida errada. Aqui a necessidade é a mesma e ficou
 * óbvia perseguindo o D90 — a mira parecia fora do traço, mas ninguém conseguia
 * dizer *quanto* fora, nem em que direção, nem se piorava com o zoom. Sem número
 * na tela, a conversa vira "parece torto", e "parece torto" não se conserta.
 *
 * **O que ele mostra, e por que cada linha está aqui.** A posição do ponteiro
 * em fração de folha (a coordenada em que TUDO neste módulo é gravado), em
 * milímetros de papel (a linguagem de quem confere contra a prancha impressa) e
 * em unidades do `viewBox` (o número exato que o backend indexou no sidecar).
 * Junto, o ponto que o snap escolheu e o **Δ em pixels de tela** entre os dois —
 * que é a medida do desconforto: com o cursor em cima do traço, o Δ é o
 * afastamento da mira, em número, agora.
 *
 * **E a régua da própria tela.** As três últimas linhas não descrevem o desenho,
 * descrevem a *pintura*: a caixa que a vista pediu ao navegador, a caixa que o
 * navegador de fato deu, o `viewBox` e o papel. Se pedida e real divergirem, o
 * desenho está sendo pintado numa escala diferente da que a mira usa para se
 * posicionar — e o erro cresce com o zoom, exatamente como se relatou. Essa
 * linha existe para essa suspeita morrer ou se confirmar em um olhar.
 *
 * **Ele se escreve por fora do React, de propósito.** O ponteiro emite dezenas
 * de eventos por segundo; virar estado faria a árvore inteira — inclusive a
 * camada com todas as marcações — re-renderizar a 60 Hz, travando a prancha
 * justamente enquanto se mede. A vista publica uma função de escrita e este
 * componente atualiza os próprios nós de texto. É a mesma razão pela qual o
 * índice de snap vive em `ref` no `Visualizador`.
 */

/**
 * A ponte de volta à coordenada do CAD, medida na emissão da folha.
 *
 * `null` quando a folha não a traz (convertida antes de a medida existir, ou
 * origem sem geometria vetorial). Aí o leitor mostra as réguas dele e diz que
 * não sabe — **coordenada errada com cara de certa é o que não se faz aqui**.
 */
export interface Mundo {
  origem_x: number
  origem_y: number
  por_folha: number
}

/** O que a vista sabe da pintura corrente — a régua da tela, não do desenho. */
export interface Instrumento {
  /** A coordenada de desenho desta folha, quando ela existe. */
  mundo: Mundo | null
  /** Pixels de tela por 1,0 de coordenada de folha (= a largura na tela). */
  escala: number
  /** Zoom relativo ao "ajustar à tela" — o mesmo número do distintivo ao lado. */
  zoom: number
  viewBox: { largura: number; altura: number } | null
  papelMm: { largura: number; altura: number } | null
  /** A caixa que a vista PEDIU ao `<img>`, em px de tela. */
  pedida: { largura: number; altura: number } | null
  /** A caixa que o navegador realmente deu, medida no DOM. */
  real: { largura: number; altura: number } | null
  /** O que sobrou para o `transform: scale()` — 1 em todo zoom praticável. */
  resto: number
}

/** Os campos que o ponteiro reescreve a cada movimento. */
type Campo =
  | 'pilula' | 'dwx' | 'dwy' | 'x' | 'y' | 'mmx' | 'mmy' | 'ux' | 'uy'
  | 'dx' | 'dy' | 'dpx' | 'gdist' | 'gang'
const CAMPOS: Campo[] = [
  'pilula', 'dwx', 'dwy', 'x', 'y', 'mmx', 'mmy', 'ux', 'uy',
  'dx', 'dy', 'dpx', 'gdist', 'gang',
]

/**
 * Coordenada de folha → coordenada do CAD.
 *
 * O Y inverte porque o SVG cresce para baixo e o desenho, para cima; e o fator é
 * o MESMO nos dois eixos porque `Ponto` normaliza x e y pela **largura**, que é o
 * que preserva o aspecto (ver o contrato em `types.ts`).
 */
function noDesenho(p: Ponto, m: Mundo): { x: number; y: number } {
  return { x: m.origem_x + p.x * m.por_folha, y: m.origem_y - p.y * m.por_folha }
}

/**
 * Casas decimais da coordenada de desenho: **cinco, sempre**.
 *
 * Decisão do dono (15/08/2026), e é a mesma régua do CAD: todo projeto tem cinco
 * casas, do arquivo à tela. Não é formatação — é o contrato que a grade do SVG,
 * o `float64` do sidecar e a tolerância de fusão foram dimensionados para
 * cumprir (`dxf.py::PRECISAO_DE_DESENHO`). Mostrar menos esconderia justamente
 * o dígito em que o desvio da mira aparecia; mostrar mais anunciaria precisão
 * que a folha não carrega.
 */
const CASAS_DE_DESENHO = 5

export function Coordenadas({
  mira,
  ancora,
  instrumento,
  registrar,
}: {
  mira?: Achado | null
  /** O último vértice do gesto em andamento — a origem do "para onde vai". */
  ancora?: Ponto | null
  instrumento: Instrumento
  /** A vista chama isto uma vez para receber o escritor do ponteiro. */
  registrar: (escrever: ((p: Ponto | null) => void) | null) => void
}) {
  const [aberto, setAberto] = useState(false)
  const [copiado, setCopiado] = useState<'sim' | 'nao' | null>(null)
  const campos = useRef<Partial<Record<Campo, HTMLSpanElement | null>>>({})
  const ultimo = useRef<Ponto | null>(null)

  // Refs e não props dentro do escritor: ele é chamado fora do ciclo do React e
  // precisa do valor de AGORA, não do que estava em escopo quando foi criado.
  const miraRef = useRef(mira)
  miraRef.current = mira
  const ancoraRef = useRef(ancora)
  ancoraRef.current = ancora
  const instRef = useRef(instrumento)
  instRef.current = instrumento

  const escrever = useCallback((p: Ponto | null) => {
    ultimo.current = p
    const c = campos.current
    if (!c.pilula) return
    const por = (campo: Campo, texto: string) => {
      const no = c[campo]
      if (no) no.textContent = texto
    }
    if (!p) {
      for (const campo of CAMPOS) por(campo, '—')
      return
    }
    const inst = instRef.current
    const alvo = miraRef.current
    // **A coordenada do desenho primeiro** — é a única que existia antes de nós
    // e a única comparável com o arquivo aberto no CAD. As outras três são
    // réguas nossas, e vêm depois porque servem para conferir a conversão, não
    // para conferir o projeto.
    const m = inst.mundo
    if (m) {
      const d = noDesenho(p, m)
      por('dwx', emDesenho(d.x))
      por('dwy', emDesenho(d.y))
    } else {
      por('dwx', '—'); por('dwy', '—')
    }
    por('x', p.x.toFixed(6).replace('.', ','))
    por('y', p.y.toFixed(6).replace('.', ','))
    // Fator ÚNICO nos dois eixos: `Ponto` normaliza x e y pela LARGURA, e é o
    // que preserva o aspecto (ver o contrato em `types.ts`). Dividir y pela
    // altura aqui daria um número bonito e errado.
    const mm = inst.papelMm?.largura ?? null
    por('mmx', mm ? milimetros(p.x * mm) : '—')
    por('mmy', mm ? milimetros(p.y * mm) : '—')
    const vb = inst.viewBox?.largura ?? null
    por('ux', vb ? Math.round(p.x * vb).toLocaleString('pt-BR') : '—')
    por('uy', vb ? Math.round(p.y * vb).toLocaleString('pt-BR') : '—')
    // A pílula fechada mostra a coordenada do DESENHO quando a folha a traz —
    // é a que o AutoCAD mostraria, e é a que se quer de relance. Sem ela, cai
    // para milímetro de papel e depois para unidade de `viewBox`; nunca "— mm",
    // que faz o instrumento parecer quebrado quando ele está funcionando.
    if (m) {
      // A pílula também mostra as cinco: ela é a barra de status, e a barra de
      // status do CAD não abrevia a coordenada. Truncar aqui e mostrar inteiro
      // no painel faria dois números diferentes para o mesmo ponto.
      const d = noDesenho(p, m)
      por('pilula', `${emDesenho(d.x)} · ${emDesenho(d.y)}`)
    } else {
      por('pilula',
        mm ? `${milimetros(p.x * mm)} · ${milimetros(p.y * mm)} mm`
          : vb ? `${Math.round(p.x * vb).toLocaleString('pt-BR')} · ${Math.round(p.y * vb).toLocaleString('pt-BR')} u`
            : `${p.x.toFixed(4).replace('.', ',')} · ${p.y.toFixed(4).replace('.', ',')}`)
    }
    if (alvo) {
      const dx = (alvo.ponto.x - p.x) * inst.escala
      const dy = (alvo.ponto.y - p.y) * inst.escala
      por('dx', comSinal(dx))
      por('dy', comSinal(dy))
      por('dpx', Math.hypot(dx, dy).toFixed(1).replace('.', ','))
    } else {
      por('dx', '—'); por('dy', '—'); por('dpx', '—')
    }

    // "Para onde está indo": distância e rumo desde o último vértice, que é a
    // entrada dinâmica do AutoCAD. Sai do ponto do SNAP quando ele está aceso,
    // e não do cursor cru — porque é ele que o clique vai gravar; mostrar a
    // distância até o cursor seria anunciar uma medida diferente da que sai.
    const origem = ancoraRef.current
    const destino = alvo?.ponto ?? p
    if (origem) {
      const vx = destino.x - origem.x
      const vy = destino.y - origem.y
      por('gdist', mm
        ? `${milimetros(Math.hypot(vx, vy) * mm)} mm`
        : Math.hypot(vx, vy).toFixed(6).replace('.', ','))
      // Anti-horário a partir do leste, como no CAD. O `-vy` é porque o y da
      // tela cresce para BAIXO e o do transferidor, para cima.
      const grau = (Math.atan2(-vy, vx) * 180 / Math.PI + 360) % 360
      por('gang', `${grau.toFixed(1).replace('.', ',')}°`)
    } else {
      por('gdist', '—'); por('gang', '—')
    }
  }, [])

  useEffect(() => {
    registrar(escrever)
    return () => registrar(null)
  }, [registrar, escrever])

  // Abrir o painel monta nós de texto novos, e a mira muda o Δ sem o ponteiro se
  // mover: nos dois casos o que está escrito ficou velho. Reescrever com a
  // última posição conhecida é o que evita o painel abrir mostrando travessões.
  useEffect(() => { escrever(ultimo.current) }, [aberto, mira, ancora, instrumento, escrever])

  const copiar = () => {
    const texto = laudo(ultimo.current, mira, instrumento)
    navigator.clipboard?.writeText(texto)
      .then(() => setCopiado('sim'))
      // `clipboard` não existe fora de contexto seguro (o acesso por IP do
      // canteiro é um). Aí o texto é selecionado e o Ctrl+C da pessoa resolve —
      // melhor que um botão que não faz nada e não diz por quê.
      .catch(() => { selecionar(document.querySelector('[data-leitura]')); setCopiado('nao') })
    window.setTimeout(() => setCopiado(null), 2600)
  }

  const conferido = confereACaixa(instrumento)

  return (
    <div
      style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}
      // O leitor mora DENTRO da prancha, e sem isto o toque nele chegaria aos
      // gestos dela: em modo de medição, abrir o painel plantaria um vértice no
      // canto da tela — uma medida errada nascida de um clique em instrumento.
      onPointerDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      <button
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        title="Coordenadas do ponteiro, o ponto que o snap pegou e a régua da tela"
        className="num"
        style={{
          display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
          fontSize: 11, fontWeight: 600, color: 'var(--ink-3)',
          background: 'var(--glass)', border: '1px solid var(--line)',
          borderRadius: 999, padding: '3px 9px',
        }}
      >
        <Crosshair size={12} />
        <span ref={(n) => { campos.current.pilula = n }}>—</span>
      </button>

      {aberto && (
        <div
          data-leitura
          className="num"
          style={{
            position: 'absolute', left: 0, bottom: 34, width: 316,
            background: 'var(--surface)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-sm)',
            padding: '10px 12px', fontSize: 11, color: 'var(--ink-2)',
            display: 'grid', gap: 7,
          }}
        >
          <Bloco titulo="ponteiro">
            {/* A coordenada do desenho encabeça o painel. Quando a folha não a
                traz, a linha DIZ isso em vez de sumir — some, o leitor abaixo
                seria lido como se fosse ela. */}
            <Par
              rotulo="desenho"
              a={instrumento.mundo ? <Vao campo="dwx" campos={campos} /> : '—'}
              b={instrumento.mundo
                ? <Vao campo="dwy" campos={campos} />
                : <span style={{ color: 'var(--ink-3)' }}>reprocessar</span>}
            />
            <Par rotulo="folha" a={<Vao campo="x" campos={campos} />} b={<Vao campo="y" campos={campos} />} />
            <Par rotulo="papel" a={<><Vao campo="mmx" campos={campos} /> mm</>} b={<><Vao campo="mmy" campos={campos} /> mm</>} />
            <Par rotulo="viewBox" a={<Vao campo="ux" campos={campos} />} b={<Vao campo="uy" campos={campos} />} />
          </Bloco>

          <Bloco titulo={mira ? `snap · ${NOME_DO_TIPO[mira.tipo]}` : 'snap · nenhum'}>
            {/* O ponto que o clique vai gravar, na coordenada do CAD: é este o
                número que se confere contra o vértice aberto no AutoCAD. */}
            <Par
              rotulo="desenho"
              a={mira && instrumento.mundo
                ? emDesenho(noDesenho(mira.ponto, instrumento.mundo).x)
                : '—'}
              b={mira && instrumento.mundo
                ? emDesenho(noDesenho(mira.ponto, instrumento.mundo).y)
                : '—'}
            />
            <Par
              rotulo="folha"
              a={mira ? mira.ponto.x.toFixed(6).replace('.', ',') : '—'}
              b={mira ? mira.ponto.y.toFixed(6).replace('.', ',') : '—'}
            />
            {/* O número que interessa: com o cursor EM CIMA do traço, este Δ é o
                afastamento da mira, em pixels de tela, medido e não estimado. */}
            <Par
              rotulo="Δ tela"
              a={<><Vao campo="dx" campos={campos} /> px</>}
              b={<><Vao campo="dy" campos={campos} /> px</>}
              extra={<><Vao campo="dpx" campos={campos} /> px</>}
            />
          </Bloco>

          {/* Só aparece com gesto em curso: fora dele não há "de onde", e uma
              linha permanentemente vazia é ruído no instrumento. */}
          {ancora && (
            <Bloco titulo="do último vértice">
              <Par
                rotulo="rumo"
                a={<Vao campo="gdist" campos={campos} />}
                b={<Vao campo="gang" campos={campos} />}
              />
            </Bloco>
          )}

          <Bloco titulo="tela">
            <Linha rotulo="zoom" valor={`${formatar(instrumento.zoom)}×`} />
            <Linha rotulo="escala" valor={`${inteiro(instrumento.escala)} px / folha`} />
            <Linha
              rotulo="caixa"
              valor={instrumento.pedida
                ? `${inteiro(instrumento.pedida.largura)} × ${inteiro(instrumento.pedida.altura)}`
                : `scale(${formatar(instrumento.resto)}) — sem caixa`}
            />
            {/* Pedida ≠ real significa desenho pintado numa escala e mira
                posicionada em outra: o desvio nasce aqui e o zoom o multiplica. */}
            <Linha
              rotulo="real"
              valor={instrumento.real
                ? `${inteiro(instrumento.real.largura)} × ${inteiro(instrumento.real.altura)}`
                : '—'}
              estado={conferido}
            />
            <Linha
              rotulo="viewBox"
              valor={instrumento.viewBox
                ? `${inteiro(instrumento.viewBox.largura)} × ${inteiro(instrumento.viewBox.altura)}`
                : '—'}
            />
            <Linha
              rotulo="papel"
              valor={instrumento.papelMm
                ? `${milimetros(instrumento.papelMm.largura)} × ${milimetros(instrumento.papelMm.altura)} mm`
                : '—'}
            />
          </Bloco>

          <button
            onClick={copiar}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              cursor: 'pointer', fontSize: 11, fontWeight: 600, padding: '5px 0',
              color: 'var(--ink-2)', background: 'var(--surface-2)',
              border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
            }}
          >
            <Copy size={12} />
            {copiado === 'sim' ? 'copiado' : copiado === 'nao' ? 'selecionado — Ctrl+C' : 'copiar leitura'}
          </button>
        </div>
      )}
    </div>
  )
}

/** Um grupo com título — o painel tem três, e sem separação vira lista de números. */
function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gap: 2 }}>
      <div style={{
        fontSize: 9.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
        color: 'var(--ink-3)', borderBottom: '1px solid var(--line)', paddingBottom: 2,
      }}>
        {titulo}
      </div>
      {children}
    </div>
  )
}

function Par({ rotulo, a, b, extra }: {
  rotulo: string; a: React.ReactNode; b: React.ReactNode; extra?: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
      <span style={{ width: 48, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      <span style={{ flex: 1, color: 'var(--ink)' }}>{a}</span>
      <span style={{ flex: 1, color: 'var(--ink)' }}>{b}</span>
      {extra && <span style={{ color: 'var(--accent-ink)', fontWeight: 700 }}>{extra}</span>}
    </div>
  )
}

function Linha({ rotulo, valor, estado }: {
  rotulo: string; valor: string; estado?: 'confere' | 'diverge' | null
}) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
      <span style={{ width: 48, color: 'var(--ink-3)', flexShrink: 0 }}>{rotulo}</span>
      <span style={{ flex: 1, color: estado === 'diverge' ? 'var(--danger-ink)' : 'var(--ink)' }}>
        {valor}
      </span>
      {estado && (
        <span style={{ color: estado === 'diverge' ? 'var(--danger-ink)' : 'var(--good-ink)', fontWeight: 700 }}>
          {estado === 'diverge' ? 'diverge' : 'confere'}
        </span>
      )}
    </div>
  )
}

/** Um valor que o ponteiro reescreve por fora do React. */
function Vao({ campo, campos }: {
  campo: Campo
  campos: React.MutableRefObject<Partial<Record<Campo, HTMLSpanElement | null>>>
}) {
  return <span ref={(n) => { campos.current[campo] = n }}>—</span>
}

/**
 * A caixa pintada é a caixa pedida?
 *
 * Meio pixel de folga porque a caixa é pedida em fração e medida em `float`, e
 * exigir igualdade binária acenderia alarme falso o tempo todo. Meio pixel de
 * divergência, por outro lado, já é o bastante para deslocar a mira em zoom alto
 * — é erro relativo, e o zoom multiplica.
 */
function confereACaixa(i: Instrumento): 'confere' | 'diverge' | null {
  if (!i.pedida || !i.real) return null
  const folga = 0.5
  return Math.abs(i.pedida.largura - i.real.largura) <= folga
    && Math.abs(i.pedida.altura - i.real.altura) <= folga
    ? 'confere'
    : 'diverge'
}

/** O texto de uma tecla — tudo o que a leitura sabe, em bloco colável. */
function laudo(p: Ponto | null, mira: Achado | null | undefined, i: Instrumento): string {
  const mm = i.papelMm?.largura ?? null
  const vb = i.viewBox?.largura ?? null
  // Sem separador de milhar no laudo: ele vai colado num relato e o ponto de
  // milhar do pt-BR viraria ponto decimal na leitura de quem recebe.
  const noCad = (q: Ponto | null | undefined) =>
    q && i.mundo
      ? `${noDesenho(q, i.mundo).x.toFixed(CASAS_DE_DESENHO)} ${noDesenho(q, i.mundo).y.toFixed(CASAS_DE_DESENHO)}`
      : '— (folha sem coordenada de desenho)'
  const linhas = [
    `ponteiro  DESENHO ${noCad(p)}`,
    `          folha ${p ? `${p.x.toFixed(6)} ${p.y.toFixed(6)}` : '—'}`,
    `          papel ${p && mm ? `${(p.x * mm).toFixed(2)} ${(p.y * mm).toFixed(2)} mm` : '—'}`,
    `          viewBox ${p && vb ? `${(p.x * vb).toFixed(1)} ${(p.y * vb).toFixed(1)}` : '—'}`,
    `snap      ${mira ? NOME_DO_TIPO[mira.tipo] : 'nenhum'}`,
    `          DESENHO ${noCad(mira?.ponto)}`,
    `          folha ${mira ? `${mira.ponto.x.toFixed(6)} ${mira.ponto.y.toFixed(6)}` : '—'}`,
    `          viewBox ${mira && vb ? `${(mira.ponto.x * vb).toFixed(1)} ${(mira.ponto.y * vb).toFixed(1)}` : '—'}`,
  ]
  if (p && mira) {
    const dx = (mira.ponto.x - p.x) * i.escala
    const dy = (mira.ponto.y - p.y) * i.escala
    linhas.push(`          Δ tela ${dx.toFixed(2)} ${dy.toFixed(2)} px  (${Math.hypot(dx, dy).toFixed(2)} px)`)
  }
  linhas.push(
    `tela      zoom ${i.zoom.toFixed(3)}x · escala ${i.escala.toFixed(2)} px/folha · resto scale(${i.resto})`,
    `          caixa pedida ${i.pedida ? `${i.pedida.largura.toFixed(2)} x ${i.pedida.altura.toFixed(2)}` : '(sem caixa)'}`,
    `          caixa real   ${i.real ? `${i.real.largura.toFixed(2)} x ${i.real.altura.toFixed(2)}` : '—'}  [${confereACaixa(i) ?? 'sem medida'}]`,
    `          viewBox ${i.viewBox ? `${i.viewBox.largura} x ${i.viewBox.altura}` : '—'}`,
    `          papel   ${i.papelMm ? `${i.papelMm.largura} x ${i.papelMm.altura} mm` : '—'}`,
  )
  return linhas.join('\n')
}

function selecionar(no: Element | null | undefined) {
  if (!no) return
  const faixa = document.createRange()
  faixa.selectNodeContents(no)
  const selecao = window.getSelection()
  selecao?.removeAllRanges()
  selecao?.addRange(faixa)
}

/** Um número na régua do projeto: cinco casas, sempre — ver `CASAS_DE_DESENHO`. */
function emDesenho(v: number): string {
  return v.toLocaleString('pt-BR', {
    minimumFractionDigits: CASAS_DE_DESENHO,
    maximumFractionDigits: CASAS_DE_DESENHO,
  })
}

function milimetros(v: number): string {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

function inteiro(v: number): string {
  return Math.round(v).toLocaleString('pt-BR')
}

function formatar(v: number): string {
  return v >= 100 ? Math.round(v).toLocaleString('pt-BR')
    : v.toLocaleString('pt-BR', { maximumFractionDigits: 3 })
}

function comSinal(v: number): string {
  return `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1).replace('.', ',')}`
}
