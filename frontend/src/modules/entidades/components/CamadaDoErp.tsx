import { useEffect, type ReactNode } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { Building2, Layers } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import { formatCPFCNPJ } from '@/utils/masks'
import { useContextoEntidades } from '../api'
import { escolherEntidade, ligarCamadaDoErp, useEntidadeAtiva } from '../entidadeAtiva'

ligarCamadaDoErp(apiClient)

/**
 * A barra de camada do ERP (docs/modulos/entidades.md §6): **Consolidado** ou
 * uma entidade. Envolve todas as telas do financeiro — a escolha vale para as
 * listas, o painel e os relatórios ao mesmo tempo.
 *
 * Com uma entidade do grupo só, a barra não aparece e nada muda para quem usa
 * (o modo simples do construtor no próprio CPF).
 */
export default function CamadaDoErp() {
  const contexto = useContextoEntidades()
  const ativa = useEntidadeAtiva()
  const qc = useQueryClient()
  const dados = contexto.data

  useEffect(() => {
    if (!dados) return
    const valida = ativa === null || dados.entidades.some(e => e.entidade === ativa)
    if (dados.modo_simples || !valida) escolherEntidade(null)
  }, [dados, ativa])

  const trocar = (id: number | null) => {
    escolherEntidade(id)
    void qc.invalidateQueries({ queryKey: ['erp'] })
  }

  const mostrar = dados && !dados.modo_simples
  return (
    <>
      {mostrar && (
        <div
          className="flex items-center gap-2 flex-wrap"
          style={{
            padding: '8px 24px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
            fontSize: 12.5, color: 'var(--ink-3)',
          }}
        >
          <span className="inline-flex items-center gap-1.5 font-semibold" style={{ color: 'var(--ink-2)' }}>
            <Layers size={14} /> Financeiro de
          </span>
          <Opcao ativa={ativa === null} onClick={() => trocar(null)} titulo="Todas as entidades que você alcança, sem o intercompany entre elas">
            Consolidado{dados.entidades.length > 1 ? ` (${dados.entidades.length})` : ''}
          </Opcao>
          {dados.entidades.map(e => (
            <Opcao
              key={e.entidade}
              ativa={ativa === e.entidade}
              onClick={() => trocar(e.entidade)}
              titulo={`${e.papel_nome}${e.documento ? ` · ${formatCPFCNPJ(e.documento)}` : ' · sem CPF/CNPJ cadastrado'}`}
            >
              <Building2 size={12} /> {e.nome}
            </Opcao>
          ))}
          <span className="flex-1" />
          <Link to="/app/erp/entidades" style={{ color: 'var(--accent-ink)', fontWeight: 600, textDecoration: 'none' }}>
            DRE por entidade
          </Link>
          <Link to="/app/erp/intercompany" style={{ color: 'var(--accent-ink)', fontWeight: 600, textDecoration: 'none' }}>
            Intercompany
          </Link>
        </div>
      )}
      <Outlet />
    </>
  )
}

function Opcao({ ativa, onClick, titulo, children }: {
  ativa: boolean
  onClick: () => void
  titulo: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={titulo}
      aria-pressed={ativa}
      className="inline-flex items-center gap-1.5"
      style={{
        padding: '4px 10px', borderRadius: 999, fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
        border: `1px solid ${ativa ? 'var(--accent)' : 'var(--line)'}`,
        background: ativa ? 'var(--accent-soft)' : 'var(--surface)',
        color: ativa ? 'var(--accent-ink)' : 'var(--ink-2)',
      }}
    >
      {children}
    </button>
  )
}
