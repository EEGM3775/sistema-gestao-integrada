/** Drone & Mapeamento dentro do SGI (Fase 7, E.1).
 *
 *  O drone é outra aplicação (Java + Angular, `funcoesODM/`), servida pelo
 *  gateway na **mesma origem**, em `/drone/`. Por isso o iframe não leva token
 *  nenhum: desde o BFF (fase 5) a sessão é o cookie HttpOnly da IAM, e o gateway
 *  o troca pelo access do drone em cada chamada à API dele (`/odm-api/`). O que
 *  a planta antiga previa — `?token=JWT` na URL — vazaria a credencial em log e
 *  em histórico, e já não existe token no navegador para passar.
 *
 *  O que vai na URL é o **contexto**: a obra (e o empreendimento dela) que o
 *  drone usa para abrir os projetos daquela obra (`project-context.service.ts`).
 *  A obra escolhida aqui fica na URL do SGI, então o link é compartilhável.
 *
 *  **Instalação sem o drone.** O servidor de avaliação não roda o drone; ali,
 *  `/drone/` cai na rota do próprio SGI e o iframe mostraria o SGI dentro dele
 *  mesmo. A página confere antes se quem responde é o drone (o `<app-root>` do
 *  Angular) e, se não é, diz isso em vez de desenhar uma moldura quebrada.
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ExternalLink, Plane } from 'lucide-react'
import { Card, Empty, Loading, SeletorDeObra } from '@/components/malha'

type Estado = 'conferindo' | 'pronto' | 'ausente'

export default function DroneWrapperPage() {
  const [params, setParams] = useSearchParams()
  const obra = Number(params.get('obra')) || null
  const empreendimento = Number(params.get('empreendimento')) || null
  const [estado, setEstado] = useState<Estado>('conferindo')
  const [carregando, setCarregando] = useState(true)

  useEffect(() => {
    let vivo = true
    fetch('/drone/', { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(async r => {
        const html = r.ok ? await r.text() : ''
        if (vivo) setEstado(html.includes('<app-root') ? 'pronto' : 'ausente')
      })
      .catch(() => { if (vivo) setEstado('ausente') })
    return () => { vivo = false }
  }, [])

  const src = useMemo(() => {
    const q = new URLSearchParams()
    if (empreendimento) q.set('empreendimento_id', String(empreendimento))
    if (obra) q.set('obra_id', String(obra))
    const qs = q.toString()
    return `/drone/${qs ? `?${qs}` : ''}`
  }, [obra, empreendimento])

  useEffect(() => { setCarregando(true) }, [src])

  const escolherObra = (id: number | null, item?: { empreendimento?: number | null }) => {
    const proximo = new URLSearchParams(params)
    if (id == null) {
      proximo.delete('obra')
      proximo.delete('empreendimento')
    } else {
      proximo.set('obra', String(id))
      if (item?.empreendimento) proximo.set('empreendimento', String(item.empreendimento))
      else proximo.delete('empreendimento')
    }
    setParams(proximo, { replace: true })
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 22px', borderBottom: '1px solid var(--line)', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <Plane size={18} style={{ color: 'var(--ink-2)' }} />
          <h1 style={{ fontSize: 17, fontWeight: 680, color: 'var(--ink)', margin: 0 }}>Drone & Mapeamento</h1>
        </div>
        <div style={{ width: 300 }}>
          <SeletorDeObra
            valor={obra}
            aoMudar={(id, item) => escolherObra(id, item)}
            permiteLimpar
            placeholder="Todas as obras — escolha para abrir os voos dela"
            aria-label="Obra"
            style={{ width: '100%', fontSize: 13, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)' }}
          />
        </div>
        {estado === 'pronto' && (
          <a href={src} target="_blank" rel="noopener" style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: 'var(--ink-3)' }}>
            Abrir em outra aba <ExternalLink size={13} />
          </a>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {estado === 'conferindo' && <Loading o="o módulo Drone" />}
        {estado === 'ausente' && (
          <div style={{ padding: 22, maxWidth: 720 }}>
            <Empty>
              O módulo Drone não está instalado neste servidor. Os voos já processados aparecem no
              Mapa (Território), e o processamento de imagens roda onde o drone estiver instalado.
            </Empty>
          </div>
        )}
        {estado === 'pronto' && (
          <Card style={{ position: 'absolute', inset: 0, padding: 0, borderRadius: 0, border: 'none' }}>
            {carregando && (
              <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: 'var(--surface)' }}>
                <Loading o="o drone" />
              </div>
            )}
            <iframe
              key={src}
              src={src}
              title="Drone & Mapeamento"
              onLoad={() => setCarregando(false)}
              style={{ width: '100%', height: '100%', border: 0, display: 'block' }}
              allow="fullscreen; geolocation"
            />
          </Card>
        )}
      </div>
    </div>
  )
}
