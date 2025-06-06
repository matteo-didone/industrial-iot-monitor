# 🏭 Sistema IoT Industriale - Dashboard di Monitoraggio

Un sistema completo end-to-end per il monitoraggio industriale IoT che simula un impianto produttivo con sensori, processamento eventi in tempo reale e dashboard web interattiva.

## 📋 Panoramica

Il sistema simula un impianto produttivo con 4 macchine (Saw1, Milling1, Milling2, Lathe1) che processano pezzi seguendo percorsi di lavorazione definiti.

### 🎯 Caratteristiche Principali

- **Simulazione Realistica**: Modelli termici, usura utensili, dati sensori variabili
- **Elaborazione Parallela**: Multiple macchine attive simultaneamente
- **Dashboard Interattiva**: Visualizzazione in tempo reale con grafici e KPI
- **Architettura Scalabile**: MQTT + InfluxDB + FastAPI + WebSocket
- **Containerizzata**: Docker Compose per deployment facile

## 🏗️ Architettura

```
Simulatore → MQTT Broker → Event Processor → InfluxDB → Dashboard
    ↓             ↓              ↓            ↓         ↓
Edge Device   Mosquitto    Python Service  Time-Series  FastAPI
```

### Componenti Principali

1. **🤖 Simulatore** (`simulator/`)
   - Simula sensori di 4 macchine industriali
   - Genera eventi di tracking (setup, processing, movimento)
   - Modelli realistici: termico, usura utensili, vibrazioni

2. **📡 MQTT Broker** (`mosquitto/`)
   - Eclipse Mosquitto per messaging real-time
   - Topics: `/plant/data/{machine}` e `/plant/tracking/{entity}`

3. **⚙️ Event Processor** (`processor/`)
   - Sottoscrive ai topic MQTT
   - Elabora e filtra messaggi
   - Persiste dati in InfluxDB

4. **💾 InfluxDB**
   - Database time-series per dati sensori
   - Schema ottimizzato per query temporali

5. **📊 Dashboard** (`dashboard/`)
   - FastAPI + WebSocket per aggiornamenti real-time
   - Interfaccia web moderna con Chart.js
   - KPI, grafici, stato macchine, eventi

## 🚀 Quick Start

### Prerequisiti

- Docker & Docker Compose
- Git

### Installazione

1. **Clona il repository**
   ```bash
   git clone https://github.com/matteo-didone/industrial-iot-monitor
   cd industrial-iot-monitor
   ```

2. **Configura variabili d'ambiente**
   ```bash
   cp .env.example .env
   # Modifica .env con le tue configurazioni
   ```

3. **Avvia il sistema**
   ```bash
   docker-compose up -d
   ```

4. **Verifica i servizi**
   ```bash
   docker-compose ps
   ```

5. **Accedi alla dashboard**
   ```
   http://localhost:8080
   ```

### Variabili d'Ambiente (.env)

```bash
# InfluxDB Configuration
INFLUX_USERNAME=admin
INFLUX_PASSWORD=password123
INFLUX_ORG=industrial-iot
INFLUX_BUCKET=sensor-data
INFLUX_TOKEN=your-super-secret-token

# Simulator Configuration
TIME_MULTIPLIER=10.0    # Velocità simulazione (10x = 10 volte più veloce)
PIECE_COUNT=20          # Numero pezzi da processare
```

## 📁 Struttura del Progetto

