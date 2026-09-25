import { useMemo } from 'react'
import { useGantt, useLocais, usePlanoCorrente } from '../hooks'
import { Campo, Linha } from './Formulario'
import { entrada } from '../estilos'

/** **Onde**: o local da obra e o serviço, os dois opcionais.
 *
 *  O local põe o registro no mapa da obra; a atividade é o que o liga ao
 *  quadro da semana — sem ela, um defeito crítico não tem como parar a frente
 *  e uma ocorrência não tem o que interditar. Por isso a atividade é pedida
 *  aqui, e não descoberta depois.
 *
 *  Só as **folhas** do plano entram na lista: um grupo da EAP não é serviço
 *  que alguém execute, e a restrição sobre ele não trava ninguém. */
export function SeletorDeLugar({
  obraId, local, atividade, aoMudarLocal, aoMudarAtividade, grande,
}: {
  obraId: number
  local: number | null
  atividade: number | null
  aoMudarLocal: (id: number | null) => void
  aoMudarAtividade: (id: number | null) => void
  grande?: boolean
}) {
  const locais = useLocais(obraId)
  const { plano } = usePlanoCorrente(obraId)
  const gantt = useGantt(plano?.cronograma_id)

  const folhas = useMemo(() => {
    const todas = gantt.data?.atividades ?? []
    const comFilho = new Set(todas.map((a) => a.pai).filter((p): p is number => p != null))
    return todas.filter((a) => !comFilho.has(a.atividade_id))
  }, [gantt.data])

  const estilo = grande ? { ...entrada, fontSize: 16, padding: '12px 12px', borderRadius: 10 } : entrada

  return (
    <Linha>
      <Campo rotulo="Local">
        <select
          value={local ?? ''}
          onChange={(e) => aoMudarLocal(e.target.value ? Number(e.target.value) : null)}
          style={estilo}
          disabled={locais.isLoading}
        >
          <option value="">{locais.isLoading ? 'Carregando…' : 'Sem local'}</option>
          {(locais.data ?? []).map((l) => (
            <option key={l.local_id} value={l.local_id}>
              {'  '.repeat(Math.max(0, l.profundidade))}{l.codigo} · {l.nome}
            </option>
          ))}
        </select>
      </Campo>
      <Campo rotulo="Serviço (atividade)" larga>
        <select
          value={atividade ?? ''}
          onChange={(e) => aoMudarAtividade(e.target.value ? Number(e.target.value) : null)}
          style={estilo}
          disabled={gantt.isLoading}
        >
          <option value="">
            {gantt.isLoading ? 'Carregando…' : plano ? 'Sem atividade' : 'A obra ainda não tem plano'}
          </option>
          {folhas.map((a) => (
            <option key={a.atividade_id} value={a.atividade_id}>
              {a.codigo} · {a.nome}
            </option>
          ))}
        </select>
      </Campo>
    </Linha>
  )
}
