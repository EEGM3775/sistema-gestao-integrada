# Sistema de Medições - FuncoesODM

## 📐 Visão Geral

Módulo completo de medições para projetos de fotogrametria, com suporte a:
- Medições 2D (ortofoto)
- Medições 3D (DEM, nuvem de pontos)
- Cálculos topográficos avançados
- Exportação para múltiplos formatos

## 🏗️ Arquitetura

```
measurement/
├── models/                          # Tipos e interfaces
│   └── measurement.model.ts         # ~350 linhas - Todos os tipos
├── services/                        # Lógica de negócio
│   ├── measurement.service.ts       # ~450 linhas - Core
│   ├── measurement-history.service.ts # ~250 linhas - Histórico
│   └── measurement-export.service.ts  # ~300 linhas - Exportação
├── components/                      # UI Components
│   ├── measurement-toolbar/         # ~150 linhas - Ferramentas
│   ├── measurement-panel/           # ~120 linhas - Resultados
│   └── measurement-history/         # Planejado
└── viewers/                         # Visualizadores
    ├── orthophoto-viewer/           # ~250 linhas - 2D
    ├── dem-viewer/                  # Planejado - DEM
    └── pointcloud-viewer/           # Planejado - 3D
```

**Total por arquivo: < 500 linhas ✅**

## 🎯 Features Implementadas

### ✅ Core (measurement.service.ts)
- CRUD de medições
- Cálculos geométricos (distância, área, volume)
- Perfis de elevação
- Conversão de unidades
- State management

### ✅ Histórico (measurement-history.service.ts)
- Undo/Redo
- Filtros e busca
- Estatísticas
- Comparação de medições

### ✅ Exportação (measurement-export.service.ts)
- PDF, CSV, GeoJSON, KML
- Relatórios customizados
- Thumbnails e mapas

### ✅ UI Components
- Toolbar com todas as ferramentas
- Panel de resultados em tempo real
- Configurações (unidades, precisão)

### ✅ Visualizadores
- Orthophoto Viewer completo
- DEM Viewer (estrutura)
- Pointcloud Viewer (estrutura)

## 🚀 Uso

### Integração em Projeto

```typescript
import { OrthophotoViewerComponent } from '@features/measurement';

// Em rotas
{
  path: 'project/:id/measurement',
  component: OrthophotoViewerComponent
}
```

### Uso Standalone

```typescript
import { MeasurementService } from '@features/measurement';

constructor(private measurementService: MeasurementService) {}

// Iniciar medição
this.measurementService.startMeasurement(
  MeasurementType.DISTANCE,
  MeasurementMode.ORTHOPHOTO
);

// Adicionar pontos
this.measurementService.addPoint({
  id: uuid(),
  lat: -23.550,
  lng: -46.633,
  elevation: 750,
  timestamp: new Date()
});

// Finalizar
this.measurementService.completeMeasurement()
  .subscribe(measurement => {
    console.log('Medição salva:', measurement);
  });
```

## 📊 Tipos de Medição

| Tipo | Ícone | Descrição | Modo |
|------|-------|-----------|------|
| DISTANCE | 📏 | Distância linear 2D/3D | Todos |
| AREA | ⬜ | Área de polígono | 2D, DEM |
| VOLUME | 📦 | Volume entre superfícies | DEM, 3D |
| ELEVATION | 📈 | Perfil de elevação | DEM |
| PERIMETER | ⭕ | Perímetro de polígono | Todos |
| SLOPE | ⛰️ | Inclinação do terreno | DEM |
| ANGLE | ∠ | Ângulo entre linhas | Todos |
| HEIGHT | 📐 | Altura de objeto | 3D |

## 📤 Formatos de Exportação

- **PDF**: Relatório completo com mapas
- **CSV**: Dados tabulares
- **GeoJSON**: Formato geoespacial padrão
- **KML**: Google Earth
- **DXF**: CAD (planejado)

## 🔧 Configuração

```typescript
import { DEFAULT_MEASUREMENT_SETTINGS } from '@features/measurement';

// Customizar unidades padrão
settings.defaultUnit = MeasurementUnit.FEET;
settings.defaultPrecision = 3;

// Estilo visual
settings.defaultStyle = {
  strokeColor: '#FF6B6B',
  strokeWidth: 3,
  fillOpacity: 0.2
};
```

## 📝 TODO

- [ ] Implementar DEM Viewer
- [ ] Implementar Pointcloud Viewer  
- [ ] Componente de histórico de medições
- [ ] Integração com backend real
- [ ] Testes unitários
- [ ] Documentação de API

## 🎨 Padrões de Desenvolvimento

### Limites de Arquivo
- ✅ Nenhum arquivo > 500 linhas
- ✅ Componentes < 300 linhas
- ✅ Services < 500 linhas
- ✅ Models < 400 linhas

### Arquitetura
- Standalone components
- Signals para state
- RxJS para async
- Modular e desacoplado

### Estilo
- SCSS modular
- BEM naming
- Responsive design
- Acessibilidade

## 📖 Referências

- [Leaflet](https://leafletjs.com/) - Mapas 2D
- [Three.js](https://threejs.org/) - Visualização 3D
- [Turf.js](https://turfjs.org/) - Cálculos geoespaciais
