# Armadilhas — o que já deu errado e como evitar

> Cada item custou tempo na subida de 12/10/2026. Estão em ordem de quanto costumam morder.

| Sintoma | Causa | Como evitar |
|---|---|---|
| Teste de API devolve **403 `error code: 1010`** | o Cloudflare barra o `User-Agent` padrão do Python/curl | mande `User-Agent` de navegador em qualquer teste por script |
| Login funciona mas **nenhum dado aparece**; a API devolve **403** em todo módulo; `iam-pdp` repete `volta falhou (400: object definition … not found)` | `spicedb_db` restaurado de outro cluster: o SpiceDB marca as linhas com o número de transação do Postgres de origem, que fica "no futuro" no servidor, e o schema novo gravado depois não aparece | não restaurar o `spicedb_db`; recriá-lo vazio e deixar o `iam-pdp` refazer ([dados-e-restauracao.md](dados-e-restauracao.md) §4) |
| **Calendário sem feriado** estadual e municipal num servidor novo | a sincronização é semanal e a primeira volta do beat só vem 7 dias depois (o boot passou a disparar — D286) | `docker exec sgi-vps-erp python manage.py sincronizar_feriados` |
| **Mapa vazio** ("Nenhum local com coordenada") com obras cadastradas | dado restaurado não traz o `Local` de cada cadastro | `docker exec sgi-vps-erp python manage.py georreferenciar_cadastros --tenant <uuid>` (`--dry-run` antes) |
| `docker compose run` num script lido por `ssh … bash -s` **engole o resto do script** | o `run` liga a entrada padrão, como o `docker exec -i` | `docker compose run … </dev/null` |
| `up.sh` termina com **`erp is unhealthy`** num banco recém-restaurado | o ERP aplica migrations e o healthcheck só espera ~100 s | o container não caiu: espere `healthy` e rode o `up.sh` de novo |
| Senha do SSH **continuava ligada** após o `bootstrap.sh` | o `50-cloud-init.conf` do Ubuntu liga a senha, e o `sshd` vale a **primeira** diretiva; um `99-…conf` é ignorado | o arquivo é `00-sgi.conf` (já corrigido no `bootstrap.sh`); confirme com `sshd -T \| grep passwordauthentication` |
| Restauração do banco **para no meio** sem erro visível | com `set -euo pipefail`, `grep` sem resultado (variável ausente no `vps.env`) aborta o script | leia variáveis opcionais com `{ grep … \|\| true; }` |
| Script remoto **para de ler o resto de si mesmo** | `docker exec -i` dentro de um script lido por `ssh … bash -s` consome a entrada | use `docker exec` sem `-i` quando não passa dado por stdin |
| Dados restaurados mas **segundo fator e segredos ilegíveis** | chaves do servidor diferem das do staging | copie `IAM_SEGUNDO_FATOR_CHAVE`, `SECRET_KEY`, `IAM_SECRET_KEY` antes de subir ([dados-e-restauracao.md](dados-e-restauracao.md)) |
| **Contas da demo ativas** no site público após restaurar | o banco do staging tem `demo123`, `dono123` (supervisor) etc. | desativar antes de religar o túnel |
| Tabelas restauradas mas **app sem permissão** | restauro com `--no-owner` deixa tudo do `postgres` | restaurar como superusuário **sem** `--no-owner`, banco criado com `OWNER` correto e `template0` |
| `www.gmaxis.com` **não resolve** na sua máquina logo depois de criar | o resolvedor da rede guardou a resposta negativa antiga | confirme por `nslookup www.gmaxis.com 8.8.8.8` ou de dentro do servidor; passa em minutos |
| Login não "pega" em outro endereço | o cookie `__Host-sgi_sessao` vale para **um** host | um só endereço canônico (`www`); os outros só redirecionam |
| `app.gmaxis.com` responde **400** | o servidor aceita só o host configurado em `ALLOWED_HOSTS` | redirecionar no Cloudflare, não aceitar vários hosts |
| Build das imagens **parece travado** | a primeira compilação do LibreDWG leva ~15 min num VPS de 6 vCPU | normal na primeira vez; as seguintes usam cache |
| Upload grande **volta 413** | Cloudflare grátis limita o corpo a 100 MB | carga grande dentro do servidor |
| Aspas quebram o comando no PowerShell | comando SSH aninhado com `$`, `'` e `"` | mande o script por arquivo: `ssh … bash -s < arquivo.sh` |
| `ssh` no Git Bash não acha a chave | o Git Bash reescreve `/home/eegm/...` para `C:/Program Files/Git/...` | chame pela WSL: `wsl -e ssh -i /home/eegm/.ssh/gmaxis …` |

## Segurança que não pode regredir

- Nada escuta em `0.0.0.0` no servidor. Não adicione `ports:` sem prefixo `127.0.0.1:` — o Docker fura o `ufw`.
- Nenhuma conta com senha conhecida no ar. Seed de demo **não** roda no servidor.
- `deploy/env/vps.env` fica só no servidor, com permissão 600. Segredo colado em conversa deve ser girado.
