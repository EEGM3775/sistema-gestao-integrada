# Ponte temporária — acessar o SGI de fora de casa

> **O que é:** um túnel público, com senha na frente, que dura algumas horas e
> morre sozinho. Serve para abrir o SGI no celular quando você não está na
> máquina de desenvolvimento. Não é deploy, não é staging, e não deve durar um
> dia inteiro.
>
> **O comando é um só:** [`infra/ponte/ponte.sh`](../infra/ponte/ponte.sh).

```
celular ──▶ cloudflared (URL pública, TLS) ──▶ nginx porteiro (senha) ──▶ sgi-gateway:80
```

Dois containers avulsos, ao lado do stack. Nada do compose é alterado, nenhuma
`settings` é editada, nenhuma porta de roteador é aberta.

---

## 1. Uso

No WSL (`wsl -d Ubuntu`), com o stack de pé:

```bash
cd ~/projetos/02sistema_gestao_integrada
./infra/ponte/ponte.sh subir          # 4 horas (padrão)
./infra/ponte/ponte.sh subir 2        # ou o prazo que você quiser, até 12h
./infra/ponte/ponte.sh subir stg      # o staging (8443) em vez do dev (8090)
```

No PowerShell, na pasta `infra\ponte`: `wsl ./ponte.sh subir` — sem o `wsl` na frente o Windows
só abre o `.sh` e nada sobe.

No `stg` o porteiro fala TLS com o gateway do staging (o `:80` de lá só redireciona) e repassa a
origem `https://localhost:8443`; a cópia do `nginx.conf` com essas duas trocas é gerada na subida.
O staging tem dado real (tenant EEGM) — a senha da ponte é o que o separa da internet.

Ele imprime a **URL**, o **usuário** (`sgi`), a **senha** — gerada na hora — e a
**hora em que expira**. No celular: abra a URL, o navegador pede usuário e
senha, e depois você cai no login normal do SGI.

| Comando | O que faz |
| --- | --- |
| `subir [horas] [stg]` | Levanta a ponte. Padrão 4h no dev, teto 12h; `stg` aponta para o staging. |
| `status` | O que está no ar, quanto falta, e se o vigia está vivo. |
| `prorrogar [horas]` | Estica o prazo. **A URL e a senha não mudam.** |
| `derrubar` | Fecha agora, sem esperar o prazo. |
| `dominio [nome\|-]` | Mostra, grava ou apaga (`-`) o **link fixo** (abaixo). |

### Link fixo

O `trycloudflare` sorteia uma URL nova a cada `subir`. Para o link ser sempre o mesmo, a ponte usa o
**domínio estático gratuito do ngrok** da conta já configurada nesta máquina
(`~/.config/ngrok/ngrok.yml`, a mesma do webhook do Asaas):

1. Reservar o domínio **uma vez** no painel do ngrok (*Universal Gateway → Domains → New Domain*; a
   conta gratuita tem um). O script não cria domínio — isso exige o login da conta.
2. `./infra/ponte/ponte.sh dominio fulano.ngrok-free.app` — fica gravado em `~/ponte-temporaria/dominio`.
3. Daí em diante, `subir` usa o ngrok nesse domínio. **A senha continua nova a cada subida**: um link
   que não muda é mais fácil de achar, e a senha é o que o protege.

