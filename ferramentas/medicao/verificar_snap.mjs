/**
 * Bancada do snap — o índice descreve mesmo o desenho que está na tela?
 *
 * **Existe porque pixel não se afere no olho.** Três tentativas de consertar o
 * desalinhamento da mira ([D90](../../docs/historico-correcoes.md)) falharam por
 * diagnóstico aritmético: as hipóteses eram plausíveis, calculáveis e erradas.
 * O que fecha esse tipo de caso é perguntar ao navegador.
 *
 * **Comece pela [conferir_snap.py](conferir_snap.py) ao lado.** Ela responde as
 * mesmas perguntas 1 e 3 em Python puro, em segundos, sem contêiner de
 * Playwright — e foi ela que fechou o D90, cujos dois defeitos eram os dois de
 * backend. Esta bancada aqui é a que responde a pergunta 2, que só o navegador
 * sabe: use-a quando a suspeita for da transformação do frontend.
 *
 * Três perguntas, nesta ordem — pare na primeira que falhar:
 *
 * 1. **cabe na folha?**  extensão do índice contra a da geometria desenhada;
 * 2. **a transformação erra quanto?**  `getScreenCTM()` do browser contra o
 *    `paraTela` da vista, para um vértice conhecido;
 * 3. **há traço onde a mira gruda?**  canvas ampliado em volta de pontos reais
 *    do sidecar, procurando o pixel de traço mais próximo.
 *
 * Uso (o relato completo do D90 está no histórico de correções):
 *
 *     docker run -d --name pw-snap -w /w mcr.microsoft.com/playwright:v1.49.0-noble sleep 3600
 *     docker exec -i pw-snap sh -c 'cat > /w/verificar_snap.mjs' < ferramentas/medicao/verificar_snap.mjs
 *     docker exec -i pw-snap sh -c 'cat > /w/folha.svg'  < folha.svg
 *     docker exec -i pw-snap sh -c 'cat > /w/folha.snap' < folha.snap
 *     docker exec pw-snap sh -c 'cd /w && npm i playwright@1.49.0 --no-audit --no-fund \
 *        && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright node verificar_snap.mjs'
 *
 * O SVG e o sidecar saem do banco — ver `exportar_folha.py` ao lado.
 */
import { chromium } from 'playwright'
import fs from 'fs'

const SVG = fs.readFileSync('/w/folha.svg', 'utf8')
const BIN = fs.readFileSync('/w/folha.snap')

//: Zoom em que se afere. 81× é o do relato original do D90 — a borda do glifo
//: (raio 7 px) alinhava com a linha ali, o que dava a régua do desvio.
const ZOOM = 81

// ---------------------------------------------------------------------------
// o sidecar (formato em motores/snap.py::empacotar)
// ---------------------------------------------------------------------------
const dv = new DataView(BIN.buffer, BIN.byteOffset, BIN.byteLength)
if (BIN.subarray(0, 5).toString() !== 'SNAP1') {
  console.error('sidecar não começa com SNAP1'); process.exit(1)
}
const n = dv.getUint32(5, true), m = dv.getUint32(9, true)
const truncado = BIN[13] === 1
const xs = new Float32Array(n), ys = new Float32Array(n)
for (let i = 0; i < n; i++) xs[i] = dv.getFloat32(14 + 4 * i, true)
for (let i = 0; i < n; i++) ys[i] = dv.getFloat32(14 + 4 * n + 4 * i, true)
const tipos = BIN.subarray(14 + 8 * n, 14 + 9 * n)
const NOME = ['extremidade', 'meio', 'centro', 'quadrante', 'no', 'intersecao']

const vb = SVG.match(/viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)/)
const vbW = Number(vb[1]), vbH = Number(vb[2])
const alturaDaFolha = vbH / vbW

console.log(`sidecar: ${n} pontos, ${m} segmentos, truncado=${truncado}`)
console.log(`viewBox: ${vbW} x ${vbH}  (folha vai de 0..1 em X e 0..${alturaDaFolha.toFixed(5)} em Y)`)

// ---------------------------------------------------------------------------
// 1. cabe na folha?
// ---------------------------------------------------------------------------
let ix0 = Infinity, ix1 = -Infinity, iy0 = Infinity, iy1 = -Infinity
for (let i = 0; i < n; i++) {
  if (xs[i] < ix0) ix0 = xs[i]; if (xs[i] > ix1) ix1 = xs[i]
  if (ys[i] < iy0) iy0 = ys[i]; if (ys[i] > iy1) iy1 = ys[i]
}
const desenhados = [...SVG.matchAll(/[ML]\s*([-\d.eE]+)\s+([-\d.eE]+)/g)]
  .map((g) => [Number(g[1]) / vbW, Number(g[2]) / vbW])
let sx0 = Infinity, sx1 = -Infinity, sy0 = Infinity, sy1 = -Infinity
for (const [a, b] of desenhados) {
  if (a < sx0) sx0 = a; if (a > sx1) sx1 = a
  if (b < sy0) sy0 = b; if (b > sy1) sy1 = b
}
const f = (v) => v.toFixed(5).padStart(12)
console.log('\n[1] EXTENSÃO — índice contra geometria desenhada')
console.log(`    índice x: ${f(ix0)} .. ${f(ix1)}     y: ${f(iy0)} .. ${f(iy1)}`)
console.log(`    svg    x: ${f(sx0)} .. ${f(sx1)}     y: ${f(sy0)} .. ${f(sy1)}`)
const forA = ix1 > 1.05 || ix0 < -0.05 || iy1 > alturaDaFolha + 0.05 || iy0 < -0.05
console.log(forA
  ? '    ✗ o índice tem geometria QUE A FOLHA NÃO DESENHA (ver §14.9 da planta)'
  : '    ✓ o índice cabe na folha')

