# `infra/` — o que sobe o sistema, e nada além disso

> **Por que este arquivo existe.** Em 16/09/2026 o dono perguntou se tudo que está aqui devia mesmo
> estar aqui. A pergunta é boa porque esta pasta já tem a cicatriz: o `ferramentas/README.md` registra
> que a `medicao/` morava em `infra/` *"por vizinhança com o Dockerfile de medição, e a pasta foi
> virando gaveta"*. Ela saiu em 16/08/2026. Sem uma regra escrita, a gaveta se refaz — e foi o que
> começou a acontecer.

## A regra de entrada

Entra em `infra/` o que **sobe ou expõe um serviço** do stack: configuração de container, de proxy,
de banco, de observabilidade, de chave. O teste é o mesmo que a `ferramentas/` usa do outro lado:
*isto levanta um serviço?* Se levanta, é infra. Se roda na máquina de alguém sobre uma pasta de
arquivos e não grava nada no sistema, é **ferramenta** e o endereço é [`ferramentas/`](../ferramentas/README.md).
Se é um passo de publicação, o endereço é [`deploy/`](../deploy/README.md).

O que **nunca** entra: script sem dono, porque "não achei lugar melhor". Foi assim que o
`serve_spa.py` chegou (ver a última linha da tabela).

## O que está aqui, e de quem é

| Peça | O que é | Veredito |
| --- | --- | --- |
| [`gateway/`](gateway/) | `nginx.conf`, `nginx.staging.conf`, `nginx.unified.conf` e o compose do porteiro do stack | ✅ **É infra.** É o serviço pelo qual tudo entra |
| [`postgres/init/`](postgres/) | `01-init-databases.sh`, montado pelo container do Postgres na primeira subida | ✅ **É infra.** Sem ele os bancos não nascem |
| [`keys/`](keys/) | Par JWT + `generate.sh`. Montado em `sgi-erp:/keys`; os `.pem` são *gitignored* | ✅ **É infra.** É credencial de serviço, e o `.gitignore` já separa o gerador do gerado |
| [`staging/`](staging/README.md) | `up.sh`/`down.sh`/`seed.sh`/`validate.sh` + cert autoassinado do ambiente `sgi-stg-*` | ✅ **É infra.** Sobe um ambiente inteiro |
| [`observability/`](observability/README.md) | `prometheus.yml` do `/metrics` que `nucleo/observability.py` publica | ✅ **É infra.** Configuração viva — o código que ela lê está em `backend/nucleo/` e em `iam/identity/` |
| [`ponte/`](ponte/) | `ponte.sh` + `nginx.conf` do túnel temporário com senha ([docs/ponte.md](../docs/ponte.md)) | ✅ **É infra.** Sobe dois containers e expõe o stack à internet |
| [`ngrok-webhook-proxy/`](ngrok-webhook-proxy/) | Proxy de um endpoint só para o webhook do Asaas, com muro de Basic Auth | ✅ **É infra.** Mesma família da `ponte/`: expor o dev para fora com muro na frente. Documentado em [funcoescobrancas.md](../docs/modulos/funcoescobrancas.md) |
| `serve_spa.py` | Servidor HTTP de 25 linhas que devolvia `index.html` para qualquer rota | ❌ **Não é infra, e está morto.** Ver abaixo |

## O caso do `serve_spa.py`

Ele é o lixo que a pergunta do dono procurava, e há **duas** razões independentes:

1. **Está quebrado desde que chegou aqui.** Ele resolve o diretório como
   `os.path.dirname(__file__) / "frontend" / "dist"` — o que funcionava na raiz do repositório e,
   dentro de `infra/`, aponta para `infra/frontend/dist`, que não existe. A mudança foi a limpeza do
   **A10** (19/07/2026), que moveu "o que tinha valor" em vez de apagar. Ninguém percebeu em dois
   meses, o que é a própria prova de que ninguém o usa.
2. **Foi substituído.** A SPA é servida pelo container `react` (nginx) atrás do gateway, e em
   desenvolvimento pelo `npm run dev` do Vite. Nenhum dos dois caminhos passa por aqui.

**Onde ele estaria, se estivesse vivo:** em lugar nenhum — é função de um serviço que já existe.
A ação é apagá-lo, e ela está registrada no **A10** do [pendencias.md](../docs/pendencias.md), que é
onde moram as remoções que dependem da decisão do dono do repositório.
