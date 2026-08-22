/**
 * A mira está sobre a linha NA TELA? — a bancada que fechou a segunda metade do D90.
 *
 * **Existe porque "a coordenada está certa" não é a mesma pergunta que "está em
 * cima da linha".** As bancadas de backend ([conferir_snap.py](conferir_snap.py))
 * comparam o sidecar com a geometria do SVG e respondem a primeira. Elas deram
 * mediana 0,00 px enquanto o dono continuava vendo a mira fora do traço — e as
 * duas coisas eram verdade ao mesmo tempo. O que faltava medir era a **tinta**.
 *
 * A armadilha estava no caminho de pintura. Toda medição anterior desenhou o SVG
 * num `<canvas>` (`drawImage`), que re-rasteriza limpo na resolução do destino.
 * A página real fazia outra coisa: dispunha o `<img>` no tamanho natural e o
 * ampliava por `transform: scale(z)`. O navegador rasteriza o SVG UMA vez, no
 * tamanho de layout, e estica o bitmap — a 81× cada pixel do raster vira um
 * bloco de 38 px, e o traço aparece deslocado de onde ele matematicamente está.
 *
 * Os três modos abaixo isolam isso. `A` é o que o app fazia; `C` é o conserto
 * (crescer a CAIXA e deixar o navegador re-rasterizar o vetor). Medido na `001`,
 * a 81×, na escala real de uma janela de trabalho:
 *
 *     A  transform: scale        mediana 3,16 px · p90 16,00 px · máx 17,89 px · 45% em cima
 *     B  idem, sem crisp-edges   idêntico a A  (image-rendering NÃO é a causa)
 *     C  caixa no tamanho final  mediana 0,00 px · p90  0,00 px · máx  1,00 px · 100% em cima
 *
 * **A janela importa, e é o erro fácil de cometer aqui.** O desvio é proporcional
 * a quanto o bitmap é esticado, que depende do `zAjuste` — logo, do tamanho da
 * janela. Medindo numa janela de 320 px o mesmo defeito aparece como 4,5 px e
 * parece tolerável; na janela real de ~1600 px ele é 17,9 px. Passe a largura da
 * janela de verdade, ou a bancada mente para o lado confortável.
 *
 * Uso:
 *
 *     docker run -d --name pw-snap -w /w mcr.microsoft.com/playwright:v1.49.0-noble sleep 3600
 *     docker cp folha.svg  pw-snap:/w/folha.svg      # da derivada, ver conferir_snap.py
 *     docker cp folha.snap pw-snap:/w/folha.snap
 *     docker cp ferramentas/medicao/aferir_tela_snap.mjs pw-snap:/w/
 *     docker exec pw-snap sh -c 'cd /w && npm i playwright@1.49.0 --no-audit --no-fund \
 *        && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright node aferir_tela_snap.mjs 81 20 1623'
 *
 *     argumentos: <zoom> <quantos pontos> <largura da janela em px>
 */
import { chromium } from 'playwright'
import fs from 'fs'

const SVG_ORIG = fs.readFileSync('/w/folha.svg', 'utf8')
const BIN = fs.readFileSync('/w/folha.snap')

/** Zoom em que se afere. 81× é o do relato original do D90. */
const ZOOM = Number(process.argv[2] || 81)
const QUANTOS = Number(process.argv[3] || 20)
/** Largura da janela. Ver o cabeçalho: medir pequeno esconde o defeito. */
const LADO = Number(process.argv[4] || 1623)

/** Espelha `espessura.ts` — o app reemite o SVG para o traço ficar com ~1,1 px.
 *  Sem isto o traço sai grosso e o desvio se esconde dentro da espessura. */
const PX_MAIS_FINA = 1.1
const PX_MAIS_GROSSA = 4
const ESTILO = /<style>[\s\S]*<\/style>/

// --- sidecar (formato em motores/snap.py::empacotar) ------------------------
const dv = new DataView(BIN.buffer, BIN.byteOffset, BIN.byteLength)
if (BIN.subarray(0, 5).toString() !== 'SNAP1') {
  console.error('sidecar não começa com SNAP1'); process.exit(1)
}
const n = dv.getUint32(5, true)
const xs = new Float32Array(n), ys = new Float32Array(n)
for (let i = 0; i < n; i++) xs[i] = dv.getFloat32(14 + 4 * i, true)
for (let i = 0; i < n; i++) ys[i] = dv.getFloat32(14 + 4 * n + 4 * i, true)
const tipos = BIN.subarray(14 + 8 * n, 14 + 9 * n)

