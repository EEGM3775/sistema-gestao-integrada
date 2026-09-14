import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'

/**
 * Quantos dias o plano do cliente dá para desfazer uma exclusão (D116).
 *
 * **Por que isto existe.** Depois da lixeira, "esta ação não pode ser desfeita"
 * virou mentira em toda tela que exclui — e, pior, mentira que esconde o que o
 * cliente pagou: a janela de recuperação é o que a paywall vende
 * (`lixo_retencao_dias`, §5.5g do `planos.py`). Uma tela que diz "não dá para
 * desfazer" quando dá é um recurso comprado e nunca descoberto.
 *
 * **Por que vem do servidor, e não de uma constante no frontend.** O número é
 * por plano: 3 dias no `free`, 15 nos contratados, 30 no Sob Medida. Um `15`
 * escrito aqui mostraria o prazo errado para quem está no `free` — e prometer
 * duas semanas para quem tem três dias é o tipo de promessa que só se descobre
 * falsa no dia em que se precisa dela.
 *
 * Vem da chave `janelas` de `/api/plano/`, e **não** de `quotas`: quantidade tem
 * barra de progresso, tempo tem frase. `lixo_retencao_dias` esteve na lista de
 * quotas por um dia e a home o desenhava como medidor sem uso — "null de 15".
 */
interface JanelaDoPlano {
  recurso: string
  rotulo: string
  dias: number
}

interface RespostaDoPlano {
  janelas?: JanelaDoPlano[]
}

export function useRetencaoDoLixo() {
  const plano = useQuery({
    queryKey: ['plano', 'janelas'],
    queryFn: async () => (await apiClient.get<RespostaDoPlano>('plano/')).data,
    // O plano contratado não muda no meio de uma sessão de trabalho; refazer
    // esta chamada a cada modal de exclusão seria uma ida ao servidor para
    // buscar um número que não mudou.
    staleTime: 10 * 60 * 1000,
    retry: false,
  })

  const dias = plano.data?.janelas?.find(j => j.recurso === 'lixo_retencao_dias')?.dias

  return {
    dias: typeof dias === 'number' ? dias : null,
    /**
     * `null` enquanto carrega ou se a chamada falhar — e aí a tela **não**
     * promete prazo nenhum. Chutar um número aqui seria pior que omitir: o
     * modal diria "15 dias" para quem tem 3, e a pessoa só descobriria no dia
     * em que fosse restaurar.
     */
    carregando: plano.isLoading,
  }
}

/**
 * A mesma frase, para os diálogos nativos (`window.confirm`), que não aceitam
 * JSX. Devolve uma função para poder ser chamada dentro do handler — o hook em
 * si roda no corpo do componente, como manda a regra dos hooks.
 *
 * **Use só onde o modelo tem lixeira.** No CRM, por exemplo, `Lead`, `Account` e
 * `Opportunity` herdam `Excluivel`, mas **`Contact` não** — prometer lixeira lá
 * seria a mentira oposta à que este arquivo veio consertar, e a pior das duas: a
 * pessoa exclui confiando que dá para voltar.
 */
export function useTextoDaLixeira() {
  const { dias } = useRetencaoDoLixo()

  return (oQue: string) => {
    const prazo = dias !== null ? `${dias} ${dias === 1 ? 'dia' : 'dias'}` : 'o prazo do seu plano'
    return `Excluir ${oQue}?\n\nVai para o Lixo e pode ser restaurado por ${prazo}. Depois disso é apagado de vez.`
  }
}
