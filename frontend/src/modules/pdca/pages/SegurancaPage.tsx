import { PostoEmConstrucao } from '../components/PostoEmConstrucao'

export default function SegurancaPage() {
  return (
    <PostoEmConstrucao
      titulo="Segurança"
      cadencia="diária no diálogo, imediata na ocorrência"
      pergunta="O que fazemos para ninguém se machucar, e o que fazemos quando alguém se machuca?"
      fara={[
        'Registrar o diálogo antes do turno com a lista de presença, que fecha no encerramento e escreve no diário da obra',
        'Registrar a ocorrência sem atrito — do quase-acidente ao acidente grave',
        'Classificar a ocorrência separadamente de quem a registrou',
        'Emitir a CAT no prazo, com o protocolo guardado',
        'Guardar o que é dado de saúde separado do resto, visível só para quem pode',
        'Ver quem está com EPI vencido',
      ]}
    />
  )
}