const vb = SVG_ORIG.match(/viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)/)
const vbW = Number(vb[1]), vbH = Number(vb[2])

function comEspessura(texto, larguraNaTela, larguraNoAjuste) {
  const bloco = texto.match(ESTILO)
  if (!bloco) return texto
  const regras = []
  const porRegra = /\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}/g
  let a
  while ((a = porRegra.exec(bloco[0])) !== null) {
    const medida = Number((a[2].match(/stroke-width:\s*([\d.]+)/) || [])[1])
    regras.push({ classe: a[1], largura: Number.isFinite(medida) ? medida : null, corpo: a[2] })
  }
  if (!regras.some((r) => r.largura !== null)) return texto
  const unidadesPorPixel = vbW / Math.max(larguraNaTela, 1)
  const fator = larguraNoAjuste > 0 ? Math.min(1, larguraNaTela / larguraNoAjuste) : 1
  const medidas = regras.map((r) => r.largura).filter((w) => w !== null && w > 0)
  const fina = medidas.length ? Math.min(...medidas) : 1
  const estilos = regras.map((r) => {
    if (r.largura === null || r.largura <= 0) return `<style>.${r.classe} {${r.corpo}}</style>`
    const px = Math.min(PX_MAIS_FINA * (r.largura / fina), PX_MAIS_GROSSA) * fator
    const w = Math.max(px * unidadesPorPixel, 1e-6)
    const sem = r.corpo.replace(/stroke-width:\s*[\d.]+;?\s*/, '')
    return `<style>.${r.classe} {${sem}stroke-width: ${w.toFixed(6)};}</style>`
  }).join('')
  const i = bloco.index ?? 0
  return texto.slice(0, i) + estilos + texto.slice(i + bloco[0].length)
}

// Só EXTREMIDADE: é "a ponta da linha" do relato, e o caso em que a mira é usada.
const alvos = []
const passo = Math.max(1, Math.floor(n / (QUANTOS * 3)))
for (let i = 0; i < n && alvos.length < QUANTOS; i += passo) {
  if (tipos[i] === 0) alvos.push({ i, x: xs[i], y: ys[i] })
}
if (!alvos.length) { console.error('nenhuma extremidade no sidecar'); process.exit(1) }

const navegador = await chromium.launch()
const pagina = await navegador.newPage({ viewport: { width: LADO, height: LADO } })

const uri0 = `data:image/svg+xml;base64,${Buffer.from(SVG_ORIG).toString('base64')}`
await pagina.setContent(`<body style="margin:0"><img id="i" src="${uri0}"></body>`)
await pagina.waitForFunction(() => document.getElementById('i').naturalWidth > 0)
const base = await pagina.evaluate(({ vbW, vbH, LADO }) => {
  const largura = document.getElementById('i').naturalWidth
  const altura = largura / (vbW / vbH)
  return { largura, altura, zAjuste: Math.min(LADO / largura, LADO / altura) * 0.94 }
}, { vbW, vbH, LADO })

const z = base.zAjuste * ZOOM
const larguraNaTela = base.largura * z
const uri = `data:image/svg+xml;base64,${Buffer.from(
  comEspessura(SVG_ORIG, larguraNaTela, base.largura * base.zAjuste)).toString('base64')}`

const fundo = (SVG_ORIG.match(/<rect fill="#([0-9a-fA-F]{6})"/) || [, '212830'])[1]
const rgbFundo = [0, 2, 4].map((k) => parseInt(fundo.slice(k, k + 2), 16))

console.log(`${n} pontos no sidecar · ${alvos.length} extremidades aferidas · zoom ${ZOOM}x`)
console.log(`janela ${LADO} px · img natural ${base.largura} px · fator de tela ${z.toFixed(2)}x`)
console.log(`(no modo A cada pixel do raster vira um bloco de ${z.toFixed(1)} px)\n`)