No ngrok gratuito o navegador mostra, na primeira visita, um aviso do próprio ngrok ("You are about to
visit…") com um botão para seguir — é dele, não do SGI. `dominio -` volta ao `trycloudflare`.

### Por que o porteiro reescreve o `Origin`

O porteiro troca o `Host` por `localhost` (para o `ALLOWED_HOSTS` valer sem ser editado). O refresh e
o logout da IAM recusam origem cross-site comparando `Origin` com `Host` — e o celular manda
`Origin: https://<ponte>`. Sem reescrever, todo refresh dava 403 e a sessão caía a cada recarga de
página ([D259](historico-correcoes.md)). Só a origem **da própria ponte** vira `http://localhost`;
qualquer outra segue como veio e continua recusada. Em produção não há porteiro: `Host` e `Origin` são
o mesmo domínio.

---

## 2. A ponte morre de velhice — e por que isso importa

*(Conserto do [D146](pendencias.md), 14/09/2026.)*

A primeira versão desta receita eram quatro comandos colados, e a regra que a
encerrava — *"levantou, usou, DERRUBOU"* — morava na memória de uma pessoa. Em
14/09 o dono perguntou se a ponte estava ativa: **estava, havia sete horas**, sem
ninguém do outro lado.

O conserto não é lembrar melhor. É **esquecer a ponte passar a fechá-la**, em vez
de a manter. São duas travas independentes:

1. **O vigia** — um processo no hospedeiro que dorme até o prazo e faz o
   `docker rm -f` dos dois containers. É ele que limpa de verdade.
2. **O porteiro morre sozinho** — o nginx roda sob `timeout` *dentro* do
   container. Se o vigia morrer, o porteiro ainda expira no mesmo instante e a
   URL passa a responder **502**: o app deixa de ser alcançável mesmo com o
   túnel de pé.

A segunda existe porque a primeira tem um modo de falha conhecido: o vigia é um
processo do WSL do usuário, e o Docker Desktop roda em outra distro. Derrubar o
WSL mata o vigia **sem** matar os containers. Uma trava só seria confiar em quem
pode morrer primeiro.

> **O que nenhuma das duas cobre, e é de propósito:** uma queda do Docker Desktop
> leva tudo junto — stack e ponte — e **a ponte não volta**. Os containers nascem
> sem política de `restart`. O stack volta sozinho; a ponte, não. É o
> comportamento certo.

**`status` é fail-loud.** Se houver container de pé sem prazo registrado, ou com
o prazo vencido, ou com o vigia morto, ele diz isso em vermelho — em vez de
responder "no ar" e deixar você achar que está tudo certo.

---

## 3. O que fica exposto — leia antes da primeira vez

O stack de desenvolvimento **não** é seguro para ficar na internet:

- `DEBUG=True` nos dois Djangos → a página de erro mostra traceback, nomes de
  settings e a SQL que falhou;
- `SECRET_KEY=django-insecure-dev-erp-0531` está **versionada** no compose;
- `dono/dono123` é superusuário e está escrito na documentação do repositório.

**É por isso que o porteiro tem senha própria.** Ela é a segunda camada — o
`/api/` exige o JWT da IAM de qualquer jeito —, mas é a única coisa entre a
página de erro do Django e quem achar a URL. E a URL do `trycloudflare` é
aleatória, o que **não** é o mesmo que secreta: esses domínios são varridos. O
log do D146 registrou o próprio scanner da Cloudflare batendo duas vezes em sete
horas (401 nas duas, como projetado).

Duas coisas já a nosso favor:

- **`/media/` responde 404 no gateway** → arquivo de obra não sai pela ponte;
- **o Drone está barrado de propósito** (decisão de 13/09/2026: consome banda e
  máquina demais para um túnel doméstico). `/drone/`, `/odm-api/` e `/ws/` caem
  em **403 com aviso** — abrir a tela do Drone no celular mostra a mensagem, não
  um erro quebrado.

A senha é **gerada, não escolhida**, e nova a cada `subir`. Senha reaproveitada
de outra coisa é o que transforma uma exposição de quatro horas num problema
permanente.

---

## 4. Quando algo dá errado

| Sintoma | Causa provável | Conserto |
| --- | --- | --- |
| A URL não resolve (`000`) | O túnel caiu ou o prazo venceu | `status`, depois `subir` de novo — a URL será outra |
| A URL responde **502** | O porteiro expirou e o túnel não | `prorrogar`, ou `derrubar` e subir de novo |
| O navegador não pede senha | O `htpasswd` não foi montado | `derrubar` e `subir` — o script recria o arquivo |
| `status` diz **vigia MORTO** | O WSL reiniciou | `prorrogar` re-arma; ou `derrubar` |
| `status` diz **SEM PRAZO REGISTRADO** | A ponte subiu fora do script | `derrubar` — e use o script |
| Quer ver quem bateu na ponte | — | `docker logs sgi-ponte-porta --tail 50` |

O histórico de subidas e descidas fica em `~/ponte-temporaria/prazo.log`.

---

## 5. Liberar RAM enquanto estiver fora (opcional)

O Drone **não** atravessa a ponte, mas os containers dele continuam rodando e
comendo memória. Dá para pausá-los sem afetar o resto do stack:

```bash
docker stop sgi-nodeodm sgi-potree sgi-odm-java sgi-odm-nginx sgi-odm-db
```

E para voltar ao normal quando chegar em casa:

```bash
docker start sgi-odm-db sgi-odm-java sgi-nodeodm sgi-potree sgi-odm-nginx
```

A ordem importa na volta: o banco primeiro, a API Java depois dele.

---

## 6. Onde isto morava antes

Na §14 do `terminal.txt` da raiz do repositório — arquivo que o **A10** já marca
para sair. O D146 registrou o agravante: se ele saísse primeiro, sumiria junto o
comando que **fecha** a ponte. Esta página é a casa definitiva; o script é a
fonte de verdade dos comandos.
