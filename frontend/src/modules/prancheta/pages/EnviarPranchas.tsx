import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { WizardArquivos } from '@/components/malha'
import { FormatosEMotores } from './Formatos'

/**
 * **Pôr projeto novo dentro** — um caminho, uma janela.
 *
 * **O que esta tela era, e por que encolheu (PRA.9d).** Havia dois modos de
 * subir arquivo no acervo, e o dono achou o defeito no uso: o botão amarelo
 * *"Escolher arquivos"* era inútil, *"já que tem enviar pasta e dentro tem
 * escolher pasta e escolher arquivos"*. Estava certo — o wizard do
 * `funcoesimpexp` sempre teve os dois cartões, e o palpite dele lê disciplina
 * **do caminho e do nome**, que era todo o argumento do caminho avulso. O que o
 * avulso fazia a mais era gravar direto, sem conferência; o que ele fazia a
 * menos era peneirar formato e peso **antes** de subir, então um `.docx` de
 * 300 MB subia inteiro para tomar 400 na porta.
 *
 * Não era violação da R17 — os dois caminhos passavam pela porta única
 * ([porta.py](../../../../../backend/moduloprancheta/porta.py)); era duplicação
 * de **interface**, que é como uma das duas telas envelhece sem ninguém notar.
 *
 * **E a segunda janela sumiu junto**, que foi o segundo pedido: antes, "Enviar
 * projetos" abria um modal cuja única função útil era hospedar o botão que abria
 * o modal do wizard. Uma janela para chegar à janela é um clique cobrado por
 * nada. Agora o botão **é** o do wizard, e a regra que a janela intermediária
 * existia para contar — o nome do arquivo virando prancha e revisão — desce pelo
 * slot `ajuda`, dentro da mesma tela em que se escolhe o arquivo.
 *
 * O que sobrou aqui é só o que o wizard genérico não pode saber: a gramática do
 * acervo e o link para a parede comercial dos formatos.
 */
export function EnviarPranchas({ obra, say }: { obra: number; say: (m: string) => void }) {
  const qc = useQueryClient()
  const [vendoFormatos, setVendoFormatos] = useState(false)

  return (
    <span style={{ display: 'inline-flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <WizardArquivos
        recurso="prancheta.acervo"
        contexto={{ obra }}
        rotulo="Enviar projetos"
        tam="md"
        ajuda={<GramaticaDoAcervo aoVerFormatos={() => setVendoFormatos(true)} />}
        onConcluida={(aplicadas: number) => {
          say(
            aplicadas
              ? `${aplicadas} prancha${aplicadas > 1 ? 's' : ''} no acervo, em rascunho — `
                + 'publicar é o ato que muda o campo.'
              : 'Nada foi gravado.',
          )
          qc.invalidateQueries({ queryKey: ['prancheta'] })
        }}
      />

      {vendoFormatos && <FormatosEMotores aoFechar={() => setVendoFormatos(false)} />}
    </span>
  )
}

/**
 * A regra que o wizard genérico não tem como saber: o que o arquivo **vira**.
 *
 * Fica no topo do passo de escolher, antes dos cartões — é a pergunta que a
 * pessoa tem na mão junto com o DWG, e respondê-la depois da escolha seria tarde.
 */
function GramaticaDoAcervo({ aoVerFormatos }: { aoVerFormatos: () => void }) {
  return (
    <div style={{
      display: 'grid', gap: 9, padding: 12, borderRadius: 'var(--r-md)',
      background: 'var(--inset)', border: '1px solid var(--line)',
    }}>
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6 }}>
        O <strong>nome do arquivo</strong> vira a prancha: <code>ARQ-PLB-001_R02.dwg</code> entra
        como a prancha <code>ARQ-PLB-001</code> na revisão <code>R02</code>, já classificada em{' '}
        <strong>Arquitetura</strong>. Mandar o mesmo código de novo vira{' '}
        <strong>revisão nova</strong>, não prancha duplicada.
      </p>
      <button
        onClick={aoVerFormatos}
        style={{
          justifySelf: 'start', background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 12, color: 'var(--ink-3)', textDecoration: 'underline',
        }}
      >
        o que dá para enviar?
      </button>
    </div>
  )
}
