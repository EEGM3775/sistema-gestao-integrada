# Domínio: NodeODM — FuncoesODM

> Cole junto com CONTEXT.md quando a sessão envolver processamento fotogramétrico, integração NodeODM ou o Dockerfile.

---

## Integração

O FuncoesODM não modifica o NodeODM — apenas consome sua API REST.  
O cliente está em `backend/java-service` → `NodeODMClientService.java`.

**URL interna (docker-compose):** `http://nodeodm:3000`

---

## Imagem Docker (custom)

**Arquivo:** `docker/nodeodm/Dockerfile`

```dockerfile
FROM opendronemap/nodeodm:latest

# Fix: GDAL compilado contra NumPy 1.x, mas venv tinha NumPy 2.3.2 → ImportError _gdal_array
RUN /code/venv/bin/pip install "numpy==1.26.4" --force-reinstall
```

**Por que é necessário:**
- NodeODM latest instala NumPy 2.x no venv
- GDAL do sistema foi compilado contra NumPy 1.x → ABI incompatível
- Downstream error: `ImportError: cannot import name '_gdal_array'` no stage `odm_report`
- Solução permanente: downgrade para NumPy 1.26.4 (última versão 1.x estável)

---

## Fluxo de Processamento

```
Frontend upload → POST /api/v1/projects/{id}/images
                → POST /api/v1/projects/{id}/tasks         (Java cria tarefa)
                     → NodeODMClientService.createTask()   (Java → NodeODM API)
                     → NodeODMClientService.uploadImages() (Java envia imagens)
WebSocket progress ← NodeODMClientService polling          (Java faz poll no NodeODM)
                  ← WebSocketService.sendProgress()        (broadcast STOMP)
                  ← ProgressIndicatorComponent             (Angular recebe)

Resultado: assets em /var/www/data/{nodeodmTaskId}/
           servidos por ChunkController: GET /api/v1/projects/{id}/chunks/{chunkId}/assets/{filename}
```

---

## API NodeODM usada

| Endpoint NodeODM | Método | Uso |
|-----------------|--------|-----|
| `/task/new` | POST | Criar nova tarefa |
| `/task/{uuid}/upload` | POST | Upload de imagens |
| `/task/{uuid}/commit` | POST | Iniciar processamento |
| `/task/{uuid}/info` | GET | Polling de status e progresso |
| `/task/{uuid}/cancel` | POST | Cancelar tarefa |
| `/task/{uuid}/download/all.zip` | GET | Download do pacote de resultados |

---

## Assets gerados pelo NodeODM

Após processamento bem-sucedido, os principais arquivos em `all.zip`:

| Arquivo | Descrição |
|---------|-----------|
| `odm_orthophoto/odm_orthophoto.tif` | Ortofoto GeoTIFF georreferenciada |
| `odm_dem/dsm.tif` | Digital Surface Model |
| `odm_dem/dtm.tif` | Digital Terrain Model |
| `odm_report/report.pdf` | Relatório de qualidade do ODM |
| `odm_georeferencing/odm_georeferenced_model.laz` | Nuvem de pontos |

---

## Opções de Processamento (principais)

| Opção | Padrão | Descrição |
|-------|--------|-----------|
| `quality` | `medium` | `ultra`, `high`, `medium`, `low`, `lowest` |
| `feature-quality` | `normal` | Qualidade da detecção de features |
| `pc-quality` | `medium` | Qualidade da nuvem de pontos |
| `dsm` | `false` | Gerar DSM |
| `dtm` | `false` | Gerar DTM |
| `orthophoto-resolution` | `5` | GSD em cm/pixel |
| `use-gpu` | `false` | Ativar aceleração GPU |
| `fast-orthophoto` | `false` | Ortofoto rápida (qualidade menor) |

**Referência completa:** [reference/OPCOES_NODEODM_COMPLETAS.md](../reference/OPCOES_NODEODM_COMPLETAS.md)

---

## Troubleshooting

**Erro:** `ImportError: cannot import name '_gdal_array'`  
**Causa:** NumPy > 2.x no venv do NodeODM  
**Fix:** Rebuild da imagem com `docker compose build nodeodm`  
**Detalhe:** [troubleshooting/NODEODM_SOLUTION.md](../troubleshooting/NODEODM_SOLUTION.md)

**Erro:** Tarefa fica em `RUNNING` sem progredir  
**Verificar:** `docker logs nodeodm` — pode ser falta de memória ou imagens corrompidas

**Verificação rápida:**
```bash
curl http://localhost:3000/info    # deve retornar JSON com version
curl http://localhost:3000/task/list
```
