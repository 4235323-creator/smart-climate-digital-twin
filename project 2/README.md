# Smart Climate Digital Twin — Industrial AI Control Platform (v3)

Платформа расширена промышленными слоями Computer Vision Occupancy Analytics
и Equipment Health Monitoring. Система больше не привязана к
заранее заданному списку ТРЦ Киева. Теперь она принимает **любой объект
мира** — страну, область, город, посёлок, село, улицу, дом, ТРЦ,
бизнес-центр, предприятие, GPS-координаты или геолокацию устройства —
и автоматически прогоняет его через:

```
User → Location Resolver → Geocoding API cascade → lat/lon
     → Timezone / Country / Region (offline enrichment)
     → Weather Providers (cascade)
     → Computer Vision Engine → Occupancy Analytics
     → Mall Analytics Engine → Reports / Tenant Analytics / Forecasts
     → Equipment Health Engine → Failure Prediction / RUL
     → Data Fusion Engine → MPC → HVAC
```

## Структура проекта

```
smart_climate/
├── domain/            # LocationResult, LocationType, BuildingProfile (pydantic)
├── infrastructure/     # общий httpx-клиент, sync↔async мост для Streamlit
├── location/           # Location Intelligence Engine
│   ├── providers/       # Nominatim → Photon → Google → Mapbox → HERE
│   ├── cache.py          # Smart Cache (не гео­кодировать повторно)
│   ├── resolver.py       # LocationResolver (универсальный поиск / GPS / reverse)
│   └── factory.py        # DI composition root
├── weather/            # Weather Data Fusion Engine
│   ├── providers/        # Open-Meteo(ECMWF/GFS) → OpenWeather → Meteostat →
│   │                      # WeatherAPI.com → Tomorrow.io → MET Norway → wttr.in
│   ├── fusion.py         # DataFusionEngine (каскад + календарь + тариф + AQI)
│   └── factory.py        # DI composition root
├── vision/             # Computer Vision Engine
│   ├── models.py         # ICameraProvider, IVisionDetector, ITracker, OccupancyEstimator
│   ├── engine.py         # IP Camera → YOLOv11/RT-DETR → ByteTrack/DeepSORT → Analytics
│   └── factory.py        # DI composition root
├── mall_analytics/     # Mall Analytics Engine
│   ├── models.py         # Footfall, Peak Occupancy, Tenant Reports, PDF jobs
│   ├── engine.py         # Daily reports, forecasts, HVAC impact, recommendations
│   └── factory.py        # DI composition root
├── equipment/          # Equipment Health Engine
│   ├── models.py         # Health Score, Failure Probability, RUL, Maintenance Status
│   ├── engine.py         # Sensors → Signal Processing → Features → ML → Planner
│   └── factory.py        # DI composition root
├── control/            # MpcOptimizer (occupancy-aware + health-aware HVAC MPC)
└── app.py              # Streamlit UI: поиск места, карта, дашборд
main.py                 # `streamlit run main.py`
```

## Новые промышленные модули

### Computer Vision Occupancy Analytics

Архитектура слоя:

```
IP Camera
→ YOLOv11 / RT-DETR
→ Person Detection
→ Person Tracking (ByteTrack / DeepSORT)
→ Occupancy Analytics
→ Heat Map
→ People Counter
→ Crowd Density
→ Data Fusion Engine
→ MPC Controller
```

Слой реализует интерфейсы `ICameraProvider`, `IVisionDetector`, `ITracker`
и `OccupancyEstimator`. Демонстрационный industrial-adapter отдаёт зоны:

- Food Court — 125 человек
- Cinema — 43 человека
- Shops — 382 человека
- Parking — 94 человека

Dashboard показывает плотность, очереди, dwell time, направление потоков,
коэффициент загрузки зоны, heatmap посещаемости и прогноз на 15/30/60 минут.
MPC использует эти данные для автоматического увеличения охлаждения,
вентиляции и притока наружного воздуха при высокой загрузке.

### Mall Analytics Engine

Отдельный коммерческий слой аналитики ТРЦ строит отчеты для администрации,
арендаторов и эксплуатации здания:

- Footfall — общее количество посетителей.
- Peak Occupancy — максимальное число людей одновременно.
- Average Dwell Time — среднее время пребывания.
- Occupancy by Zone — загрузка каждой зоны.
- Visitor Forecast — прогноз на ближайшие часы и дни.
- HVAC Impact — влияние посещаемости на охлаждение, вентиляцию и энергию.
- Energy per Visitor и Cost per Visitor.
- Black Friday Analytics и сравнение с обычным днем.
- Tenant Reports для Fashion Zone, Food Court, Cinema и других зон.
- PDF jobs для ежедневного, недельного, месячного и годового отчетов.

В dashboard добавлена вкладка **Mall Analytics**: KPI отчета за 05.07.2026,
тепловая карта посещаемости, почасовая посещаемость, самые загруженные зоны,
среднее время пребывания, дни недели, прогнозы, tenant report, HVAC impact и
AI-рекомендации.

### Equipment Health Monitoring

Архитектура слоя:

```
Sensors
→ Signal Processing
→ Feature Extraction
→ ML Model
→ Remaining Useful Life
→ Failure Prediction
→ Maintenance Planner
```

Слой принимает температуру компрессора, вибрацию, ток двигателя, напряжение,
давление, расход воздуха, расход воды, часы работы, количество включений и
циклов. На выходе формируются `Health Score`, `Failure Probability`,
`Remaining Useful Life`, `Critical Components`, `Warnings` и
`Maintenance Status`.

Вкладка **Building Health** показывает:

- Chiller 1 — 🟢 98%
- Chiller 2 — 🟡 71% dashboard status, при этом ML-риск отказа 78%
- AHU 3 — 🟢 93%
- Pump 2 — 🔴 42%

При вероятности отказа выше 70% система показывает предупреждение:
`⚠ Chiller 2`, `Failure Probability 78%`, `Estimated Failure 12 days`,
`Recommendation Replace compressor bearings.` При `Health Score < 40` MPC
переводит агрегат в безопасный режим и уменьшает его использование.

## Ключевые принципы

- **Ни одной захардкоженной координаты.** `MALLS = {...}` полностью удалён.
  Всё, что раньше было "3 ТРЦ Киева", теперь — `BuildingProfile`, который
  пользователь настраивает под конкретное здание независимо от локации.
- **Geocoding cascade с автоматическим fallback**: если Nominatim недоступен —
  пробуется Photon, затем Google/Mapbox/HERE (если указаны ключи).
- **Weather cascade** аналогично перебирает провайдеров и **добирает**
  недостающие поля от следующего источника (`WeatherSample.merge_missing_from`).
- **Smart Cache**: повторный поиск того же объекта не géo­кодируется заново
  (TTL-кэш в памяти + опциональная персистентность на диск).
- **SOLID / DI**: `LocationResolver` и `DataFusionEngine` зависят только от
  абстракций (`GeocodingProvider`, `WeatherProvider`); конкретные провайдеры
  собираются в `factory.py` (composition root).
- **Clean Architecture / DDD**: vision, equipment, weather, location и control
  разделены по bounded context; MPC получает только доменные snapshots.
- **Repository / Factory Pattern**: telemetry и камеры подключаются через
  интерфейсы и composition roots, без привязки UI к конкретной реализации.
- **AsyncIO**: все сетевые вызовы — через `httpx.AsyncClient`; для Streamlit
  добавлен безопасный мост `run_async()`.

## Установка и запуск

```bash
pip install -r requirements.txt
streamlit run main.py
```

Провайдеры без ключа (Nominatim, Photon, Open-Meteo, MET Norway, wttr.in,
RainViewer) работают из коробки. Ключи для Google/Mapbox/HERE и
OpenWeather/Meteostat/WeatherAPI.com/Tomorrow.io/IQAir вводятся прямо в
сайдбаре приложения — без них соответствующий провайдер просто
пропускается в каскаде.

## Геолокация устройства

Кнопка **«📡 Моя геолокация»** использует пакет `streamlit-js-eval`
(`navigator.geolocation` браузера) → `LocationResolver.resolve_by_gps()`.