```
📦 iot-industrial-monitor/
├── 🤖 simulator/              # Simulatore impianto industriale
│   ├── simulator.py           # Logic principale simulazione
│   ├── requirements.txt       # Dipendenze Python
│   └── Dockerfile            # Container simulatore
├── ⚙️ processor/              # Event processor MQTT→InfluxDB
│   ├── main.py               # Logic elaborazione eventi
│   ├── requirements.txt      # Dipendenze Python
│   └── Dockerfile           # Container processor
├── 📊 dashboard/             # Dashboard web FastAPI
│   ├── main.py              # Server FastAPI + WebSocket
│   ├── requirements.txt     # Dipendenze Python
│   ├── Dockerfile          # Container dashboard
│   └── static/             # Frontend web
│       ├── index.html      # Interfaccia principale
│       ├── js/
│       │   ├── main.js     # Logic dashboard
│       │   └── charts.js   # Gestione grafici
│       └── css/
│           └── style.css   # Stili aggiuntivi
├── 📡 mosquitto/            # Configurazione MQTT
│   └── config/
│       └── mosquitto.conf  # Config broker MQTT
├── 🐳 docker-compose.yml    # Orchestrazione servizi
├── 📄 .env.example         # Template variabili ambiente
└── 📖 README.md           # Questa documentazione
```

## 🔧 Funzionalità Dettagliate

### Simulatore di Impianto

Il simulatore crea un ambiente realistico con:

#### Macchine Simulate
- **Saw1**: Sega industriale (blade_speed, material_feed)
- **Milling1/2**: Fresatrici (rpm_spindle, feed_rate, vibration_level)
- **Lathe1**: Tornio (rpm_spindle, cut_depth)

#### Modelli Fisici
- **Modello Termico**: Riscaldamento/raffreddamento realistico
- **Usura Utensili**: Degradazione progressiva con impact su vibrazioni
- **Trasporto Pezzi**: Tempi di movimento tra stazioni

#### Dati Generati
```json
{
  "entity": "Milling1",
  "data": {
    "temperature": 45.2,
    "power": 12.8,
    "rpm_spindle": 2850,
    "feed_rate": 285,
    "vibration_level": 1.8
  },
  "timestamp": "2025-06-05T10:30:45"
}
```

### Event Processor

Elabora eventi MQTT e li persiste in InfluxDB:

#### Tipi di Dati
1. **Sensor Data** → Measurement `sensor_data`
2. **Tracking Events** → Measurement `tracking_events`

#### Elaborazioni
- Filtraggio dati non validi
- Normalizzazione timestamp
- Arricchimento con metadati (tipo macchina, etc.)

### Dashboard Web

#### KPI Principali
- 🏭 **Macchine Attive**: Conteggio real-time
- ⚡ **Potenza Totale**: Somma consumo energetico
- 🌡️ **Temperatura Media**: Con soglie di allarme
- 📊 **Eventi Recenti**: Conteggio attività

#### Grafici Real-time
- **Temperature Trends**: Andamento termico per macchina
- **Power Consumption**: Monitoraggio energetico

#### Monitoraggio Macchine
- Status real-time (🟢 Active, 🟡 Warning, 🔴 Critical, ⚫ Offline)
- Metriche chiave per ogni macchina
- Storico eventi e setup utensili

#### Eventi e Tracking
- Tabella eventi recenti
- Tracciamento movimentazione pezzi
- Setup e cambio utensili

## 🛠️ Sviluppo e Personalizzazione

### Aggiungere Nuove Macchine

1. **Nel Simulatore** (`simulator.py`):
   ```python
   machines = {
       "Saw1": Machine("Saw1", "Saw", mqtt_client),
       "NewMachine": Machine("NewMachine", "CustomType", mqtt_client),
       # ...
   }
   ```

2. **Nel Dashboard** (`main.py`):
   ```python
   def get_machine_status():
       machines = ['Saw1', 'Milling1', 'Milling2', 'Lathe1', 'NewMachine']
       # ...
   ```

### Personalizzare Sensori

Nel file `simulator.py`, metodo `simulate_variable_data()`:

```python
def simulate_variable_data(self, dt: float) -> dict[str, float]:
    # Aggiungi nuovi sensori qui
    if self.type == "CustomType":
        return {
            "custom_sensor": self._apply_jitter(base_value, spread),
            "another_metric": calculated_value
        }
```

