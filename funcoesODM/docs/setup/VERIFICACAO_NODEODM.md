#  Verificação NodeODM  FuncoesODM

> Gerado em: 2026-01-21 16:30:22

---

##  Resumo

| Item | Quantidade |
|------|-----------|
| Opções NodeODM (\config.py\) | 105 |
| Opções mapeadas no frontend | 104 |
| Bindings na UI (\options.*\) | 107 |

---

##  Diferenças Encontradas

### Faltando no frontend

- \dem-\ *(opção incompleta/deprecada  verificar)*

### Extras no frontend

*(nenhuma)*

---

##  Opções por Seção (Títulos da UI)

###  Processamento Paralelo

| Opção | Descrição |
|-------|-----------|
| \maxConcurrency\ | Máximo de threads paralelas |
| \merge\ | Mesclar resultados |
| \split\ | Dividir processamento |
| \splitOverlap\ | Sobreposição ao dividir |

---

###  Nuvem de Pontos Avançado

| Opção | Descrição |
|-------|-----------|
| \pcClassify\ | Classificação de pontos |
| \pcFilter\ | Filtro de nuvem de pontos |
| \pcGeometric\ | Filtro geométrico |
| \pcRectify\ | Retificar nuvem de pontos |
| \pcSample\ | Amostragem de pontos |

---

###  Câmera & Calibração

| Opção | Descrição |
|-------|-----------|
| \cameraLens\ | Tipo de lente da câmera |
| \ollingShutter\ | Correção de rolling shutter |
| \ollingShutterReadout\ | Tempo de readout |
| \useFixedCameraParams\ | Parâmetros fixos de câmera |

---

###  Recorte & Limites

| Opção | Descrição |
|-------|-----------|
| \crop\ | Recorte da área de processamento |
| \orceGps\ | Forçar uso de GPS |

---

###  Formatos de Saída

| Opção | Descrição |
|-------|-----------|
| \cog\ | Cloud Optimized GeoTIFF |
| \demEuclideanMap\ | Mapa euclidiano do DEM |
| \orthophotoKmz\ | Exportar ortofoto como KMZ |
| \orthophotoPng\ | Exportar ortofoto como PNG |
| \	iles\ | Tiles de mapa |
| \	iles3d\ | Tiles 3D |

---

###  Texturização Avançada

| Opção | Descrição |
|-------|-----------|
| \	exturingDataTerm\ | Termo de dados para texturização |
| \	exturingKeepUnseenFaces\ | Manter faces não vistas |
| \	exturingSkipGlobalSeam\ | Ignorar costura global |
| \	exturingSkipLocalSeam\ | Ignorar costura local |

---

###  GPU & Aceleração

| Opção | Descrição |
|-------|-----------|
| \
oGpu\ | Desativar uso de GPU |

---

###  Debug & Monitoramento

| Opção | Descrição |
|-------|-----------|
| \debug\ | Modo debug detalhado |
| \	ime\ | Medir tempo de cada etapa |
| \erbose\ | Log verboso |

---

###  Qualidade

| Opção | Descrição |
|-------|-----------|
| \eatureQuality\ | Qualidade de extração de features |
| \pcQuality\ | Qualidade da nuvem de pontos |

---

###  Features & Depth Maps

| Opção | Descrição |
|-------|-----------|
| \depthMapQuality\ | Qualidade dos depth maps |
| \matcher\ | Algoritmo de matching |
| \minNumFeatures\ | Mínimo de features por imagem |

---

###  Resolução

| Opção | Descrição |
|-------|-----------|
| \demResolution\ | Resolução do DEM (cm/px) |
| \orthophotoResolution\ | Resolução da ortofoto (cm/px) |

---

###  Modelo 3D

| Opção | Descrição |
|-------|-----------|
| \meshOctreeDepth\ | Profundidade da octree da malha |
| \meshSize\ | Tamanho máximo da malha |
| \skipModel\ | Ignorar geração do modelo 3D |

---

###  Pontos de Controle (GCP)

| Opção | Descrição |
|-------|-----------|
| \gcpAccuracy\ | Precisão esperada dos GCPs |
| \useGcp\ | Usar arquivo GCP |

---

###  Otimização

| Opção | Descrição |
|-------|-----------|
| \utoMask\ | Máscara automática |
| \astOrthophoto\ | Ortofoto rápida (menor qualidade) |
| \ignoreGsd\ | Ignorar GSD do projeto |
| \adiometricCalibration\ | Calibração radiométrica |

---

###  Otimização & Memória

| Opção | Descrição |
|-------|-----------|
| \optimizeDiskSpace\ | Otimizar uso de disco |
| \esizeTo\ | Redimensionar imagens antes do processamento |

---

###  Opções Adicionais NodeODM

<details>
<summary>Ver lista completa de opções adicionais mapeadas</summary>

