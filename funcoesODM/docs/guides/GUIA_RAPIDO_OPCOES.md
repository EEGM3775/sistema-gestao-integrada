# 🎯 Guia Rápido: Novas Opções do FuncoesODM

## 📦 Como Acessar

1. Abra um projeto
2. Clique em **"Nova Tarefa de Processamento"**
3. Expanda **"Opções Avançadas"** (botão ▶)
4. Navegue pelas 14 seções disponíveis

---

## 🎨 Seções Disponíveis

### 🔹 **Sempre Visíveis**

#### 1️⃣ Nome da Tarefa
```
Ex: Ortomosaico Área 1
```

#### 2️⃣ Preset de Configuração
- ⚡ Rápido (Preview)
- ⚖️ Padrão (Balanceado)
- 🎯 Alta Qualidade
- 🎲 Modelo 3D Detalhado
- 🌾 Agricultura (NDVI)
- 📐 Topografia (Alta Precisão)
- ⚙️ Personalizado

#### 3️⃣ Produtos a Gerar
- 📷 Ortofoto
- 🗻 DSM
- 📊 DTM
- ☁️ Nuvem de Pontos
- 🎲 Modelo 3D
- 📄 Relatório PDF ⚠️

---

### 🔹 **Opções Avançadas** (Clique para expandir)

#### 4️⃣ ⚡ Processamento Paralelo
**Para datasets grandes (500+ imagens)**
```
Máx. Processos Paralelos: 0 (auto)
Dividir Dataset: 999999 (auto-detect)
Sobreposição Split: 150-200m
Tipo de Merge: all
```
💡 **Dica:** Reduz tempo em 50-70%

---

#### 5️⃣ Qualidade
**Controle fino de qualidade**
```
Detecção de Features: ultra/high/medium/low/lowest
Nuvem de Pontos: ultra/high/medium/low/lowest
Mapa de Profundidade: ultra/high/medium/low/lowest
Mín. Features: 4000-50000
```

---

#### 6️⃣ Resolução
```
Ortofoto: 1-100 cm/pixel (0 = máximo)
DEM: 1-100 cm/pixel
```
💡 **Dica:** Menor = melhor qualidade, maior tempo

---

#### 7️⃣ Modelo 3D
```
Tamanho da Malha: 50k-1M faces
Profundidade Octree: 6-14
☐ Pular geração de modelo 3D
```

---

#### 8️⃣ ☁️ Nuvem de Pontos Avançado
**Classificação e filtragem**
```
☐ Classificar automaticamente (chão, vegetação)
☐ Filtro geométrico
☐ Retificar nuvem
Filtro de Ruído: 0-100
Amostragem: 0-1 (0 = sem amostragem)
```
💡 **Use:** Topografia, análise de vegetação, BIM

---

#### 9️⃣ 📷 Câmera & Calibração
**Para câmeras especiais**
```
Tipo de Lente:
  • Auto (Detectar)
  • Perspectiva
  • Brown (Distorção)
  • Fisheye/Olho de Peixe
  • Esférica/360°

☐ Corrigir Rolling Shutter
  Tempo de Readout: 0-100 ms

☐ Usar parâmetros fixos de câmera
```
💡 **Use:** GoPro, smartphones, câmeras 360°

---

#### 🔟 ✂️ Recorte & Limites
```
Recortar Bordas: 0-100 pixels
☐ Forçar GPS (mesmo com GCPs)
```
💡 **Use:** Remover bordas ruins das fotos

---

#### 1️⃣1️⃣ 💾 Formatos de Saída
**Integração com outras plataformas**
```
☐ Ortofoto como PNG
☐ KMZ para Google Earth
☐ Tiles XYZ/TMS (web maps)
☐ COG (Cloud-Optimized GeoTIFF)
☐ 3D Tiles (Cesium)
☐ Mapa Euclidiano DEM
```

| Formato | Uso |
|---------|-----|
| PNG | Visualização simples |
| KMZ | Google Earth |
| Tiles | Leaflet, Mapbox |
| COG | Streaming GIS |
| 3D Tiles | Cesium (web 3D) |

---

#### 1️⃣2️⃣ 🎨 Texturização Avançada
**Para modelos 3D perfeitos**
```
Termo de Dados: GMI / Área
☐ Pular nivelamento global
☐ Pular nivelamento local
☐ Pular preenchimento de buracos
☐ Manter faces não vistas
```
💡 **Use:** Otimizar qualidade vs performance

---

#### 1️⃣3️⃣ ⚙️ Memória & Otimização
**Para máquinas com recursos limitados**
```
Redimensionar Imagens: 0-10000 pixels
  (0 = original, 2048 = rápido)

☐ Otimizar espaço em disco
  (deleta arquivos intermediários)
```
💡 **Dica:** Resize=2048 economiza 60-80% do tempo

---

#### 1️⃣4️⃣ 🐛 Debug & Monitoramento
**Para troubleshooting**
```
☐ Saída verbosa (detalhada)
☐ Mostrar tempos de execução
☐ Modo debug (salvar intermediários)
```
⚠️ **Atenção:** Debug pode usar 5-10x mais disco!