### Modificare Dashboard

I file frontend sono in `dashboard/static/`:
- **HTML**: `index.html` - Struttura pagina
- **JavaScript**: `js/main.js`, `js/charts.js` - Logic e grafici
- **CSS**: `css/style.css` - Stili personalizzati

## 📊 API Endpoints

### REST API

| Endpoint | Metodo | Descrizione |
|----------|---------|-------------|
| `/` | GET | Dashboard principale |
| `/health` | GET | Stato sistema |
| `/api/machines` | GET | Lista macchine e status |
| `/api/sensors/{machine}` | GET | Dati sensori macchina |
| `/api/events` | GET | Eventi tracking |
| `/api/overview` | GET | Panoramica KPI |

### WebSocket

- **Endpoint**: `/ws`
- **Messaggi**: Aggiornamenti real-time ogni 5 secondi
- **Formato**:
  ```json
  {
    "type": "live_update",
    "timestamp": "2025-06-05T10:30:45",
    "machines": {...},
    "recent_events": [...]
  }
  ```

## 🔍 Monitoraggio e Debug

### Log dei Servizi

```bash
# Tutti i servizi
docker-compose logs -f

# Servizio specifico
docker-compose logs -f simulator
docker-compose logs -f processor
docker-compose logs -f dashboard
```

### Accesso InfluxDB

```bash
# Web UI InfluxDB
http://localhost:8086

# CLI
docker exec -it iot-influxdb influx
```

### MQTT Debug

```bash
# Sottoscrivi a tutti i topic
docker exec -it iot-mosquitto mosquitto_sub -t "#" -v

# Pubblica messaggio test
docker exec -it iot-mosquitto mosquitto_pub -t "/test" -m "hello"
```

## 🚨 Troubleshooting

### Problemi Comuni

#### Dashboard non si carica
```bash
# Verifica stato servizi
docker-compose ps

# Riavvia dashboard
docker-compose restart dashboard
```

#### Dati non arrivano
```bash
# Verifica MQTT
docker-compose logs mosquitto

# Verifica processor
docker-compose logs processor

# Test connettività
docker exec -it iot-processor ping mosquitto
```

#### InfluxDB non connette
```bash
# Verifica inizializzazione
docker-compose logs influxdb

# Reset completo (⚠️ cancella dati)
docker-compose down -v
docker-compose up -d
```

## 🔧 Configurazioni Avanzate

### Performance Tuning

**Simulatore più veloce**:
```bash
# Nel .env
TIME_MULTIPLIER=50.0  # 50x più veloce
```

**Più pezzi simultanei**:
```python
# In simulator.py
with ThreadPoolExecutor(max_workers=8) as executor:
```

**Dashboard refresh più frequente**:
```python
# In dashboard/main.py
await asyncio.sleep(2)  # Invece di 5 secondi
```

### Sicurezza

**MQTT con autenticazione**:
```bash
# In mosquitto.conf
allow_anonymous false
password_file /mosquitto/config/passwd
```

**InfluxDB token personalizzato**:
```bash
# Genera nuovo token
INFLUX_TOKEN=$(openssl rand -hex 32)
```

## 📈 Estensioni Possibili

### Machine Learning
- Predizione guasti basata su dati sensori
- Anomaly detection su pattern operativi
- Manutenzione predittiva

### Scalabilità
- Cluster InfluxDB per volumi maggiori
- Load balancer per dashboard multiple
- Kafka per stream processing avanzato

### Integrazione Enterprise
- Connessione ERP/MES esistenti
- API per sistemi esterni
- Export dati per analytics

### 🎉 Demo Live

Per vedere il sistema in azione:

1. Avvia con `docker-compose up -d`
2. Apri `http://localhost:8080`
3. Osserva le 4 macchine lavorare in parallelo
4. Monitora temperature, potenza e eventi in tempo reale
5. Clicca su una macchina per vedere dettagli storici
