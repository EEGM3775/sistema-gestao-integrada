# Início Rápido - FuncoesODM

## Fluxo recomendado

1. Leia [docs/README.md](README.md) para localizar a documentação principal.
2. Se quiser abrir a aplicação, use os scripts da raiz do projeto.
3. Se quiser entender a stack, leia [OVERVIEW.md](guides/OVERVIEW.md).

## Scripts principais

- `menu.bat` / `menu.sh` - menu interativo com todas as opções
- `start.bat` / `start.ps1` / `start.sh` - iniciar a aplicação
- `stop.bat` / `stop.ps1` / `stop.sh` - parar a aplicação
- `status.ps1` / `status.sh` - verificar status
- `criar-atalhos.vbs` - criar atalhos na área de trabalho no Windows

## Início rápido

### Windows

1. Execute `criar-atalhos.vbs` para gerar atalhos na área de trabalho.
2. Abra o atalho de início da FuncoesODM.
3. Aguarde o navegador abrir automaticamente.

### Linux/WSL

1. Execute `./start.sh`.
2. Aguarde o ambiente subir.
3. Abra http://localhost:8088.

## URLs de acesso

- Frontend: http://localhost:8088
- Backend: http://localhost:8080
- NodeODM: http://localhost:3000

## Credenciais de teste

- Usuário: admin
- Senha: admin123

## Ver logs

```bash
docker-compose logs -f
docker-compose logs -f java-service
docker-compose logs -f nginx
docker-compose logs -f nodeodm
```

## Comandos úteis

```bash
docker-compose restart
docker-compose ps
docker-compose exec java-service bash
docker-compose exec db psql -U funcoesodm
```

## Referência

- [SCRIPTS.md](guides/SCRIPTS.md) - documentação detalhada dos scripts
- [BEST_PRACTICES.md](architecture/BEST_PRACTICES.md) - padrões e convenções
