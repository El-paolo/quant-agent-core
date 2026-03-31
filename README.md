# FINA — Financial Analysis API

FINA es una plataforma de análisis financiero construida como un paquete Python expuesto vía **FastAPI REST API**. Obtiene precios de mercado, calcula métricas financieras y genera resúmenes con IA usando un modelo de lenguaje local (Ollama).

Soporta renta variable, crypto, FX y ETFs de renta fija.

---

## Requisitos

- Python `3.13.x`
- [`uv`](https://docs.astral.sh/uv/) — gestor de entornos y dependencias
- [Ollama](https://ollama.com) — para el agente de resumen (opcional)

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd fina

# 2. Crear entorno virtual e instalar dependencias
uv sync

# 3. Activar el entorno
source .venv/bin/activate
```

---

## Configuración

Crea un archivo `.env` en la raíz del proyecto. Solo `NEWS_API_KEY` es obligatoria para usar el agente de resumen:

```env
# Proveedor de LLM (default: ollama — sin costo, sin API key)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Requerida para el endpoint /agent/summarize/
NEWS_API_KEY=tu_clave_de_newsapi

# Solo requerida si LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
```

Puedes obtener una clave gratuita de NewsAPI en [newsapi.org](https://newsapi.org).

### Configurar Ollama (para el agente)

```bash
# Instalar Ollama desde https://ollama.com
# Luego descargar el modelo
ollama pull llama3.2:3b

# Verificar que está corriendo
ollama list
```

---

## Levantar la API

```bash
uvicorn fina.api.main:app --reload
```

La API queda disponible en `http://localhost:8000`.

Documentación interactiva (Swagger):
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

---

## Endpoints

### `GET /health`

Verifica que la API está en línea.

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "version": "0.1.0" }
```

---

### `POST /analysis/`

Calcula métricas financieras para un ticker.

**Request:**

```bash
curl -X POST http://localhost:8000/analysis/ \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "period": "1y",
    "metrics": ["returns", "volatility", "sharpe", "rsi", "macd", "bollinger"]
  }'
```

**Parámetros:**

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `ticker` | string | — | Símbolo del activo (ej. `AAPL`, `BTC-USD`, `EURUSD=X`) |
| `period` | string | `"1y"` | Período de datos: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max` |
| `metrics` | list | todas | Métricas a calcular (ver tabla más abajo) |

**Métricas disponibles:**

| Métrica | Descripción |
|---------|-------------|
| `returns` | Retornos logarítmicos (media, std, min, max) |
| `volatility` | Volatilidad realizada anualizada |
| `rolling_volatility` | Volatilidad rolling (ventana 21 días) |
| `sharpe` | Ratio de Sharpe anualizado |
| `sortino` | Ratio de Sortino anualizado |
| `rsi` | RSI (ventana 14 días) |
| `macd` | MACD (12/26/9) con señal e histograma |
| `bollinger` | Bandas de Bollinger (20 días, 2σ) con %B y bandwidth |
| `beta` | Beta vs SPY, alpha, R² y correlación |

**Formatos de ticker:**

| Tipo | Formato | Ejemplo |
|------|---------|---------|
| Renta variable | `SYMBOL` | `AAPL`, `MSFT`, `NVDA` |
| Crypto | `SYMBOL-USD` | `BTC-USD`, `ETH-USD` |
| FX | `PAR=X` | `EURUSD=X`, `USDCLP=X` |
| ETF renta fija | `SYMBOL` | `TLT`, `AGG` |

---

### `POST /agent/summarize/`

Busca noticias recientes y genera un resumen con IA.

Requiere `NEWS_API_KEY` en `.env` y Ollama corriendo localmente.

```bash
curl -X POST http://localhost:8000/agent/summarize/ \
  -H "Content-Type: application/json" \
  -d '{ "ticker": "AAPL" }'
```

Con prompt personalizado:

```bash
curl -X POST http://localhost:8000/agent/summarize/ \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "BTC-USD",
    "summary_prompt": "Enfócate en el sentimiento del mercado y riesgos regulatorios."
  }'
```