| Opção (camelCase) | Opção (kebab-case) |
|-------------------|--------------------|
| \lign\ | \lign\ |
| \utoBoundaryDistance\ | \uto-boundary-distance\ |
| \gRemoval\ | \g-removal\ |
| \oundary\ | \oundary\ |
| \uildOverviews\ | \uild-overviews\ |
| \cameras\ | \cameras\ |
| \copyTo\ | \copy-to\ |
| \dem\ | \dem\ |
| \demDecimation\ | \dem-decimation\ |
| \demGapfillSteps\ | \dem-gapfill-steps\ |
| \endWith\ | \end-with\ |
| \eatureType\ | \eature-type\ |
| \geo\ | \geo\ |
| \gltf\ | \gltf\ |
| \gpsAccuracy\ | \gps-accuracy\ |
| \gpsZOffset\ | \gps-z-offset\ |
| \help\ | \help\ |
| \matcherNeighbors\ | \matcher-neighbors\ |
| \matcherOrder\ | \matcher-order\ |
| \mergeSkipBlending\ | \merge-skip-blending\ |
| \orthophotoCompression\ | \orthophoto-compression\ |
| \orthophotoCutline\ | \orthophoto-cutline\ |
| \orthophotoNoTiled\ | \orthophoto-no-tiled\ |
| \pcCopc\ | \pc-copc\ |
| \pcCsv\ | \pc-csv\ |
| \pcEpt\ | \pc-ept\ |
| \pcLas\ | \pc-las\ |
| \pcSkipGeometric\ | \pc-skip-geometric\ |
| \primaryBand\ | \primary-band\ |
| \projectPath\ | \project-path\ |
| \erun\ | \erun\ |
| \erunAll\ | \erun-all\ |
| \erunFrom\ | \erun-from\ |
| \sfmAlgorithm\ | \sfm-algorithm\ |
| \sfmNoPartial\ | \sfm-no-partial\ |
| \skipBandAlignment\ | \skip-band-alignment\ |
| \skipOrthophoto\ | \skip-orthophoto\ |
| \skyRemoval\ | \sky-removal\ |
| \smCluster\ | \sm-cluster\ |
| \smNoAlign\ | \sm-no-align\ |
| \smrf\ | \smrf\ |
| \smrfScalar\ | \smrf-scalar\ |
| \smrfSlope\ | \smrf-slope\ |
| \smrfThreshold\ | \smrf-threshold\ |
| \smrfWindow\ | \smrf-window\ |
| \splitImageGroups\ | \split-image-groups\ |
| \	exturingOutlierRemovalType\ | \	exturing-outlier-removal-type\ |
| \	exturingSingleMaterial\ | \	exturing-single-material\ |
| \	exturingToneMapping\ | \	exturing-tone-mapping\ |
| \useExif\ | \use-exif\ |
| \useHybridBundleAdjustment\ | \use-hybrid-bundle-adjustment\ |
| \ersion\ | \ersion\ |
| \ideoLimit\ | \ideo-limit\ |
| \ideoResolution\ | \ideo-resolution\ |

</details>

---

##  Lista Completa de Opções Mapeadas (kebab-case)

<details>
<summary>Ver todas as 104 opções mapeadas</summary>

\\\
3d-tiles              align                 auto-boundary
auto-boundary-distance bg-removal            boundary
build-overviews       camera-lens           cameras
cog                   copy-to               crop
debug                 dem                   dem-decimation
dem-euclidean-map     dem-gapfill-steps     dem-resolution
depthmap-resolution   dsm                   dtm
end-with              fast-orthophoto       feature-quality
feature-type          force-gps             gcp
geo                   gltf                  gps-accuracy
gps-z-offset          help                  ignore-gsd
matcher-neighbors     matcher-order         matcher-type
max-concurrency       merge                 merge-skip-blending
mesh-octree-depth     mesh-size             min-num-features
no-gpu                optimize-disk-space   orthophoto-compression
orthophoto-cutline    orthophoto-kmz        orthophoto-no-tiled
orthophoto-png        orthophoto-resolution pc-classify
pc-copc               pc-csv                pc-ept
pc-filter             pc-geometric          pc-las
pc-quality            pc-rectify            pc-sample
pc-skip-geometric     primary-band          project-path
radiometric-calibration rerun               rerun-all
rerun-from            resize-to             rolling-shutter
rolling-shutter-readout sfm-algorithm       sfm-no-partial
skip-3dmodel          skip-band-alignment   skip-orthophoto
skip-report           sky-removal           sm-cluster
sm-no-align           smrf                  smrf-scalar
smrf-slope            smrf-threshold        smrf-window
split                 split-image-groups    split-overlap
texturing-data-term   texturing-keep-unseen-faces
texturing-outlier-removal-type              texturing-single-material
texturing-skip-global-seam-leveling         texturing-skip-local-seam-leveling
texturing-tone-mapping tiles                time
use-3dmesh            use-exif              use-fixed-camera-params
use-hybrid-bundle-adjustment                verbose
version               video-limit           video-resolution
\\\

</details>

---

>  **Documentação relacionada:** [Opções Completas NodeODM](../reference/OPCOES_NODEODM_COMPLETAS.md) | [Guia Rápido de Opções](../guides/GUIA_RAPIDO_OPCOES.md)
