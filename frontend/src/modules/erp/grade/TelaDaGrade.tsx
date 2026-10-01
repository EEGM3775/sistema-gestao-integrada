import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { AgruparPor, CaixaDeBusca, Situacoes, Totais, type OpcaoSituacao } from './BarraDaGrade'
import { Grade, type SelecaoGrade } from './Grade'
import type { ColunaGrade, NoGrupo } from './tipos'
import type { useGrade } from './useGrade'

/**
 * A moldura das telas de títulos (contas a receber, a pagar, boletos): o mesmo
 * lugar para a busca, os recortes, o agrupamento, os totais e a grade — quem
 * aprende uma, sabe as três.
 */
export function TelaDaGrade<T>({
  titulo, subtitulo, acoes, busca, onBuscar, placeholderBusca, situacoes, situacao, onSituacao,
  filtros, grade, colunas, onAbrir, onAbrirSoOGrupo, selecao, extraTotais, substantivo, mostrarSaldo, vazio, abas,
}: {
  titulo: string
  subtitulo: string
  acoes?: ReactNode
  busca: string
  onBuscar: (termo: string) => void
  placeholderBusca: string
  situacoes?: OpcaoSituacao[]
  situacao?: string
  onSituacao?: (v: string) => void
  filtros?: ReactNode
  grade: ReturnType<typeof useGrade<T>>
  colunas: ColunaGrade<T>[]
  onAbrir: (linha: T) => void
  onAbrirSoOGrupo: (no: NoGrupo) => void
  selecao?: SelecaoGrade<T>
  extraTotais?: ReactNode
  substantivo: [string, string]
  mostrarSaldo: boolean
  vazio: string
  abas?: ReactNode
}) {
  return (
    <div className="px-6 py-6 flex flex-col" style={{ height: 'calc(100vh - 64px)', minHeight: 560 }}>
      <Link to="/app/erp" className="inline-flex items-center gap-1.5 text-xs font-semibold mb-2"
        style={{ color: 'var(--ink-3)', textDecoration: 'none' }}>
        <ArrowLeft size={14} /> ERP Financeiro
      </Link>

      <div className="flex items-end justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>{titulo}</h1>
          <p className="text-xs" style={{ color: 'var(--ink-3)' }}>{subtitulo}</p>
        </div>
        {acoes && <div className="flex items-center gap-2 flex-wrap">{acoes}</div>}
      </div>

      {abas}

      <div className="flex items-center gap-3 flex-wrap mb-3">
        <CaixaDeBusca valor={busca} onBuscar={onBuscar} placeholder={placeholderBusca} buscando={grade.atualizando} />
        {situacoes && onSituacao && <Situacoes opcoes={situacoes} valor={situacao ?? ''} onEscolher={onSituacao} />}
      </div>

      <div className="flex items-center gap-3 flex-wrap mb-3">
        {filtros}
        <AgruparPor dimensoes={grade.dimensoes} niveis={grade.niveis} teto={grade.tetoNiveis} onMudar={grade.setNiveis} />
      </div>

      <div className="mb-2">
        <Totais totais={grade.totais} substantivo={substantivo} mostrarSaldo={mostrarSaldo} extra={extraTotais} />
      </div>

      <Grade
        itens={grade.itens}
        colunas={colunas}
        ordenar={grade.ordenar}
        carregando={grade.carregando}
        mostrarSaldo={mostrarSaldo}
        selecao={selecao}
        vazio={vazio}
        onOrdenar={grade.setOrdenar}
        onAbrir={onAbrir}
        onAlternarGrupo={grade.alternarGrupo}
        onAbrirSoOGrupo={onAbrirSoOGrupo}
        onFimDaLista={grade.fimDaLista}
      />
    </div>
  )
}
