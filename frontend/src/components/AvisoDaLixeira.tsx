import { Link } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'
import { useRetencaoDoLixo } from '@/hooks/useRetencaoDoLixo'

/**
 * O que um modal de exclusão passou a ter de dizer depois da lixeira (D116).
 *
 * **Achado do dono, 13/09/2026**, olhando o modal de excluir obra:
 *
 * > *"Esta ação não pode ser desfeita. E essa mensagem não considera o usuário
 * > que pagou pelo lixo."*
 *
 * As duas metades da frase dele são dois defeitos diferentes, e o segundo é o
 * pior:
 *
 * 1. **a mensagem mentia.** Desde a lixeira, excluir marca a lápide e o registro
 *    volta inteiro. "Não pode ser desfeita" descreve o sistema de ontem;
 * 2. **a mensagem escondia o que foi vendido.** A janela de recuperação é a
 *    paywall da lixeira (`lixo_retencao_dias`, §5.5g do `planos.py`). Uma tela
 *    que avisa "não dá para desfazer" faz o cliente pagar por um recurso que ele
 *    nunca descobre — e ainda o assusta na hora de usar o produto.
 *
 * **Por que é um componente, e não uma string corrigida em cada modal.** São 16
 * modelos com lixeira, em 7 módulos, cada um com o seu diálogo. Corrigir texto a
 * texto garante que o 17º nasça mentindo de novo, e que os prazos divirjam entre
 * telas. Aqui a frase é uma só, lê o prazo do plano de um lugar só, e a tela
 * seguinte só precisa montar o componente.
 *
 * **O que ele NÃO faz:** não aparece onde a exclusão é mesmo irreversível —
 * cancelar boleto no Asaas, cancelar NFS-e na NFE.io. Aquelas mensagens estão
 * certas e continuam como estão: o que sai da nossa máquina não volta porque a
 * gente tem uma lixeira.
 */
export function AvisoDaLixeira({ oQue = 'O registro' }: { oQue?: string }) {
  const { dias } = useRetencaoDoLixo()

  return (
    <span>
      {oQue} vai para o <strong>Lixo</strong> e pode ser restaurado
      {/* Sem o prazo carregado, a frase promete a lixeira mas não promete
          prazo. Chutar "15 dias" mostraria o número errado para quem está no
          plano free (3 dias) — e a pessoa só descobriria no dia em que
          precisasse restaurar, que é o pior dia possível para descobrir. */}
      {dias !== null ? (
        <>
          {' '}por <strong>{dias} {dias === 1 ? 'dia' : 'dias'}</strong>.
        </>
      ) : (
        <> pelo prazo do seu plano.</>
      )}{' '}
      Depois disso é apagado de vez.{' '}
      <Link
        to="/app/lixo"
        style={{ color: 'var(--color-brand)', textDecoration: 'underline', whiteSpace: 'nowrap' }}
      >
        <RotateCcw size={11} style={{ display: 'inline', marginRight: 3, verticalAlign: -1 }} />
        ver o Lixo
      </Link>
    </span>
  )
}
