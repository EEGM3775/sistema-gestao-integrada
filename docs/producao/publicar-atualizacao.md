# Publicar atualização e módulo novo

> Fluxo de rotina para levar o que foi desenvolvido ao servidor. Pressupõe o ambiente descrito em
> [README.md](README.md). Rode os comandos de SSH pela **WSL** (a chave está lá).

## 0. Antes (se houver migration)

Toda migration nova roda sozinha quando o `erp` sobe. Ela não desfaz sozinha, então faça um backup
antes de publicar qualquer coisa que mude o banco (ver [dados-e-restauracao.md](dados-e-restauracao.md)).

## 1. Fechar o que vai sair

O servidor recebe o **commit**, não a pasta de trabalho, e só de um branch: **`0x70726f64`** ("prod" em
hexadecimal; o `0x` impede que o git o confunda com um commit). O desenvolvimento entra na `main` por
PR; quando a `main` estiver verde e for a hora de publicar, ela avança o branch do servidor:

```bash
git checkout 0x70726f64 && git pull && git merge --ff-only origin/main && git push
```

Nada se desenvolve direto no `0x70726f64` — ele só anda para onde a `main` já está.

## 2. Enviar o código (só o que roda lá)

Da raiz do repositório, na WSL, **com o `0x70726f64` em checkout**:

```bash
git archive 0x70726f64 backend iam frontend payment funcoesemail funcoesautorizacao funcoesODM infra \
  deploy/compose/base.yml deploy/compose/vps.yml deploy/env/vps.env.example THIRD-PARTY-LICENSES.md \
  | ssh -i ~/.ssh/gmaxis root@75.119.143.64 'tar -x -C /opt/sgi'
```

**Publicar o que ainda não tem commit** (a pasta de trabalho): nunca `tar` direto das pastas — ele leva o
que o git ignora, inclusive `infra/keys/*.pem` (as chaves de dev **sobrescrevem as do servidor** e toda a
API cai em 401) e os `.env` de dev (entram na imagem do ERP). Mande só o que o git enxerga:

```bash
git ls-files -co --exclude-standard -- backend iam frontend payment funcoesemail funcoesautorizacao \
  funcoesODM infra deploy/compose/base.yml deploy/compose/vps.yml deploy/env/vps.env.example \
  THIRD-PARTY-LICENSES.md | while read f; do [ -f "$f" ] && echo "$f"; done > /tmp/envio.txt
grep -E '\.pem$|(^|/)\.env$' /tmp/envio.txt && echo 'PARE: segredo na lista'
tar -cz -T /tmp/envio.txt | ssh -i ~/.ssh/gmaxis root@75.119.143.64 'tar -x -C /opt/sgi'
```

Isso **não** leva testes, ambiente dev, docs, ferramentas nem `vps.env` (ver
[README.md](README.md#o-que-não-sobe-para-o-servidor-decisão-do-dono-12102026)). O `tar` só acrescenta
e sobrescreve; arquivo removido no repositório continua no servidor, sem efeito.

## 3. Subir

```bash
ssh -i ~/.ssh/gmaxis root@75.119.143.64 'cd /opt/sgi && bash infra/vps/up.sh'
```

`up.sh` faz o build das imagens que mudaram e recria só os containers afetados. Para um serviço só:
`bash infra/vps/up.sh erp react`. O build usa `COMPOSE_PARALLEL_LIMIT=2` para não estourar a memória.

> **Se o `up.sh` terminar com "dependency failed to start: container sgi-vps-erp is unhealthy"**:
> é o ERP aplicando migrations (o healthcheck dele só espera ~100 s). O container **não caiu**.
> Espere ficar `healthy` (`docker ps`) e rode `bash infra/vps/up.sh` de novo — é seguro repetir.
> Num banco já migrado isso não acontece.

## 4. Conferir

```bash
docker ps --format '{{.Names}}  {{.Status}}' | sort      # tudo Up/healthy; cloudflared Up
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0' https://www.gmaxis.com/   # 200
```

Teste de API por script: mande um `User-Agent` de navegador — o Cloudflare barra o do Python/curl
padrão com erro 1010.

## Módulo novo

1. O backend e o frontend do módulo seguem o fluxo acima; as migrations rodam no `erp`.
2. **Variáveis novas** (chaves, URLs) entram em `deploy/env/vps.env` **no servidor** — o arquivo não vai
   no git. Se o módulo exige ALLOWED_HOSTS/CORS novos, são as mesmas variáveis do `www.gmaxis.com`.
3. **Permissões e módulo no IAM:** o catálogo de permissões novas só vale depois do `sync_authz`, e o
   módulo precisa existir e estar assinado pela empresa:

   ```bash
   cd /opt/sgi
   docker compose --env-file deploy/env/vps.env -f deploy/compose/base.yml -f deploy/compose/vps.yml \
     --profile full exec iam python manage.py sync_authz --all-tenants
   ```

   O registro do módulo (`Modulo`) e a assinatura da empresa (`AssinaturaTenant`) seguem o que
   `infra/vps/criar_admin.py` faz para os módulos existentes; um módulo novo entra na lista `MODULOS`
   de lá ou é assinado pelo mesmo caminho no shell do IAM.
4. Módulo que **escreve em outro módulo** precisa da notificação cruzada (regra do `CLAUDE.md`) — isso
   é código, vai no passo 2.
5. Se o módulo trouxer **carga de dados** grande (base de orçamento, importações), lembre do teto de
   100 MB do Cloudflare: faça a carga dentro do servidor.

## Voltar atrás

- **Só código** (sem migration): `git archive <commit bom> …` no passo 2 e repita o 3.
- **Com migration:** o código antigo pode não funcionar com o banco novo. Restaure o backup do passo 0
  (ver [dados-e-restauracao.md](dados-e-restauracao.md)) e depois o código antigo.
