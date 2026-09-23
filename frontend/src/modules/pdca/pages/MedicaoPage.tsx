import { PostoEmConstrucao } from '../components/PostoEmConstrucao'

export default function MedicaoPage() {
  return (
    <PostoEmConstrucao
      titulo="Medição"
      cadencia="mensal, fecha o mês"
      pergunta="Quanto se deve, por que, e quem autoriza?"
      fara={[
        'Ver os contratos da obra com saldo, retenção acumulada e aditivos',
        'Montar a planilha contratual enquanto o contrato permitir editá-la',
        'Apurar a medição do período a partir do avanço apontado, com a memória de cálculo de cada linha',
        'Conferir a prévia antes de submeter',
        'Submeter, atestar e liberar retenção, cada degrau com quem pode',
        'Registrar aditivo e deduções',
      ]}
    />
  )
}
