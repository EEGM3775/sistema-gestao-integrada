import { useState } from 'react'
import { Btn, Modal } from '@/components/malha'
import { useFileUpload } from '@/hooks/useFileUpload'
import { useAbrirNc } from '../hooks'
import { entrada } from '../estilos'
import { Ajuda, Campo, Escolhas, FaixaDeErro, Grupo } from './Formulario'
import { SeletorDeLugar } from './SeletorDeLugar'
import type { GravidadeNc, NaoConformidade } from '../types'
import { primeiraFrase } from '../formato'
import { GRAVIDADES } from '../vocabulario'


/** **Registrar um defeito** fora de uma ficha — o que se viu andando pela obra.
 *
 *  A gravidade é perguntada aqui, por quem viu: é propriedade do defeito, e
 *  quem trata não a decide depois. A foto é opcional no escritório (no campo, a
 *  tela abre pela câmera). */
export function FormularioDeNc({
  obraId, aoFechar, aoCriar,
}: {
  obraId: number
  aoFechar: () => void
  aoCriar: (nc: NaoConformidade) => void
}) {
  const abrir = useAbrirNc()
  const { validate, acceptAttr } = useFileUpload()
  const [descricao, setDescricao] = useState('')
  const [gravidade, setGravidade] = useState<GravidadeNc | null>(null)
  const [local, setLocal] = useState<number | null>(null)
  const [atividade, setAtividade] = useState<number | null>(null)
  const [foto, setFoto] = useState<File | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const completo = descricao.trim() && gravidade

  return (
    <Modal
      titulo="Registrar um defeito"
      onClose={aoFechar}
      largura={620}
      alto
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={!completo || abrir.isPending}
            onClick={async () => {
              if (!gravidade) return
              setErro(null)
              try {
                const nova = await abrir.mutateAsync({
                  corpo: {
                    obra: obraId, descricao: descricao.trim(), gravidade, local, atividade,
                  },
                  foto,
                })
                aoCriar(nova)
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            {abrir.isPending ? 'Gravando…' : 'Registrar defeito'}
          </Btn>
        </div>
      }
    >
      <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <FaixaDeErro>{erro}</FaixaDeErro>

        <Campo rotulo="O que está errado">
          <textarea
            rows={3} value={descricao} autoFocus
            onChange={(e) => setDescricao(e.target.value)}
            style={{ ...entrada, resize: 'vertical' }}
            placeholder="Ex.: parede do banheiro 12 fora de prumo, 2 cm em 2,6 m"
          />
        </Campo>

        <Grupo rotulo="Gravidade">
          <Escolhas
            valor={gravidade}
            aoEscolher={setGravidade}
            opcoes={GRAVIDADES.map((g) => ({ valor: g.valor, rotulo: `${g.rotulo} — ${g.explica}`, tom: g.tom }))}
          />
        </Grupo>

        <SeletorDeLugar
          obraId={obraId}
          local={local}
          atividade={atividade}
          aoMudarLocal={setLocal}
          aoMudarAtividade={setAtividade}
        />

        <Campo rotulo="Foto (opcional)">
          <input
            type="file" accept={acceptAttr.includes('image') ? acceptAttr : 'image/*'}
            onChange={(e) => {
              const arquivo = e.target.files?.[0] ?? null
              const problema = arquivo ? validate(arquivo) : null
              setErro(problema)
              setFoto(problema ? null : arquivo)
            }}
            style={{ fontSize: 12.5 }}
          />
          <Ajuda>A foto viaja com o defeito até quem vai consertar.</Ajuda>
        </Campo>
      </div>
    </Modal>
  )
}