**Response:**

```json
{
  "ticker": "AAPL",
  "summary": "Apple reportó resultados sólidos en el último trimestre...",
  "headlines": [
    "Apple beats Q4 earnings expectations",
    "iPhone 16 demand exceeds forecasts"
  ]
}
```

---

## Proveedores de LLM

FINA soporta múltiples proveedores a través de una arquitectura extensible:

| Proveedor | Estado | Configuración |
|-----------|--------|---------------|
| Ollama (local) | Activo | `LLM_PROVIDER=ollama` |
| Anthropic Claude | Fase 2 | Ver `src/fina/agent/providers/anthropic.py` |

Para agregar un nuevo proveedor (OpenAI, Gemini, etc.):
1. Crear `src/fina/agent/providers/<nombre>.py` implementando `LLMProvider`
2. Agregar un `elif` en `summarizer.get_provider()`
3. Agregar los campos de configuración en `core/config.py`

---

## Tests

```bash
# Ejecutar todos los tests
pytest tests/

# Con reporte de cobertura
pytest tests/ --cov=src/fina --cov-report=term-missing

# Solo tests unitarios (rápido)
pytest tests/unit/

# Un módulo específico
pytest tests/unit/test_ratios.py -v
```

Cobertura actual: **96% — 389 tests pasando**.

> Ningún test hace llamadas de red reales. yfinance, Ollama y NewsAPI están siempre mockeados.

---

## Estructura del proyecto

```
fina/
├── src/
│   └── fina/
│       ├── core/
│       │   ├── config.py          # Settings via pydantic-settings + .env
│       │   └── exceptions.py      # Excepciones centralizadas
│       ├── data/
│       │   ├── fetcher.py         # Descarga de precios via yfinance
│       │   └── cleaner.py         # NaN, timezone, detección de outliers
│       ├── metrics/
│       │   ├── returns.py         # Retornos simples y logarítmicos
│       │   ├── volatility.py      # Volatilidad realizada y rolling
│       │   ├── ratios.py          # Sharpe y Sortino
│       │   ├── correlation.py     # Matriz de correlación, rolling corr, beta
│       │   └── technical.py       # RSI, MACD, Bollinger Bands
│       ├── agent/
│       │   ├── providers/
│       │   │   ├── base.py        # LLMProvider Protocol
│       │   │   ├── ollama.py      # Proveedor Ollama (activo)
│       │   │   └── anthropic.py   # Placeholder fase 2
│       │   ├── news.py            # Fetcher de NewsAPI
│       │   └── summarizer.py      # Orquestador de resumen
│       ├── orchestration/
│       │   └── analysis.py        # Pipeline completo: datos → métricas
│       └── api/
│           ├── main.py            # create_app() factory
│           ├── schemas.py         # Modelos Pydantic v2
│           ├── dependencies.py    # Dependencias FastAPI
│           ├── middleware.py      # CORS + X-Process-Time-Ms
│           └── routes/
│               ├── health.py      # GET /health
│               ├── analysis.py    # POST /analysis/
│               └── agent.py       # POST /agent/summarize/
├── tests/
│   ├── conftest.py
│   └── unit/
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Tech Stack

| Capa | Herramienta |
|------|-------------|
| Lenguaje | Python 3.13 |
| Gestor de paquetes | uv |
| API framework | FastAPI + Uvicorn |
| Validación | Pydantic v2 |
| Settings | pydantic-settings |
| Datos de mercado | yfinance |
| Procesamiento | pandas, numpy, scipy |
| LLM local | Ollama (`llama3.2:3b`) |
| Noticias | NewsAPI |
| Tests | pytest + pytest-cov + pytest-httpx |

---

## Notas

- Los precios se asumen ajustados por dividendos y splits salvo indicación explícita.
- Los outliers en precios se detectan pero **no se eliminan** automáticamente — se reportan como advertencias en la respuesta para que el caller decida.
- El ratio de Sortino retorna `null` cuando no hay retornos negativos en el período (mercados alcistas), esto es comportamiento esperado.

## License

All rights reserved.
