# ferramentas/medicao/ — medir o motor livre sobre arquivo real

O número que decide **onde fica a fronteira entre os planos** da [Prancheta](../../docs/modulos/moduloprancheta.md)
não sai de documentação de biblioteca: sai de rodar o motor sobre os DWGs que a construtora tem. Esta
pasta guarda o **como** e o **sobre o quê**, porque as duas coisas já se perderam uma vez.

| Arquivo | O que é |
|---|---|
| [remedir_dwg.sh](remedir_dwg.sh) | O disparo — lotes, um container por lote, com teto duro |
| [corpus-160.txt](corpus-160.txt) | O corpus da remedição de 07/08/2026, em caminhos **relativos**. Desde 12/08/2026 o acervo tem **159** deles: a pasta `…/VCA/Terrenos/Benfica/` saiu, e o comando avisa a diferença em vez de calar |
| [corpus-grandes-10.txt](corpus-grandes-10.txt) | Os **10 DWGs acima de 40 MB** que estão locais — o corpus que julga o `DWG_MB_MOTOR_LIVRE` (os outros 18 do acervo são placeholders do OneDrive) |
| [comparar_decodificador.py](comparar_decodificador.py) | Dois `dwg2dxf` sobre os mesmos arquivos — mede **entidade e envolvente**, não "abriu" |
| [Dockerfile.libredwg-master](Dockerfile.libredwg-master) | Imagem de medição com um binário candidato **ao lado** do de produção |
| [d43-alvos-19.txt](d43-alvos-19.txt) | Os 19 alvos do [D43](../../docs/historico-correcoes.md), nomeados |
| `resultado-*.log` | O relatório consolidado de cada passada |
| [resultado-2026-08-12-custo-por-arquivo-pela-tela.log](resultado-2026-08-12-custo-por-arquivo-pela-tela.log) | A primeira passada medida **no caminho de produção**, e não na bancada: os mesmos 159 arquivos subidos pela tela e convertidos pelo `worker-conversao`. Saída do `custo_do_acervo`, não deste diretório |
| [relatorio_custo_por_caminho.py](relatorio_custo_por_caminho.py) | O custo de cada arquivo **ao lado do caminho dele na pasta** — pareado por SHA-256, porque a `RevisaoDocumento` não guarda o caminho e o acervo tem nomes repetidos entre subpastas. Gera [docs/medicoes/custo-acervo-160.md](../../docs/medicoes/custo-acervo-160.md) |

**O custo já é por arquivo, e `LOTE=1` deixou de ser obrigatório para isso** *(desde 12/08/2026,
[D82](../../docs/historico-correcoes.md))*. O pico do subprocesso vinha do `RUSAGE_CHILDREN`, que é
marca d'água **acumulada de todos os filhos** — e que ainda conta as páginas herdadas do pai no
`fork`, por copy-on-write. Com dois arquivos no mesmo processo, o segundo herdava o pico do primeiro;
pior, um `/bin/true` disparado por um pai de 1,7 GB reportava 1.714 MB. Agora o filho é medido por
dentro, pelo `VmHWM` do `/proc` dele, que o `exec` zera — e o número é do `dwg2dxf`, não do retrato
do pai.

`LOTE=1` continua sendo boa prática para **isolar o resto** (o pico do pai, a fragmentação do
alocador entre arquivos), mas não é mais o que torna o custo atribuível. Quando o subprocesso vive
menos que uma amostra, o comando grava `n/d` e avisa — nunca um zero, que passaria por "não custou
nada".

**Parciais v3 e v4 não somam.** A troca acima mudou a *grandeza* de `pico_filho_mb`, não a precisão
dela; misturar as duas leituras numa faixa só é exatamente o que a versão do parcial existe para
impedir.

**Para o custo do que já está no sistema, o instrumento é outro.** Este diretório mede bancada: roda
o motor sobre uma pasta e não grava nada. O acervo que já subiu e já converteu tem o custo de cada
conversão em `DerivadaProjeto.memoria["custo"]`, e se lê com
`manage.py custo_do_acervo --obra N` ([§4.7 da planta](../../docs/modulos/moduloprancheta.md)).

