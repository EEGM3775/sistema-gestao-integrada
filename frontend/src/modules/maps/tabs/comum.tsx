import { useEffect, useState, type ReactNode } from 'react'
import { Info, TriangleAlert } from 'lucide-react'
import { Card } from '@/components/malha'
import { COR_TIPO } from '@/components/malha/mapaCores'
import type { StatusMaps } from '../types'
import { ROTULO_TIPO } from './util'

/** Peças que as abas do Maps compartilham — layout, campos, legenda, avisos. */

function useEstreito(limite = 920) {
  const consulta = `(max-width: ${limite}px)`
  const [estreito, setEstreito] = useState(() => typeof window !== 'undefined' && window.matchMedia(consulta).matches)
  useEffect(() => {
    const mq = window.matchMedia(consulta)
    const ouvir = () => setEstreito(mq.matches)
    mq.addEventListener('change', ouvir)
    return () => mq.removeEventListener('change', ouvir)
  }, [consulta])
  return estreito
}

/**
 * **Mapa e lista lado a lado, com a mesma altura** — e quem rola é a lista.
 *
 * Era o defeito da antiga aba Locais (item 67): uma tabela sem mapa, e um mapa
 * sem tabela. Empilhar os dois não resolvia — com muitos locais, a lista
 * empurrava o mapa para longe da tela. Aqui o painel tem a altura do mapa e
 * rola por dentro; em tela estreita ele desce para baixo do mapa com altura
 * limitada, e o mapa continua à vista.
 */
export function MapaComPainel({ mapa, painel, altura = 600, rodape }: {
  mapa: ReactNode; painel: ReactNode; altura?: number; rodape?: ReactNode
}) {
  const estreito = useEstreito()
  return (
    <Card style={{ padding: 12 }}>
      <div style={{
        display: 'grid', gap: 12,
        gridTemplateColumns: estreito ? '1fr' : 'minmax(0, 1fr) 360px',
      }}>
        <div style={{ position: 'relative', minWidth: 0 }}>{mapa}</div>
        <div style={{
          display: 'flex', flexDirection: 'column', minHeight: 0,
          height: estreito ? 'auto' : altura, maxHeight: estreito ? 460 : altura,
          border: '1px solid var(--line)', borderRadius: 'var(--r-md)', background: 'var(--surface)',
        }}>
          {painel}
        </div>
      </div>
      {rodape && <div style={{ marginTop: 12 }}>{rodape}</div>}
    </Card>
  )
}

/** Faixa por cima do mapa — o "você está editando" que não pode passar batido. */
export function FaixaDoMapa({ children }: { children: ReactNode }) {
  return (
    <div style={{
      position: 'absolute', top: 10, left: 10, right: 54, zIndex: 2,
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      padding: '8px 12px', borderRadius: 9, fontSize: 12.5,
      background: 'var(--surface)', border: '1px solid var(--accent)', boxShadow: 'var(--shadow-sm)', color: 'var(--ink)',
    }}>
      {children}
    </div>
  )
}

/**
 * **Legenda das cores** (item 64). A cor é do TIPO de local e sai da mesma
 * tabela que pinta o pin (`COR_TIPO`); o halo é a PRECISÃO. Cada tipo é um
 * botão: clicar filtra o mapa e a lista por ele — legenda que só explica,
 * quando podia também recortar, é metade do serviço.
 */
