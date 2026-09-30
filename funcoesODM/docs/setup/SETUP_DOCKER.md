# Setup Docker - FuncoesODM

## Problema Detectado

O Docker Desktop nao estava em execucao quando o setup foi testado. O erro observado foi:

```text
error during connect: Head "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/_ping"
```

---

## Solucao

### 1. Iniciar Docker Desktop
1. Abra o Docker Desktop no Windows
2. Aguarde o status ficar pronto
3. Confirme que a integracao com WSL esta habilitada para Ubuntu

### 2. Validar o ambiente
Execute estes comandos no PowerShell:

```powershell
cd "\\wsl.localhost\Ubuntu\home\eegm\projetos\Metashape\funcoesODM"
docker ps
docker-compose config --quiet
```

### 3. Build e inicializacao

```powershell
docker-compose build
docker-compose up -d
docker-compose ps
```

---

## URLs

- Frontend: http://localhost:8088
- API: http://localhost:8080
- NodeODM: http://localhost:3000
- PostgreSQL: localhost:5433

---

## Credenciais de teste

- Admin: admin / admin123
- Teste: testuser / test123

---

## Troubleshooting rapido

- Se o Docker nao responder, reinicie o Docker Desktop
- Se a porta 8088 estiver ocupada, ajuste o mapeamento em docker-compose.yml
- Se um container falhar, consulte os logs com docker-compose logs -f

---

## Status

Documento movido para dentro da estrutura oficial de docs do projeto.
