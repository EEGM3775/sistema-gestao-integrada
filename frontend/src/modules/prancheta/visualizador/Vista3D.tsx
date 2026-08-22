import { useEffect, useRef, useState } from 'react'
import { Spinner } from '@/components/malha'

/**
 * Modelo 3D — o glTF binário (`.glb`) que o IfcOpenShell gerou do IFC.
 *
 * **Por que glTF e não Fragments** (planta §12.3): Fragments comprime melhor,
 * mas é gerado por biblioteca JS — plugá-lo no backend poria Node de volta,
 * contra a Fase 11 inteira, que acabou de tirá-lo. glTF é o denominador aberto
 * que o próprio `web-ifc` consome; se a compressão virar problema, ela entra
 * como passo **do frontend** sobre este mesmo glTF, sem serviço novo.
 *
 * O `three` entra por `import()` dinâmico dentro do efeito, e não no topo do
 * arquivo: ele é a dependência mais pesada do bundle e só quem abre um modelo
 * BIM deve pagá-la. Quem foi ver a planta baixa em PDF no celular não baixa
 * nada disso.
 */
export function Vista3D({ src }: { src: string }) {
  const caixaRef = useRef<HTMLDivElement>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(true)

  useEffect(() => {
    const caixa = caixaRef.current
    if (!caixa) return

    let vivo = true
    let quadro = 0
    let limpar = () => {}
    setCarregando(true)
    setErro(null)

    ;(async () => {
      const THREE = await import('three')
      const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js')
      const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js')
      if (!vivo) return

      const cena = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 5000)
      // `alpha: true` porque o fundo é o token da Malha: a caixa acompanha
      // claro/escuro sem o 3D pintar um cinza próprio por cima do tema.
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
      caixa.appendChild(renderer.domElement)
      renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;touch-action:none'

      // Duas luzes e nenhuma sombra: modelo de obra chega sem material, e o par
      // hemisférica + direcional é o que dá relevo à geometria crua sem custo de
      // shadow map no celular.
      cena.add(new THREE.HemisphereLight(0xffffff, 0x445566, 2.2))
      const sol = new THREE.DirectionalLight(0xffffff, 1.6)
      sol.position.set(1, 2, 1.5)
      cena.add(sol)

      const controles = new OrbitControls(camera, renderer.domElement)
      controles.enableDamping = true

      const ajustar = () => {
        const r = caixa.getBoundingClientRect()
        if (!r.width || !r.height) return
        camera.aspect = r.width / r.height
        camera.updateProjectionMatrix()
        renderer.setSize(r.width, r.height, false)
      }
      const observador = new ResizeObserver(ajustar)
      observador.observe(caixa)
      ajustar()

      new GLTFLoader().load(
        src,
        (gltf) => {
          if (!vivo) return
          cena.add(gltf.scene)

          // Enquadra pelo raio da esfera envolvente: modelo de obra vem em
          // metros e com origem no ponto de amarração do projeto, que costuma
          // estar longe do prédio. Sem recentrar, o "modelo carregou" seria uma
          // tela vazia com o edifício fora do campo de visão.
          const caixaEnv = new THREE.Box3().setFromObject(gltf.scene)
          const centro = caixaEnv.getCenter(new THREE.Vector3())
          const raio = caixaEnv.getSize(new THREE.Vector3()).length() / 2 || 1
          controles.target.copy(centro)
          camera.position.copy(centro).add(new THREE.Vector3(raio * 1.6, raio * 1.1, raio * 1.6))
          camera.near = raio / 100
          camera.far = raio * 100
          camera.updateProjectionMatrix()
          controles.update()
          setCarregando(false)
        },
        undefined,
        () => {
          if (!vivo) return
          setErro('O modelo 3D não pôde ser lido pelo visualizador.')
          setCarregando(false)
        },
      )

      const desenhar = () => {
        quadro = requestAnimationFrame(desenhar)
        controles.update()
        renderer.render(cena, camera)
      }
      desenhar()

      limpar = () => {
        cancelAnimationFrame(quadro)
        observador.disconnect()
        controles.dispose()
        // Modelo BIM tem milhares de malhas: sem soltar geometria e material a
        // GPU segura tudo até a aba morrer, e navegar por três pranchas basta.
        cena.traverse((no) => {
          const malha = no as { geometry?: { dispose(): void }; material?: unknown }
          malha.geometry?.dispose()
          const material = malha.material
          if (Array.isArray(material)) material.forEach((m) => (m as { dispose(): void }).dispose())
          else (material as { dispose?: () => void } | undefined)?.dispose?.()
        })
        renderer.dispose()
        renderer.domElement.remove()
      }
    })().catch(() => {
      if (vivo) {
        setErro('Não foi possível iniciar o visualizador 3D neste dispositivo.')
        setCarregando(false)
      }
    })

    return () => {
      vivo = false
      limpar()
    }
  }, [src])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: 'var(--inset)' }}>
      <div ref={caixaRef} style={{ width: '100%', height: '100%' }} />
      {(carregando || erro) && (
        <div
          style={{
            position: 'absolute', inset: 0, display: 'grid', placeItems: 'center',
            gap: 10, gridAutoFlow: 'row', color: 'var(--ink-3)', fontSize: 13, padding: 24,
            textAlign: 'center',
          }}
        >
          {erro ?? (
            <>
              <Spinner />
              <span>Carregando o modelo 3D…</span>
            </>
          )}
        </div>
      )}
      {!carregando && !erro && (
        <span
          style={{
            position: 'absolute', left: 12, bottom: 12, fontSize: 11, fontWeight: 600,
            color: 'var(--ink-3)', background: 'var(--glass)', border: '1px solid var(--line)',
            borderRadius: 999, padding: '3px 9px',
          }}
        >
          Arraste para girar · duas mãos para aproximar
        </span>
      )}
    </div>
  )
}
