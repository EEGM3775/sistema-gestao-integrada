/**
 * Favoritos, recentes e "a minha obra" — o que o aparelho lembra.
 *
 * **Por que no aparelho e não no servidor:** o backend do PRA.0/PRA.1 não tem
 * tabela para nada disso, e inventar um número de "mais visto" no cliente para
 * preencher a tela contraria a régua de dados honestos. O que existe de verdade
 * é o histórico **deste aparelho** — e no canteiro isso é quase sempre o que
 * interessa: o tablet fica na obra, com a mesma pessoa, abrindo as mesmas cinco
 * pranchas o dia inteiro.
 *
 * Por isso a tela rotula "neste aparelho" em vez de fingir sincronia entre
 * dispositivos. Quando o servidor ganhar `AcessoDocumento`/`FavoritoDocumento`,
 * estas funções viram o cache local do mesmo dado e a tela não muda.
 *
 * A chave é por **usuário**: um tablet compartilhado no canteiro não pode
 * mostrar os favoritos de quem usou antes.
 */

const PREFIXO = 'prancheta'
const MAX_RECENTES = 24

export interface AberturaRecente {
  documento_id: number
  obra: number
  codigo: string
  titulo: string
  disciplina_rotulo: string
  /** Quantas vezes este aparelho abriu — é o que ordena "mais vistas". */
  vezes: number
  /** ISO. Desempata e alimenta o "há 2 h". */
  visto_em: string
}

const chave = (usuario: string, o: string) => `${PREFIXO}:${usuario}:${o}`

function ler<T>(k: string, padrao: T): T {
  try {
    const cru = localStorage.getItem(k)
    return cru ? (JSON.parse(cru) as T) : padrao
  } catch {
    // Aba anônima, storage cheio ou JSON corrompido por versão anterior: a tela
    // continua funcionando sem memória, que é degradação aceitável aqui.
    return padrao
  }
}

function gravar(k: string, valor: unknown) {
  try {
    localStorage.setItem(k, JSON.stringify(valor))
  } catch {
    /* sem espaço/sem permissão — seguir sem lembrar é melhor que quebrar a tela */
  }
}

// ── Favoritos ──────────────────────────────────────────────────────────────
export const lerFavoritos = (usuario: string): number[] =>
  ler<number[]>(chave(usuario, 'favoritos'), [])

export function alternarFavorito(usuario: string, documentoId: number): number[] {
  const atuais = lerFavoritos(usuario)
  const novos = atuais.includes(documentoId)
    ? atuais.filter((id) => id !== documentoId)
    : [documentoId, ...atuais]
  gravar(chave(usuario, 'favoritos'), novos)
  return novos
}

// ── Recentes / mais vistas ─────────────────────────────────────────────────
export const lerRecentes = (usuario: string): AberturaRecente[] =>
  ler<AberturaRecente[]>(chave(usuario, 'recentes'), [])

/**
 * Registra uma abertura. Mantém **contagem** e **última vez** porque as duas
 * perguntas são diferentes: "a que mais abro" (a planta baixa do pavimento tipo)
 * e "a que acabei de ver" (a prancha que o mestre pediu agora).
 */
export function registrarAbertura(
  usuario: string,
  doc: Omit<AberturaRecente, 'vezes' | 'visto_em'>,
): AberturaRecente[] {
  const atuais = lerRecentes(usuario)
  const anterior = atuais.find((r) => r.documento_id === doc.documento_id)
  const atualizado: AberturaRecente = {
    ...doc,
    vezes: (anterior?.vezes ?? 0) + 1,
    visto_em: new Date().toISOString(),
  }
  const novos = [atualizado, ...atuais.filter((r) => r.documento_id !== doc.documento_id)]
    .slice(0, MAX_RECENTES)
  gravar(chave(usuario, 'recentes'), novos)
  return novos
}

/** Mais abertas primeiro; empate resolve pela mais recente. */
export const porMaisVistas = (recentes: AberturaRecente[]) =>
  [...recentes].sort((a, b) => b.vezes - a.vezes || b.visto_em.localeCompare(a.visto_em))

// ── A obra deste aparelho ──────────────────────────────────────────────────
/**
 * **Não é controle de acesso, e a tela diz isso.** O backend não tem vínculo
 * usuário↔obra (nem `Obra.responsavel`, nem alocação em `rh`), então "a obra em
 * que trabalho" é uma escolha do aparelho, não um fato do servidor: ela evita
 * que o tablet do canteiro mostre projeto de outra obra por engano — e não
 * impede ninguém de nada, porque impedir é trabalho do backend.
 */
export const lerMinhaObra = (usuario: string): number | null =>
  ler<number | null>(chave(usuario, 'minha-obra'), null)

export const gravarMinhaObra = (usuario: string, obra: number | null) =>
  gravar(chave(usuario, 'minha-obra'), obra)

// ── Modo sol ───────────────────────────────────────────────────────────────
/**
 * Fica no aparelho porque é propriedade **do lugar**, não da pessoa: o tablet
 * que vive no canteiro liga o modo sol e nunca mais desliga; o mesmo usuário no
 * escritório, à noite, não quer a tela estourada de contraste.
 */
export const lerModoSol = (usuario: string): boolean =>
  ler<boolean>(chave(usuario, 'modo-sol'), false)

export const gravarModoSol = (usuario: string, ligado: boolean) =>
  gravar(chave(usuario, 'modo-sol'), ligado)

/** "há 2 h", "ontem" — a leitura do canteiro, não um timestamp ISO. */
export function desde(iso: string): string {
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutos < 1) return 'agora'
  if (minutos < 60) return `há ${minutos} min`
  const horas = Math.floor(minutos / 60)
  if (horas < 24) return `há ${horas} h`
  const dias = Math.floor(horas / 24)
  return dias === 1 ? 'ontem' : `há ${dias} dias`
}