async function medir(nome, cfg) {
  const estilo = cfg.reraster
    ? `width:${larguraNaTela}px;height:${base.altura * z}px;image-rendering:auto`
    : `width:${base.largura}px;height:${base.altura}px;`
      + `image-rendering:${cfg.crisp ? 'crisp-edges' : 'auto'}`
  await pagina.setContent(`
<body style="margin:0;background:rgb(${rgbFundo.join(',')})">
<div style="position:relative;width:${LADO}px;height:${LADO}px;overflow:hidden">
  <img id="i" src="${uri}" draggable="false" style="
      position:absolute;top:0;left:0;transform-origin:0 0;${estilo};
      user-select:none;max-width:none"></div></body>`)
  await pagina.waitForFunction(() => document.getElementById('i').naturalWidth > 0)

  const ds = []
  for (const alvo of alvos) {
    // Centraliza o alvo: `paraTela(alvo)` cai exatamente no centro da janela,
    // que é onde a mira seria desenhada. A distância medida do centro até a
    // tinta É o desvio que o olho vê.
    const tx = LADO / 2 - alvo.x * larguraNaTela
    const ty = LADO / 2 - alvo.y * larguraNaTela
    await pagina.evaluate(({ tx, ty, z, reraster }) => {
      document.getElementById('i').style.transform = reraster
        ? `translate(${tx}px, ${ty}px)`
        : `translate(${tx}px, ${ty}px) scale(${z})`
    }, { tx, ty, z, reraster: !!cfg.reraster })

    const buf = await pagina.screenshot({ type: 'png' })
    ds.push(await pagina.evaluate(async ({ b64, LADO, rgbFundo }) => {
      const img = new Image(); img.src = `data:image/png;base64,${b64}`; await img.decode()
      const cv = document.createElement('canvas'); cv.width = cv.height = LADO
      const ctx = cv.getContext('2d', { willReadFrequently: true }); ctx.drawImage(img, 0, 0)
      const d = ctx.getImageData(0, 0, LADO, LADO).data
      const c = (LADO - 1) / 2
      let melhor = Infinity
      for (let y = 0; y < LADO; y++) for (let x = 0; x < LADO; x++) {
        const k = 4 * (y * LADO + x)
        // Tinta = DIFERENÇA do fundo, nunca luminância: as linhas da `001` são
        // vermelhas (luminância 85) sobre fundo #212830 (luminância 40), e um
        // limiar de brilho as classifica como fundo. Foi assim que a primeira
        // passada desta família de teste devolveu "nenhum traço" para tudo.
        const dif = Math.abs(d[k] - rgbFundo[0]) + Math.abs(d[k + 1] - rgbFundo[1])
                  + Math.abs(d[k + 2] - rgbFundo[2])
        if (dif > 30) { const dd = Math.hypot(x - c, y - c); if (dd < melhor) melhor = dd }
      }
      return melhor
    }, { b64: buf.toString('base64'), LADO, rgbFundo }))
  }

  const ok = ds.filter(Number.isFinite).sort((a, b) => a - b)
  const emCima = ok.filter((v) => v <= 1).length
  console.log(nome)
  console.log(`   mediana ${ok[Math.floor(ok.length / 2)].toFixed(2)} px · `
    + `p90 ${ok[Math.floor(ok.length * 0.9)].toFixed(2)} px · `
    + `máx ${ok[ok.length - 1].toFixed(2)} px · `
    + `EM CIMA ${emCima}/${ds.length} (${(100 * emCima / ds.length).toFixed(0)}%)`)
  return ok[Math.floor(ok.length / 2)]
}

await medir('A  transform: scale        (o que o app fazia antes do conserto)', { crisp: true })
await medir('B  idem, sem crisp-edges   (controle: image-rendering não é a causa)', { crisp: false })
const c = await medir('C  caixa no tamanho final (o conserto — re-rasteriza o vetor)', { reraster: true })

console.log(c <= 1
  ? '\n✓ com a caixa no tamanho final a mira fica sobre o traço'
  : '\n✗ nem re-rasterizando a mira cai sobre o traço — o defeito é outro, '
    + 'volte para a conferir_snap.py')

await navegador.close()
