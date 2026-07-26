# funcoesimpexp — importação e exportação de plataforma

Motor único de entrada e saída de dados. **Este app não conhece modelo nenhum**:
cada módulo declara os recursos que sabe exportar e importar, e o motor cuida do
resto (ler, conferir, gravar, gerar arquivo, auditar, contar quota).

Planta e a régua que toda declaração precisa obedecer:
[docs/modulos/funcoesimpexp.md](../../docs/modulos/funcoesimpexp.md).

Regra que resume o resto: **acesso total ou nada**. Se qualquer coluna declarada
sairia mascarada ou inacessível para quem pediu, a operação é recusada com a
permissão nomeada — nunca se entrega arquivo parcial (§3 da planta).
