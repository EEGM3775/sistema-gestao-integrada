import { useEffect } from 'react'
import { Link, Navigate, Outlet, useParams } from 'react-router-dom'
import { ChevronLeft, Command } from 'lucide-react'
import { Loading } from '@/components/malha'
import { ProvedorPdca } from '../ProvedorPdca'
import { usePdca } from '../contexto'
import { useObras } from '../hooks'
import { Inspetor } from './Inspetor'
import { PaletaDeComando } from './PaletaDeComando'
import { Rail } from './Rail'
import { SeletorDeObra } from './SeletorDeObra'

/** A casca do workspace de obra: cabeçalho com o contexto, rail dos seis postos,
 *  o posto e o inspetor. A obra vive na rota — todo link é colável, e abrir
 *  numa aba nova cai onde estava. */
export default function CascaPdca() {
  const { obraId: param } = useParams()
  const obraId = Number(param)
  const { data: obras, isLoading, isError } = useObras()

  if (!Number.isFinite(obraId) || obraId <= 0) {
    return <Navigate to="/app/pdca" replace />
  }
  if (isLoading) return <Loading o="a obra" />
  if (isError) {
    return (
      <div style={{ padding: 28 }}>
        <p style={{ color: 'var(--ink-2)', fontSize: 14 }}>
          Não foi possível carregar as obras. Verifique a conexão e tente de novo.
        </p>
      </div>
    )
  }

  const obra = obras?.find((o) => o.obra_id === obraId)
  if (!obra) {
    return (
      <div style={{ padding: 28, display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'flex-start' }}>
        <p style={{ color: 'var(--ink-2)', fontSize: 14, margin: 0 }}>
          Esta obra não existe ou não é desta empresa.
        </p>
        <Link
          to="/app/pdca"
          style={{ fontSize: 13, color: 'var(--brand)', textDecoration: 'none' }}
        >
          Escolher outra obra
        </Link>
      </div>
    )
  }

  return (
    <ProvedorPdca obraId={obraId} obra={obra}>
      <Moldura nomeDaObra={obra.nome_obra} obraId={obraId} />
    </ProvedorPdca>
  )
}

function Moldura({ nomeDaObra, obraId }: { nomeDaObra: string; obraId: number }) {
  const { abrirPaleta, paletaAberta, fecharPaleta } = usePdca()

  useEffect(() => {
    function atalho(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (paletaAberta) fecharPaleta()
        else abrirPaleta()
      }
    }
    window.addEventListener('keydown', atalho)
    return () => window.removeEventListener('keydown', atalho)
  }, [abrirPaleta, fecharPaleta, paletaAberta])

  return (
    <div
      style={{
        display: 'flex', flexDirection: 'column',
        height: '100%', minHeight: 0, background: 'var(--ground)',
      }}
    >
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 16px', borderBottom: '1px solid var(--line)',
          background: 'var(--surface)', flexShrink: 0,
        }}
      >
        <Link
          to="/app/pdca"
          title="Voltar à carteira de obras"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontSize: 12, color: 'var(--ink-3)', textDecoration: 'none',
            flexShrink: 0,
          }}
        >
          <ChevronLeft size={14} />
          Carteira
        </Link>

        <span style={{ width: 1, height: 20, background: 'var(--line)', flexShrink: 0 }} />

        <SeletorDeObra obraId={obraId} nome={nomeDaObra} />

        <span style={{ flex: 1 }} />

        <button
          type="button"
          onClick={abrirPaleta}
          title="Buscar e executar (Ctrl+K)"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: 'var(--surface-2)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-sm)', padding: '5px 9px', cursor: 'pointer',
            color: 'var(--ink-3)', fontSize: 12,
          }}
        >
          <Command size={12} />
          <span style={{ fontFamily: 'var(--mono)' }}>K</span>
        </button>
      </header>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Rail obraId={obraId} />
        <main style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
          <Outlet />
        </main>
        <Inspetor />
      </div>

      <PaletaDeComando />
    </div>
  )
}