---

#### 1️⃣5️⃣ Pontos de Controle (GCP)
```
☐ Usar arquivo GCP
  Precisão GCP: 0.001-10 metros
```
💡 **Use:** Topografia de alta precisão

---

#### 1️⃣6️⃣ Otimização Geral
```
☐ Ortofoto Rápida (menor qualidade)
☐ Auto-mascaramento de bordas
☐ Ignorar GSD

Calibração Radiométrica:
  • Nenhuma
  • Apenas Câmera
  • Câmera + Sol
```

---

## 🎯 Casos de Uso Comuns

### 1. 🏗️ Construção Civil (Padrão)
```
Preset: Padrão
Produtos: Ortofoto ✓, DSM ✓
Formato: KMZ ✓ (para compartilhar)
```

### 2. 🚜 Agricultura com NDVI
```
Preset: Agricultura
Produtos: Ortofoto ✓
Calibração: Câmera + Sol
Formato: Tiles ✓, KMZ ✓
```

### 3. 📐 Topografia de Alta Precisão
```
Preset: Topografia
Produtos: Ortofoto ✓, DSM ✓, DTM ✓, Nuvem ✓
GCP: ✓ enabled
PC Classify: ✓
PC Geometric: ✓
Formato: COG ✓
```

### 4. 🎲 Modelo 3D para Visualização
```
Preset: Modelo 3D
Produtos: Modelo 3D ✓, Nuvem ✓
Formato: 3D Tiles ✓
PC Classify: ✓
Texturização: padrão (GMI)
```

### 5. ⚡ Preview Rápido (Teste)
```
Preset: Rápido
Resize To: 2048
Optimize Disk: ✓
Fast Orthophoto: ✓
Produtos: Ortofoto ✓
```

### 6. 🏔️ Dataset Grande (1000+ fotos)
```
Preset: Custom
Split: 999999 (auto)
Split Overlap: 200m
Merge: all
Max Concurrency: 0 (auto)
Optimize Disk: ✓
```

---

## ⏱️ Estimativa de Tempo

O sistema calcula automaticamente baseado em:
- Qualidade selecionada
- Produtos adicionais
- Classificação de nuvem
- Geração de tiles
- Split (reduz tempo)
- Resize (reduz tempo)
- Debug (aumenta tempo)

**Exemplo:**
```
100 imagens, Alta Qualidade, Modelo 3D, Tiles
→ Estimativa: 2h 30min
```

---

## 💡 Dicas Rápidas

### ⚡ Acelerar Processamento
1. Use preset "Rápido"
2. Resize To: 2048
3. Split: 999999 (auto)
4. Fast Orthophoto: ✓
5. Skip Model: ✓

### 🎯 Máxima Qualidade
1. Preset: Alta Qualidade
2. Feature Quality: ultra
3. PC Quality: high
4. Orthophoto Res: 1-2 cm/pixel
5. Min Features: 20000

### 💾 Economizar Espaço
1. Optimize Disk Space: ✓
2. PC Sample: 0.5 (reduz 50%)
3. Skip Report: ✓
4. Não usar Debug mode

### 🐛 Troubleshooting
1. Verbose: ✓
2. Time: ✓
3. Verificar logs do NodeODM

---

## 📊 Comparação de Presets

| Preset | Tempo | Qualidade | Espaço | Uso |
|--------|-------|-----------|--------|-----|
| ⚡ Rápido | 10min | ★★☆☆☆ | 500MB | Teste |
| ⚖️ Padrão | 30min | ★★★★☆ | 2GB | Geral |
| 🎯 Alta | 1-2h | ★★★★★ | 5GB | Topografia |
| 🎲 3D | 2-3h | ★★★★★ | 10GB | Visualização |
| 🌾 Agricultura | 45min | ★★★★☆ | 3GB | NDVI |
| 📐 Topografia | 2-4h | ★★★★★ | 8GB | GCP/Precisão |

*Tempos para ~100 imagens em máquina i7/16GB RAM*

---

## ✅ Checklist Antes de Processar

- [ ] Preset selecionado adequado ao uso
- [ ] Produtos necessários marcados
- [ ] Resolução adequada (menor = mais tempo)
- [ ] Para 500+ imagens: Split habilitado
- [ ] Para topografia: GCP configurado
- [ ] Para 3D: Modelo 3D e texturas habilitados
- [ ] Espaço em disco suficiente (5-10GB por task)
- [ ] Verificar estimativa de tempo

---

## 🆘 Suporte

Para dúvidas sobre opções específicas:
1. Passe o mouse sobre ⓘ (tooltips)
2. Leia `<small>` texts abaixo dos campos
3. Consulte [ODM Docs](https://docs.opendronemap.org/)
4. Verifique logs do container NodeODM

---

**Última atualização:** 21/01/2026
**Versão:** 2.0 - Opções Completas