## Como remedir o MESMO conjunto (e por que isso importa)

Passada que troca o **motor** só diz alguma coisa contra o **mesmo** corpus: com amostra nova, a
diferença entre 84% e 99% pode ser sorte do sorteio. Daí o `CORPUS=`, que desliga o sorteio:

```sh
CORPUS=ferramentas/medicao/corpus-160.txt IMAGEM=sgi-erp:libredwg-master \
  ferramentas/medicao/remedir_dwg.sh ~/acervo ~/medicao-dwg-0908
```

Duas variáveis existem por causa do Docker Desktop no Windows, e ambas têm padrão seguro:
`COMANDO_PY=` (vazio) usa o comando que já está na imagem, porque bind mount de `\\wsl.localhost\…`
falha; `DOCKER_USER=` (vazio) roda como root, porque o UID do Git Bash não existe no container.
Quando o repositório e o daemon estão no mesmo mundo, os dois padrões antigos voltam sozinhos.

**Antes de medir com a imagem, confira que ela é a do repositório** (`md5sum` do
`medir_cobertura_dwg.py` dos dois lados). Medir com comando velho é medir outra coisa.

## Por que o resultado é por arquivo, e não só a taxa

A passada de 07/08 rodou sem `--detalhe` e guardou apenas os agregados. O relatório dizia que 11
arquivos estouraram o orçamento e 21 geraram DXF ilegível, e **nenhum deles ficou com nome** — nem no
log do lote, nem no parcial. Cada achado virou um número que a investigação seguinte teria de
reconquistar remedindo o acervo inteiro; o corpus estava versionado pela lição do
[D41](../../docs/pendencias.md), o resultado não.

Desde 08/08 o parcial é **v2** e grava a linha de cada arquivo (balde, versão do DWG, causa, sinais),
e `--consolidar` imprime a lista **por causa, com o dono junto**. A subida de versão também recusa
somar parciais de antes do [D76](../../docs/historico-correcoes.md), quando o orçamento de memória
media o processo inteiro: duas passadas com tetos diferentes não formam uma taxa.

**Saída nova por passada.** O script pula lote que já tem parcial, então uma remedição nova pede
pasta de saída própria (`~/medicao-dwg-DDMM`) — reaproveitar a anterior faz o script pular tudo e a
consolidação recusar a mistura.

## Por que o corpus está versionado

A remedição de 02/08/2026 sorteou 1-em-7 com um script de rascunho e **a lista se perdeu junto do
scratchpad**. Sem ela, a medição seguinte não é o mesmo conjunto, e a diferença entre duas passadas
não pode ser atribuída ao conserto — pode ser sorte da amostra. É a mesma lição do
[D41](../../docs/pendencias.md): o que prova um número não pode viver fora do repositório.

Os DWGs em si **não** entram aqui (são 356 MB de arquivo de cliente). O que entra é a lista, que
torna a amostra reproduzível sobre o acervo montado onde quer que ele esteja.

## Por que em lotes

Memória alocada por extensão C — o `ezdxf` desenhando, o LibreDWG lendo — não volta ao sistema
operacional quando o Python libera o objeto. Volta quando **o processo morre**. Uma passada única
sobre o acervo inteiro segura tudo até o fim, e foi assim que a medição de 06/08 chegou a **62 GB numa
estação de 64** ([D57](../../docs/pendencias.md)). Cada lote aqui é um `docker run --rm` próprio: teto
duro de container, memória devolvida ao fim de cada lote, e interrupção possível entre um e outro.

```bash
bash ferramentas/medicao/remedir_dwg.sh /caminho/do/acervo ~/medicao-dwg 10 7
```

Relançar o comando **pula** os lotes que já têm parcial e continua de onde parou. A soma final
(`--consolidar`) recusa lotes de corpus ou de motor diferentes e denuncia buraco e sobreposição na
cobertura — uma taxa que parece do corpus inteiro e não é seria pior que nenhuma.