const navegador = await chromium.launch()
const pagina = await navegador.newPage({ viewport: { width: 500, height: 500 } })
const dataUri = `data:image/svg+xml;base64,${Buffer.from(SVG).toString('base64')}`
await pagina.setContent(`<body style="margin:0"><img id="i" src="${dataUri}"></body>`)
await pagina.waitForFunction(() => document.getElementById('i').naturalWidth > 0)

// ---------------------------------------------------------------------------
// 2. a transformação imagem -> tela erra quanto?
// ---------------------------------------------------------------------------
const alvo = desenhados[Math.min(20, desenhados.length - 1)]
const erro = await pagina.evaluate(({ svg, vbW, vbH, nx, ny }) => {
  const img = document.getElementById('i')
  const largura = img.naturalWidth              // o que o `Vista2D` usa
  const caixa = document.createElement('div')
  caixa.innerHTML = svg
  const el = caixa.querySelector('svg')
  // a MESMA caixa que a vista aplica: largura natural, altura pelo aspecto exato
  el.setAttribute('width', largura)
  el.setAttribute('height', largura / (vbW / vbH))
  el.style.cssText = 'position:absolute;top:0;left:0'
  document.body.appendChild(el)
  const p = el.createSVGPoint()
  p.x = nx * vbW; p.y = ny * vbW
  const real = p.matrixTransform(el.getScreenCTM())
  return { x: real.x - nx * largura, y: real.y - ny * largura, largura }
}, { svg: SVG, vbW, vbH, nx: alvo[0], ny: alvo[1] })

console.log('\n[2] TRANSFORMAÇÃO — browser contra o paraTela da vista')
console.log(`    erro no ajuste : ${erro.x.toFixed(5)} px em X, ${erro.y.toFixed(5)} px em Y`)
console.log(`    erro a ${ZOOM}x     : ${(erro.x * ZOOM).toFixed(2)} px em X, ${(erro.y * ZOOM).toFixed(2)} px em Y`)
console.log(Math.max(Math.abs(erro.x), Math.abs(erro.y)) * ZOOM > 1
  ? '    ✗ a transformação erra mais de 1 px no zoom de referência'
  : '    ✓ a transformação é exata para o que a mira precisa')

// ---------------------------------------------------------------------------
// 3. há traço desenhado onde a mira gruda?
// ---------------------------------------------------------------------------
const amostra = []
for (let i = 0; i < n && amostra.length < 12; i += Math.floor(n / 13) + 1) {
  amostra.push({ i, x: xs[i], y: ys[i], tipo: NOME[tipos[i]] ?? tipos[i] })
}
const fundo = (SVG.match(/<rect fill="#([0-9a-fA-F]{6})"/) || [, '212830'])[1]
const rgbFundo = [0, 2, 4].map((k) => parseInt(fundo.slice(k, k + 2), 16))

const pixels = await pagina.evaluate(({ amostra, ZOOM, rgbFundo }) => {
  const img = document.getElementById('i')
  const nW = img.naturalWidth
  const LADO = 161
  const cv = document.createElement('canvas')
  cv.width = cv.height = LADO
  const ctx = cv.getContext('2d', { willReadFrequently: true })
  const centro = (LADO - 1) / 2
  return amostra.map((a) => {
    const px = a.x * nW, py = a.y * nW
    ctx.fillStyle = `rgb(${rgbFundo.join(',')})`
    ctx.fillRect(0, 0, LADO, LADO)
    ctx.drawImage(img, px - LADO / (2 * ZOOM), py - LADO / (2 * ZOOM),
                  LADO / ZOOM, LADO / ZOOM, 0, 0, LADO, LADO)
    const d = ctx.getImageData(0, 0, LADO, LADO).data
    let melhor = Infinity
    for (let y = 0; y < LADO; y++) for (let x = 0; x < LADO; x++) {
      const o = (y * LADO + x) * 4
      // **Diferença do FUNDO, nunca luminância.** Linha vermelha (lum 85) sobre
      // fundo #212830 (lum 40) é mais escura que muitos limiares de brilho: um
      // detector por luminância classifica o traço como fundo e devolve "não há
      // traço" para o desenho inteiro.
      const dif = Math.abs(d[o] - rgbFundo[0]) + Math.abs(d[o + 1] - rgbFundo[1])
                + Math.abs(d[o + 2] - rgbFundo[2])
      if (dif < 60) continue
      const dist = Math.hypot(x - centro, y - centro)
      if (dist < melhor) melhor = dist
    }
    return { ...a, dist: melhor === Infinity ? null : +melhor.toFixed(2) }
  })
}, { amostra, ZOOM, rgbFundo })

console.log(`\n[3] PIXEL — há traço onde o ponto gruda? (janela a ${ZOOM}x, fundo #${fundo})`)
for (const p of pixels) {
  console.log(`    ${String(p.i).padStart(8)}  ${String(p.tipo).padEnd(12)} `
            + `dist=${p.dist === null ? '  SEM TRAÇO' : String(p.dist).padStart(6) + ' px'}`)
}
const achados = pixels.map((p) => p.dist).filter((v) => v !== null)
const semTraco = pixels.length - achados.length
console.log(`\n    ${achados.length}/${pixels.length} sobre traço`
          + (achados.length ? ` · máx ${Math.max(...achados)} px` : ''))
console.log(semTraco
  ? `    ✗ ${semTraco} ponto(s) sem traço nenhum na janela — não são do desenho visível`
  : '    ✓ todo ponto amostrado cai sobre traço desenhado')

await navegador.close()
process.exit(forA || semTraco ? 1 : 0)