export function LegendaDoMapa({ porTipo, tipoAtivo, aoEscolherTipo, extra }: {
  porTipo: Record<string, number>
  tipoAtivo: string
  aoEscolherTipo: (tipo: string) => void
  extra?: ReactNode
}) {
  const escala: Array<[string, string, number]> = [
    ['exata', 'Porta (pin/EXIF)', 8],
    ['endereco', 'Endereço', 14],
    ['cep', 'CEP', 20],
    ['municipio', 'Centro da cidade', 26],
  ]
  const rotulo: React.CSSProperties = {
    fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', fontSize: 10.5, color: 'var(--ink-3)', minWidth: 64,
  }
  return (
    <div style={{ display: 'grid', gap: 9 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
        <span style={rotulo}>Cor = tipo</span>
        {Object.entries(COR_TIPO).map(([tipo, cor]) => {
          const on = tipoAtivo === tipo
          return (
            <button key={tipo} type="button" onClick={() => aoEscolherTipo(on ? '' : tipo)}
              title={on ? 'Mostrar todos os tipos' : `Mostrar só ${ROTULO_TIPO[tipo]?.toLowerCase()}`}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 9px', borderRadius: 999,
                fontSize: 12, cursor: 'pointer', color: 'var(--ink-2)',
                border: `1px solid ${on ? cor : 'var(--line)'}`, background: on ? 'var(--surface-2)' : 'transparent',
              }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: cor, border: '2px solid var(--surface)', boxShadow: `0 0 0 1px ${cor}`, flex: 'none' }} />
              {ROTULO_TIPO[tipo]}
              <span style={{ color: 'var(--ink-3)', fontVariantNumeric: 'tabular-nums' }}>{porTipo[tipo] ?? 0}</span>
            </button>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 14, fontSize: 12, color: 'var(--ink-3)' }}>
        <span style={rotulo}>Halo = precisão</span>
        {escala.map(([chave, texto, tamanho]) => (
          <span key={chave} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: tamanho, height: tamanho, borderRadius: '50%', display: 'grid', placeItems: 'center', background: chave === 'exata' ? 'transparent' : 'color-mix(in srgb, var(--ink-3) 18%, transparent)', border: chave === 'exata' ? 'none' : '1px solid color-mix(in srgb, var(--ink-3) 45%, transparent)', flex: 'none' }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--ink-2)' }} />
            </span>
            {texto}
          </span>
        ))}
        <span>— quanto maior a mancha, mais longe o pin pode estar do lugar real.</span>
      </div>
      {extra}
    </div>
  )
}

const VAR_DO_PROVEDOR = {
  geocodificacao_endereco: {
    nome: 'Geocodificador de endereço',
    falta: 'Sem ele, o pin de um endereço novo cai no centro da cidade (precisão de município) até alguém posicioná-lo à mão.',
    como: <>Defina <code>NOMINATIM_URL</code> no <code>.env</code> do servidor — Nominatim self-host, ou um provedor compatível com chave (LocationIQ: <code>NOMINATIM_URL=https://us1.locationiq.com/v1</code> + <code>NOMINATIM_API_KEY</code>).</>,
  },
  motor_rota: {
    nome: 'Motor de rota (OSRM)',
    falta: 'Sem ele, a rota é a reta entre as paradas e o tempo sai de uma velocidade média.',
    como: <>Defina <code>OSRM_URL</code> no <code>.env</code> do servidor (OSRM self-host; em desenvolvimento, <code>https://router.project-osrm.org</code>).</>,
  },
} as const

/**
 * **O que esta instalação consegue fazer, dito na tela** (itens 62 e 70).
 *
 * "Maps está sem API KEY" era isto: os provedores são opcionais e, ausentes, o
 * mapa degrada em silêncio. Faltando, o aviso diz o que se perde e QUAL
 * variável liga; ligados no servidor público do OpenStreetMap, avisa que é de
 * teste — funciona, mas com cota baixa e sem garantia.
 */
export function AvisoDeProvedores({ status, quais }: {
  status: StatusMaps | undefined
  quais: Array<keyof typeof VAR_DO_PROVEDOR>
}) {
  if (!status) return null
  const faltando = quais.filter((q) => status.provedores?.[q] === false)
  const publicos = quais.filter((q) => status.provedores_publicos?.includes(q))
  if (!faltando.length && !publicos.length) return null
  return (
    <div style={{ display: 'grid', gap: 8, marginBottom: 14 }}>
      {faltando.map((q) => (
        <div key={q} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 12px', borderRadius: 9, background: 'var(--accent-soft)', border: '1px solid var(--accent-soft)' }}>
          <TriangleAlert size={16} style={{ color: 'var(--accent-ink)', flex: 'none', marginTop: 1 }} />
          <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
            <b style={{ color: 'var(--ink)' }}>{VAR_DO_PROVEDOR[q].nome} não configurado.</b>{' '}
            {VAR_DO_PROVEDOR[q].falta} {VAR_DO_PROVEDOR[q].como}
          </div>
        </div>
      ))}
      {publicos.map((q) => (
        <div key={q} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '9px 12px', borderRadius: 9, background: 'var(--surface-2)', border: '1px solid var(--line)' }}>
          <Info size={15} style={{ color: 'var(--ink-3)', flex: 'none', marginTop: 1 }} />
          <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
            {VAR_DO_PROVEDOR[q].nome}: servidor <b>público</b> do OpenStreetMap — bom para testar, com limite de uso e sem garantia.
            Em produção, use self-host ou um provedor com chave.
          </div>
        </div>
      ))}
    </div>
  )
}
