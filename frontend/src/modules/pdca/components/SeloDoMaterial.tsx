import { Package } from 'lucide-react'
import { Pill } from '@/components/malha'
import { usePdca } from '../contexto'
import { useNecessidadeDeMaterial, usePlanoCorrente } from '../hooks'

/** O material do compromisso está no estoque da obra? — o make-ready do
 *  material, conferido **antes** de a equipe assumir a semana. Lê a fila de
 *  suprimentos do plano vigente (uma consulta, em cache para o quadro inteiro):
 *
 *  - tudo coberto pelo estoque → *material no estoque*;
 *  - coberto, mas por pedido ou demanda ainda não entregues → *a caminho*;
 *  - falta comprar → *falta material*.
 *
 *  Não bloqueia comprometer — a trava é a restrição; isto é o aviso de que
 *  talvez falte registrar uma. Atividade sem material calculado não mostra nada. */
export function SeloDoMaterial({ atividade }: { atividade: number }) {
  const { obraId } = usePdca()
  const { plano } = usePlanoCorrente(obraId)
  const { data } = useNecessidadeDeMaterial(plano?.cronograma_id)
  const linhas = (data?.linhas ?? []).filter((l) => l.atividade === atividade)
  if (linhas.length === 0) return null
  const faltam = linhas.filter((l) => Number(l.a_comprar) > 0)
  const aCaminho = linhas.filter((l) => Number(l.a_comprar) <= 0 && Number(l.coberto_estoque) < Number(l.restante))
  const lista = (ls: typeof linhas) => ls.map((l) => `${l.descricao}: ${Number(l.a_comprar || l.restante).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} ${l.unidade}`).join('\n')
  if (faltam.length) {
    return (
      <Pill kind="danger" title={`Falta comprar:\n${lista(faltam)}`}>
        <Package size={10} /> falta material ({faltam.length})
      </Pill>
    )
  }
  if (aCaminho.length) {
    return (
      <Pill kind="accent" title={`Pedido ou em demanda, ainda não entregue:\n${aCaminho.map((l) => l.descricao).join('\n')}`}>
        <Package size={10} /> material a caminho
      </Pill>
    )
  }
  return (
    <Pill kind="good" title="Todo o material desta atividade está no estoque da obra">
      <Package size={10} /> material no estoque
    </Pill>
  )
}
