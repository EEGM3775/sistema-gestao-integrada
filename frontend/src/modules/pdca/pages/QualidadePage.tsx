import { PostoEmConstrucao } from '../components/PostoEmConstrucao'

export default function QualidadePage() {
  return (
    <PostoEmConstrucao
      titulo="Qualidade"
      cadencia="contínua, disparada por evento"
      pergunta="O que reprovou, quem está tratando, e acabou mesmo?"
      fara={[
        'Ver o que está parado em cada ponto: o defeito que ninguém pegou, a ação vencida, o conserto que ninguém conferiu e a ficha parada no meio',
        'Montar os modelos de ficha da empresa — o que se confere e com que critério',
        'Acompanhar a não-conformidade do registro ao encerramento, com o plano de ação no mesmo lugar',
        'Encerrar só com a eficácia verificada em campo',
        'Ler o que mais reprova, e em que situação cada reprova está hoje',
      ]}
    />
  )
}
