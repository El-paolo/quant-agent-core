# FINA -- Guia de Desarrollo

Documentacion tecnica para mantener y extender el software. Cubre arquitectura, conexiones entre modulos, y procedimientos para agregar features.

---

## Indice

1. [Arquitectura general](#1-arquitectura-general)
2. [Estructura de directorios](#2-estructura-de-directorios)
3. [Flujo de datos](#3-flujo-de-datos)
4. [Backend: modulos y conexiones](#4-backend-modulos-y-conexiones)
5. [Frontend: modulos y conexiones](#5-frontend-modulos-y-conexiones)
6. [Como agregar un nuevo endpoint](#6-como-agregar-un-nuevo-endpoint)
7. [Como agregar un nuevo panel al frontend](#7-como-agregar-un-nuevo-panel-al-frontend)
8. [Como agregar un nuevo modelo cuantitativo](#8-como-agregar-un-nuevo-modelo-cuantitativo)
9. [Como agregar una nueva metrica/indicador](#9-como-agregar-una-nueva-metricaindicador)
10. [Sistema de cache](#10-sistema-de-cache)
11. [Testing](#11-testing)
12. [Configuracion y variables de entorno](#12-configuracion-y-variables-de-entorno)
13. [Mapa de dependencias entre archivos](#13-mapa-de-dependencias-entre-archivos)

---

## 1. Arquitectura general

```
┌──────────────────────────────────────────────────────┐
│                    FRONTEND                          │
│  app.html ← state.js ← api.js ← panels.js          │
│                         ↕ fetch()                    │
├──────────────────────────────────────────────────────┤
│                   FastAPI (api/)                      │
│  routes/ → schemas.py (validacion)                   │
│         → dependencies.py (inyeccion Settings)       │
│         → middleware.py (CORS, rate-limit, headers)   │
├──────────────────────────────────────────────────────┤
│               ORCHESTRATION (orchestration/)          │
│  Wrappers que encadenan fetch → clean → compute      │
│  con manejo de errores estructurado                  │
├──────────────────────────────────────────────────────┤
│               LOGICA DE NEGOCIO                      │
│  metrics/   models/   backtest/   agent/             │
├──────────────────────────────────────────────────────┤
│                 DATA (data/)                          │
│  fetcher.py (yfinance + cache)                       │
│  cleaner.py (NaN, outliers, timezone)                │
├──────────────────────────────────────────────────────┤
│                 CORE (core/)                          │
│  config.py (Settings) + exceptions.py                │
└──────────────────────────────────────────────────────┘
```

**Principios:**
- Cada capa solo importa de capas inferiores (nunca al reves).
- `routes/` nunca contiene logica de negocio; delega a `orchestration/`.
- `orchestration/` nunca accede a la API ni al frontend.
- Todas las importaciones son absolutas: `from fina.data.fetcher import ...`
- Los `__init__.py` estan vacios — no hay re-exports magicos.

---

## 2. Estructura de directorios

```
src/fina/
├── core/                   # Config + excepciones (base de todo)
│   ├── config.py           # Settings via pydantic-settings, carga .env
│   └── exceptions.py       # FetcherError, MetricsError, BacktestError, etc.
│
├── data/                   # Adquisicion y limpieza de datos
│   ├── fetcher.py          # yfinance: precios, OHLC, volumen, fundamentales
│   └── cleaner.py          # NaN, outliers (Z-score modificado), timezones
│
├── metrics/                # Metricas financieras (sin dependencia de modelos)
│   ├── returns.py          # Retornos simples y logaritmicos
│   ├── volatility.py       # Vol realizada + rolling (21d, anualizada)
│   ├── ratios.py           # Sharpe, Sortino
│   ├── technical.py        # RSI, MACD, Bollinger Bands
│   └── correlation.py      # Correlacion, Beta vs benchmark
│
├── models/                 # Modelos cuantitativos
│   ├── arima.py            # Auto-ARIMA (pmdarima), walk-forward
│   ├── garch.py            # GARCH(1,1) (arch), vol condicional + forecast
│   ├── hmm.py              # HMM Gaussiano (hmmlearn), deteccion de regimenes
│   └── comparator.py       # Comparador lado a lado, metricas estandarizadas
│
├── backtest/               # Motor de backtesting
│   ├── engine.py           # Orquestador: fetch → signals → simulate → metrics
│   ├── signals.py          # Generacion de señales ARIMA/HMM/GARCH + combine
│   ├── strategy.py         # Simulacion de estrategia, equity curve, trades
│   ├── metrics.py          # Metricas de performance (Sharpe, drawdown, etc.)
│   └── montecarlo.py       # N simulaciones GARCH parametricas + agregacion
│
├── agent/                  # Asistente IA
│   ├── assistant.py        # Q&A contextual con litellm (system prompt + context)
│   ├── news.py             # Fetch noticias via yfinance
│   ├── summarizer.py       # Resumen de noticias con LLM
│   ├── state.py            # Estado del agente
│   └── providers/          # Abstraccion de proveedores LLM
│       ├── base.py         # Protocol LLMProvider
│       ├── ollama.py       # Implementacion Ollama local
│       └── anthropic.py    # Implementacion Anthropic (placeholder)
│
├── orchestration/          # Pipelines que encadenan modulos
│   ├── analysis.py         # fetch → clean → metrics (run_analysis)
│   ├── models.py           # fetch → clean → returns → fit models
│   └── backtest.py         # Wrappers para run_backtest, run_montecarlo
│
├── api/                    # Capa HTTP
│   ├── main.py             # Factory create_app(), registro de routers
│   ├── schemas.py          # Pydantic v2: request/response models
│   ├── dependencies.py     # SettingsDep, AgentSettingsDep
│   ├── middleware.py        # Rate limit, security headers, timing
│   └── routes/
│       ├── health.py       # GET /health
│       ├── analysis.py     # POST /analysis/
│       ├── timeseries.py   # POST /analysis/timeseries/
│       ├── agent.py        # POST /agent/summarize/, /agent/ask/
│       ├── models.py       # POST /models/, /models/timeseries/, /models/compare/
│       ├── backtest.py     # POST /backtest/, /backtest/montecarlo/
│       └── fundamentals.py # GET /fundamentals/{ticker}
│
├── editorial/              # (Futuro) Generacion de reportes PDF
└── sentiment/              # (Futuro) Analisis de sentiment Reddit

frontend/
├── index.html              # Landing page
├── app.html                # Workspace (SPA)
├── css/
│   ├── main.css            # Estilos landing (design tokens, tipografia)
│   └── app.css             # Estilos workspace (panels, charts, grids)
└── js/
    ├── main.js             # Landing: scroll animations, nav
    ├── state.js            # Estado global, constantes, helpers, DOM refs ($)
    ├── api.js              # Fetch API, switchToPanel, health check
    ├── charts.js           # Chart.js: render de todos los graficos + pin system
    ├── panels.js           # Render de panels (overview, metrics, tech, models)
    ├── backtest.js         # Panel backtest + Monte Carlo
    └── assistant.js        # Drawer Q&A (toggle, send, render messages)

tests/unit/                 # 603 tests, ~96% coverage
    test_*.py               # Un archivo por modulo, mocks para yfinance/LLM
```

---

## 3. Flujo de datos

### Analisis de un ticker (flujo principal)

```
Usuario escribe "AAPL" → click "Analizar"
    │
    ├─ api.js: POST /analysis/        → analysis.py route
    │   └─ orchestration/analysis.py: run_analysis()
    │       ├─ fetcher.fetch_close_prices("AAPL", period="1y")
    │       ├─ cleaner.clean_prices(prices)
    │       ├─ returns.compute_returns(prices)
    │       ├─ volatility.compute_volatility(returns)
    │       ├─ ratios.compute_sharpe(returns)
    │       ├─ technical.compute_rsi(prices)
    │       └─ ... (todas las metricas pedidas)
    │
    ├─ api.js: POST /analysis/timeseries/  → timeseries.py route
    │   └─ Mismos datos, formato series temporales para charts
    │
    ├─ api.js: POST /agent/summarize/  → agent.py route
    │   └─ news.fetch_news() → summarizer.summarize()
    │
    └─ api.js: GET /fundamentals/AAPL  → fundamentals.py route
        └─ fetcher.fetch_fundamentals("AAPL")

Respuestas → panels.js renderOverview() → charts.js render*()
```

### Backtest

```
Usuario configura fechas/modelos → click "Ejecutar Backtest"
    │
    backtest.js: POST /backtest/
    └─ orchestration/backtest.py → engine.run_backtest()
        ├─ fetcher.fetch_close_prices(ticker, start, end)
        ├─ Separa train/test por fecha
        ├─ signals.generate_arima_signals(train, test)
        ├─ signals.generate_hmm_signals(train, test)
        ├─ signals.generate_garch_sizing(train, test)
        ├─ signals.combine_signals(arima, hmm, garch)
        ├─ strategy.simulate_strategy(positions, test_prices)
        └─ metrics.compute_backtest_metrics(equity, returns, trades)
```

### Monte Carlo

```
Usuario click "Simular" (dentro de resultados de backtest)
    │
    backtest.js: POST /backtest/montecarlo/
    └─ montecarlo.run_montecarlo()
        ├─ _fit_models(train_returns, ...) → _MCModels dataclass
        └─ Loop N veces:
            ├─ _simulate_garch_path() → retornos sinteticos
            ├─ _arima_signals_synthetic() (deepcopy por sim)
            ├─ _hmm_signals_synthetic() (read-only predict)
            ├─ _garch_sizing_synthetic()
            ├─ combine_signals() → positions
            └─ simulate_strategy() → equity, metrics
        └─ _aggregate() → fan_chart (percentiles), VaR, CVaR
```

---

## 4. Backend: modulos y conexiones

### core/config.py
- **Lee:** `.env`, variables de entorno del OS
- **Usado por:** `api/dependencies.py` (inyeccion), `agent/assistant.py` (modelo LLM)
- **Para modificar:** agregar campo a la clase `Settings`, con default. Si necesita validacion, agregar metodo.

### core/exceptions.py
- **Define:** `FetcherError`, `MetricsError`, `BacktestError`, `ValidationError`, `ConfigError`, `ReturnsError`, `VolatilityError`
- **Usado por:** Toda la capa de negocio. Las routes los capturan con try/except y devuelven HTTP 422/500.
- **Para agregar:** Heredar de la excepcion base mas cercana. No olvidar capturarla en la route correspondiente.

### data/fetcher.py
- **Importa:** yfinance, cachetools
- **Funciones publicas:** `fetch_close_prices()`, `fetch_volume()`, `fetch_ohlc()`, `fetch_fundamentals()`, `configure_price_cache()`
- **Cache:** `TTLCache` con lock para thread-safety (FastAPI corre fetchers en threadpool via `asyncio.to_thread`).
- **Seguridad:** Regex estricto `^[A-Z0-9\-=\.]{1,20}$` para tickers. Fechas validadas contra rango 1970-2100.
- **Para agregar un nuevo tipo de dato:** Usar `_fetch_history()` interno (ya cachea el DataFrame completo) y extraer la columna necesaria.

### data/cleaner.py
- **Importa:** pandas, numpy
- **Usado por:** orchestration/analysis.py, backtest/engine.py
- **Hace:** NaN forward-fill, timezone strip, outlier detection via Z-score modificado.

### metrics/ (returns, volatility, ratios, technical, correlation)
- **Cada modulo:** Recibe pd.Series o DataFrame, devuelve dict con resultados.
- **No hace fetch de datos** — solo computo puro.
- **Agregar metrica:** Crear funcion en el modulo correspondiente, agregar a `orchestration/analysis.py`, agregar al frontend.

### models/ (arima, garch, hmm, comparator)
- **Cada modulo:** Recibe retornos (pd.Series), ajusta modelo, devuelve dict con diagnosticos, predicciones, validacion train/test.
- **arima.py:** Usa `pmdarima.auto_arima()`. Walk-forward 1-step.
- **garch.py:** Usa `arch.arch_model()`. Escala ×100 interna. `show_warning=False` para suprimir convergence warnings.
- **hmm.py:** Usa `hmmlearn.GaussianHMM`. Ordena estados por varianza (0=low_vol). Mapea regimenes a señales.
- **comparator.py:** Corre ARIMA y GARCH lado a lado, normaliza metricas.

### backtest/signals.py (CRITICO — logica de señales)
- **`generate_arima_signals()`**: Walk-forward predict+update. Retorna `signals=None` si ARIMA(0,0,0).
- **`generate_hmm_signals()`**: Mapea estados a {-1, 0, +1} via rank por varianza.
- **`generate_garch_sizing()`**: `target_vol / cond_vol`, clipped [0.5, 2.0].
- **`combine_signals()`**: HMM = base, ARIMA override cuando no-cero, HMM -1 siempre override a 0 (risk-off), GARCH escala tamaño.

### backtest/strategy.py
- **`simulate_strategy()`**: `shifted_pos = pos.shift(1).fillna(0)` (sin look-ahead). Calcula equity curve, benchmark, trades.
- **Trades:** Iteracion sobre cambios de posicion, calcula entry/exit/pnl/duracion.

### backtest/montecarlo.py
- **`_MCModels` dataclass:** Contiene todos los parametros de modelos ajustados.
- **`_simulate_garch_path()`:** Varianza cap, floor, shock clipping 10sigma.
- **`_arima_signals_synthetic()`:** `deepcopy` por simulacion (~50ms/sim, inevitable).
- **`_hmm_signals_synthetic()`:** `.predict()` es read-only, sin copia.
- **Punto clave:** `run_montecarlo()` requiere minimo 10 simulaciones exitosas (`_MC_MIN_SUCCESSFUL`).

### orchestration/ (analysis, models, backtest)
- **Patron:** Wrapper fino que encadena modulos y re-raise excepciones.
- **No agregar logica aqui** — solo coordinacion y error handling.

### api/schemas.py
- **Define:** Todos los request/response Pydantic models.
- **Validacion:** Regex para tickers, ISO dates, enum para periodos validos, rango para n_simulations [50-300].
- **Para agregar endpoint:** Crear request+response models aqui primero.

### api/routes/
- **Patron de cada route:**
  1. Recibe request validado por schema
  2. `await asyncio.to_thread(orchestration_function, ...)` para CPU-bound
  3. try/except: `FetcherError`/`MetricsError` → 422, `Exception` → 500
  4. Retorna response model
- **Rate limit:** 30 req/min (configurable en middleware.py).

### api/main.py
- **Factory pattern:** `create_app(settings=None)` — permite inyectar Settings en tests.
- **Orden de middleware:** timing → security headers → rate limit → CORS (ultimo aplicado = mas externo).
- **Static files:** Sirve `frontend/` en `/static`, `app.html` en `/app`, `index.html` en `/`.

---

## 5. Frontend: modulos y conexiones

### Namespace global: `window.FINA`

Todos los modulos JS usan IIFE `(() => { ... })()` y se comunican via `window.FINA`:

```
state.js  →  Define window.FINA (state, $, charts, helpers)
charts.js →  Lee FINA, expone renderXChart(), pin system
panels.js →  Lee FINA, expone renderOverview(), renderTechnicalsPanel()
api.js    →  Lee FINA, expone switchToPanel(), checkHealth(), triggerAnalysis()
backtest.js → Lee FINA, expone loadBacktestPanel()
assistant.js → Lee FINA, maneja drawer Q&A
```

**Orden de carga en app.html:**
```html
<script src="/static/js/state.js"></script>    <!-- 1. Primero: define FINA -->
<script src="/static/js/charts.js"></script>   <!-- 2. Chart rendering -->
<script src="/static/js/panels.js"></script>   <!-- 3. Panel logic -->
<script src="/static/js/api.js"></script>      <!-- 4. API + orchestration -->
<script src="/static/js/backtest.js"></script> <!-- 5. Backtest panel -->
<script src="/static/js/assistant.js"></script><!-- 6. Q&A drawer -->
```

**El orden importa.** Cada modulo asume que los anteriores ya expusieron sus funciones en `FINA`.

### state.js
- **Define:** `FINA.state` (estado de la app), `FINA.$` (refs a elementos DOM), `FINA.charts` (instancias Chart.js), helpers (`fmt`, `fmtPct`, `fmtSign`, `show`, `hide`, `escHtml`).
- **Para agregar estado:** Agregar campo en `state`, ref DOM en `$`, slot de chart en `charts`.

### charts.js
- **Registra plugins:** candleWick (wicks en candlestick), pinLines (lineas verticales sincronizadas).
- **`baseChartOptions()`:** Config compartida: tooltip, zoom/pan, grid, escalas.
- **`sparseLabels()`:** Reduce labels del eje X manteniendo largo del array (blank los intermedios).
- **Pin system:** `pinGroups` define grupos de charts sincronizados. `dblclick` agrega/remueve pin. Cada chart almacena `_pinFullDates` para mostrar fecha real.
- **Para agregar chart:** Crear funcion `renderNewChart()`, registrar en `charts` (state.js), exponer en `F.renderNewChart`, destruir en api.js al cambiar panel.

### panels.js
- **`renderOverview()`:** Construye metric cards + llama fetchFundamentals().
- **`loadMetricsPanel()`:** Fetch timeseries → render price/vol/bb/volume charts + initPinGroup("metrics").
- **`loadTechnicalsPanel()`:** Fetch RSI/MACD/BB → render + initPinGroup("technicals").
- **`loadModelsPanel()`:** Fetch models + comparison → render GARCH/HMM/ARIMA charts.
- **Para agregar panel:** Agregar case en `switchToPanel()` (api.js), crear load/render functions aqui.

### api.js
- **`switchToPanel(name)`:** Oculta todos los panels, muestra el seleccionado, destruye charts del panel anterior, llama load correspondiente.
- **`triggerAnalysis()`:** Lanza 3 calls paralelas (analysis, timeseries, agent) + fundamentals.
- **`checkHealth()`:** Polling cada 30s a `/health`.
- **Para agregar panel al switch:** Agregar el `else if` en switchToPanel, agregar hide del panel en la seccion de ocultar, agregar destruccion de charts al salir.

### backtest.js
- **`runBacktest()`:** POST /backtest/ con fechas/modelos del form.
- **`runMonteCarlo()`:** POST /backtest/montecarlo/ usando mismos parametros + n_simulations.
- **`renderBacktestResults()`:** Equity chart, metrics cards, benchmark row, positions chart, trades table, signals summary.
- **`renderMonteCarloResults()`:** Fan chart (P5-P95), risk cards (VaR/CVaR/prob), distribution grid.
- **Fechas default:** test_end=hoy, test_start=6mo atras, train_end=dia antes de test_start, train_start=2yr antes de train_end.

### assistant.js
- **`gatherContext()`:** Recolecta estado actual (metricas, modelos, backtest, MC, fundamentales) para enviar como contexto al LLM.
- **`sendQuestion()`:** POST /agent/ask/ con question + context.
- **Para agregar contexto:** Agregar campo en `gatherContext()` (JS) y en `_build_context_block()` (Python, assistant.py).

---

## 6. Como agregar un nuevo endpoint

**Ejemplo: agregar `GET /analysis/sectors/`**

### Paso 1: Schema (src/fina/api/schemas.py)
```python
class SectorResponse(BaseModel):
    sectors: list[dict[str, Any]]
```

### Paso 2: Logica de negocio (modulo existente o nuevo)
```python
# src/fina/metrics/sectors.py
def compute_sector_data(...) -> dict:
    ...
```

### Paso 3: Orchestration (opcional, si encadena varios modulos)
```python
# src/fina/orchestration/analysis.py
def run_sector_analysis(...) -> dict:
    ...
```

### Paso 4: Route (src/fina/api/routes/)
```python
# En archivo existente o nuevo
@router.get("/sectors/", response_model=SectorResponse)
async def get_sectors(...):
    result = await asyncio.to_thread(run_sector_analysis, ...)
    return SectorResponse(**result)
```

### Paso 5: Registrar router (src/fina/api/main.py)
```python
from fina.api.routes.sectors import router as sectors_router
app.include_router(sectors_router, prefix="/analysis")
```

### Paso 6: Tests (tests/unit/test_sectors.py)
- Mockear `fetch_close_prices` o el fetcher que use.
- Testear logica pura + route via `TestClient`.

---

## 7. Como agregar un nuevo panel al frontend

**Ejemplo: agregar panel "Sentiment"**

### Paso 1: HTML (frontend/app.html)
```html
<!-- Agregar boton en el rail (nav) -->
<button class="rail-link" data-panel="sentiment">
  <svg class="rail-icon">...</svg>
  <span class="rail-label">Sentiment</span>
</button>

<!-- Agregar panel en el canvas -->
<div id="sentiment-panel" class="panel hidden">
  <div class="panel-header">
    <h2 class="panel-title" id="sentiment-panel-ticker"></h2>
  </div>
  <div id="sentiment-content" class="hidden">...</div>
</div>
```

### Paso 2: DOM refs (frontend/js/state.js)
```javascript
sentimentPanel:  document.getElementById("sentiment-panel"),
sentimentContent: document.getElementById("sentiment-content"),
// + agregar chart slot si necesario: sentChart: null en charts
```

### Paso 3: Panel logic (frontend/js/panels.js o archivo nuevo)
```javascript
const loadSentimentPanel = () => {
  // fetch data, render
};
F.loadSentimentPanel = loadSentimentPanel;
```

### Paso 4: Registrar en switch (frontend/js/api.js)
En `switchToPanel()`:
```javascript
// Agregar hide
hide($.sentimentPanel);

// Agregar show + load
else if (panelName === "sentiment") {
  show($.sentimentPanel);
  if (state.analysisResult) loadSentimentPanel();
}

// Agregar destruccion de charts al salir
if (prevPanel === "sentiment" && panelName !== "sentiment") {
  ["sentChart"].forEach(F.destroyChart);
}
```

### Paso 5: CSS (frontend/css/app.css)
Agregar estilos especificos del panel.

### Paso 6: Script tag (frontend/app.html)
Si es archivo nuevo, agregar `<script>` despues de panels.js y antes de api.js (o despues de api.js si usa funciones de api.js).

---

## 8. Como agregar un nuevo modelo cuantitativo

**Ejemplo: agregar modelo LSTM**

### Paso 1: Modulo del modelo (src/fina/models/lstm.py)
```python
def fit_lstm(returns: pd.Series, train_ratio=0.8, ...) -> dict:
    """
    Retornar dict con:
    - diagnostics: dict con metricas del modelo
    - predictions: dict con forecast
    - validation: dict con metricas train/test
    - warnings: list[str]
    """
```

### Paso 2: Integrarlo en orchestration (src/fina/orchestration/models.py)
Agregar al pipeline de modelos, con try/except y degradacion graceful.

### Paso 3: Schema de respuesta (src/fina/api/schemas.py)
Agregar campo `lstm: dict[str, Any] | None = None` al `ModelsResponse`.

### Paso 4: Para backtest — agregar señales (src/fina/backtest/signals.py)
```python
def generate_lstm_signals(train, test, ...) -> dict:
    ...
```
Y actualizar `combine_signals()` si el modelo aporta direccion o sizing.

### Paso 5: Para Monte Carlo (src/fina/backtest/montecarlo.py)
Agregar al `_MCModels` dataclass, `_fit_models()`, y crear `_lstm_signals_synthetic()`.

### Paso 6: Frontend
Agregar visualizacion en el panel de modelos (charts.js + panels.js).

---

## 9. Como agregar una nueva metrica/indicador

### Metricas numericas (tipo Sharpe, Sortino)

1. **Implementar** en `src/fina/metrics/` (archivo existente o nuevo)
2. **Agregar** a `_KNOWN_METRICS` en `schemas.py`
3. **Computar** en `orchestration/analysis.py` dentro de `run_analysis()`
4. **Renderizar** en `panels.js` dentro de `buildMetricCards()`
5. **Test** en `tests/unit/`

### Indicadores tecnicos (tipo RSI, MACD — con serie temporal)

1. **Implementar** en `src/fina/metrics/technical.py`
2. **Agregar** a `_KNOWN_TIMESERIES` en `schemas.py`
3. **Computar** en la route `timeseries.py`
4. **Renderizar chart** en `charts.js` (nueva funcion render)
5. **Llamar render** desde `panels.js` en `renderTechnicalsPanel()` o `renderMetricsPanel()`
6. **Agregar canvas** en `app.html`
7. **Agregar chart key** en `state.js` (`charts` object)
8. **Destruir** en `api.js` al cambiar de panel

---

## 10. Sistema de cache

| Cache | Ubicacion | TTL | Proposito |
|-------|-----------|-----|-----------|
| `_price_cache` | `data/fetcher.py` | 300s (5min) | Precios, OHLC, volumen de yfinance |
| `_fundamentals_cache` | `data/fetcher.py` | 600s (10min) | Datos fundamentales de empresa |
| `_news_cache` | `agent/news.py` | 900s (15min) | Noticias de Yahoo Finance |

- Todos usan `cachetools.TTLCache` con `threading.Lock` para thread-safety.
- `configure_price_cache()` y `configure_news_cache()` se llaman en `create_app()` con valores de Settings.
- La cache es **en memoria** — se pierde al reiniciar el servidor.
- Los fetchers internos (`_fetch_history`) cachean el DataFrame completo; las funciones publicas (`fetch_close_prices`, `fetch_volume`) extraen columnas del DataFrame cacheado.

---

## 11. Testing

### Ejecutar tests
```bash
# Todos los tests
python -m pytest tests/unit/ -q

# Un modulo especifico
python -m pytest tests/unit/test_backtest_signals.py -v

# Con coverage
python -m pytest tests/unit/ --cov=fina --cov-report=term-missing
```

### Convenciones
- **Un archivo de test por modulo:** `test_<modulo>.py`
- **Fixtures:** En `conftest.py` o al inicio del archivo de test.
- **Mocks:** Todas las llamadas a yfinance y LLMs se mockean con `unittest.mock.patch`.
- **Route tests:** Usan `fastapi.testclient.TestClient`.
- **Patron de mock para fetcher:**
```python
@pytest.fixture
def mock_prices():
    dates = pd.date_range("2022-01-03", periods=500, freq="B")
    rng = np.random.default_rng(42)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 500))), index=dates)

def test_algo(mock_prices):
    with patch("fina.modulo.fetch_close_prices", return_value=mock_prices):
        result = funcion_a_testear(...)
```

### Gotchas
- `test_config.py`: Usa `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` + `Settings(_env_file=None)` para aislar de variables del OS.
- HMM tests: Necesitan datos con estructura de regimenes real (3 segmentos distintos), no random uniforme — Cholesky falla con datos sin estructura.
- ARIMA(0,0,0): Es comun para retornos de acciones. Los tests deben contemplar `signals=None` en este caso.

---

## 12. Configuracion y variables de entorno

### .env
```
LLM_PROVIDER=ollama          # "ollama" o "anthropic"
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
ANTHROPIC_API_KEY=            # Solo si LLM_PROVIDER=anthropic
NEWS_API_KEY=                 # No requerido (yfinance no lo necesita)
```

### Settings (src/fina/core/config.py)
| Campo | Default | Proposito |
|-------|---------|-----------|
| `llm_provider` | `"ollama"` | Backend LLM ("ollama" o "anthropic") |
| `ollama_base_url` | `http://localhost:11434` | URL de Ollama local |
| `ollama_model` | `"mistral"` | Modelo a usar en Ollama |
| `anthropic_api_key` | `""` | API key de Anthropic |
| `cache_prices_ttl_seconds` | `300` | TTL de cache de precios |
| `cache_news_ttl_seconds` | `900` | TTL de cache de noticias |
| `cache_max_size` | `128` | Max entradas por cache |
| `cors_origins` | `["*"]` | Origenes CORS permitidos |

### Arrancar el servidor
```bash
uvicorn fina.api.main:app --reload --port 8000
```

---

## 13. Mapa de dependencias entre archivos

### Backend: quien importa a quien

```
core/config.py       ← api/dependencies.py, agent/assistant.py
core/exceptions.py   ← TODOS los modulos de negocio + routes

data/fetcher.py      ← orchestration/*, backtest/engine.py, backtest/montecarlo.py,
                        routes/fundamentals.py
data/cleaner.py      ← orchestration/*, backtest/engine.py

metrics/returns.py   ← orchestration/analysis.py, backtest/montecarlo.py
metrics/volatility.py ← orchestration/analysis.py
metrics/ratios.py    ← orchestration/analysis.py
metrics/technical.py ← orchestration/analysis.py, routes/timeseries.py
metrics/correlation.py ← orchestration/analysis.py

models/arima.py      ← orchestration/models.py
models/garch.py      ← orchestration/models.py
models/hmm.py        ← orchestration/models.py
models/comparator.py ← orchestration/models.py

backtest/signals.py  ← backtest/engine.py, backtest/montecarlo.py
backtest/strategy.py ← backtest/engine.py, backtest/montecarlo.py
backtest/metrics.py  ← backtest/engine.py
backtest/engine.py   ← orchestration/backtest.py
backtest/montecarlo.py ← orchestration/backtest.py

orchestration/analysis.py ← routes/analysis.py
orchestration/models.py   ← routes/models.py
orchestration/backtest.py ← routes/backtest.py

agent/assistant.py   ← routes/agent.py
agent/news.py        ← agent/summarizer.py
agent/summarizer.py  ← routes/agent.py
```

### Frontend: quien depende de quien

```
state.js    → (sin dependencias, define FINA)
charts.js   → state.js (lee FINA.$, FINA.charts, FINA.CHART_COLORS)
panels.js   → state.js + charts.js (usa FINA.render*Chart, FINA.initPinGroup)
api.js      → state.js + charts.js + panels.js (usa FINA.renderOverview, etc.)
backtest.js → state.js (lee FINA.$, FINA.state, FINA.charts)
assistant.js → state.js (lee FINA.$, FINA.state, FINA.fmt*)
```

### Que conecta backend con frontend (endpoints)

| Endpoint | Route file | JS caller | Panel |
|----------|-----------|-----------|-------|
| `POST /analysis/` | analysis.py | api.js | Overview |
| `POST /analysis/timeseries/` | timeseries.py | api.js | Metrics, Technicals |
| `POST /agent/summarize/` | agent.py | api.js | Overview (IA summary) |
| `POST /agent/ask/` | agent.py | assistant.js | Q&A drawer |
| `POST /models/` | models.py | panels.js | Models |
| `POST /models/timeseries/` | models.py | panels.js | Models |
| `POST /models/compare/` | models.py | panels.js | Models |
| `POST /backtest/` | backtest.py | backtest.js | Backtest |
| `POST /backtest/montecarlo/` | backtest.py | backtest.js | Backtest (MC section) |
| `GET /fundamentals/{ticker}` | fundamentals.py | panels.js | Overview |
| `GET /health` | health.py | api.js | Status dot (header) |

### Que conecta el asistente Q&A con el resto

El asistente recibe contexto dinamico del estado actual. Para que el asistente "sepa" algo:

1. **Backend (`assistant.py`):**
   - `_SYSTEM_PROMPT`: Conocimiento estatico sobre FINA (metricas, modelos, backtesting, MC, fundamentales).
   - `_build_context_block(context)`: Parsea el dict de contexto y lo formatea como texto.

2. **Frontend (`assistant.js`):**
   - `gatherContext()`: Lee `state.analysisResult`, `state.modelsResult`, `state.backtestResult`, `state.monteCarloResult`, `state.fundamentalsResult` y arma el dict de contexto.

**Para que el asistente conozca un nuevo dato:**
- Agregar lectura en `gatherContext()` (JS)
- Agregar parseo en `_build_context_block()` (Python)
- Agregar explicacion en `_SYSTEM_PROMPT` (Python)
