# FlyCraft

FAFB v783 fruit-fly connectome tabanlı persistent LIF simülasyonunu Minecraft'a bağlama projesi.

## Aşama 1–5 durumu

Tamamlanan temel:

- `eonsystemspbc/fly-brain` commit `680b7b3d8d1134bf3cbd289b892cf5d37f097d34` incelendi ve veri sürümü sabitlendi.
- Upstream Brian2 CPU simülasyonu 138,639 neuron ve 15,091,983 bağlantı satırıyla yerelde çalıştırıldı.
- Persistent `BrainRuntime` eklendi; ağ bir kez kuruluyor ve ardışık `step` çağrıları aynı Brian2 state'ini ilerletiyor.
- Stimulation FlyWire root ID kabul ediyor; sonuçlar yeni spike'ları FlyWire ID, Brian2 index ve mutlak simulation time olarak döndürüyor.
- Veri indirirken SHA-256 doğrulaması yapılıyor.
- Codex FAFB v783 metadata için checksum doğrulamalı yerel cache ve sorgu araçları eklendi.
- Modeldeki 138,639 root ID'nin tamamının Codex v783 içindeki 139,255 root ID ile eşleştiği doğrulandı.
- Visual, olfactory, gustatory, mechanosensory ve descending candidate population tanımları metadata filtreleriyle sürümlendi.
- `SensoryState -> NeuronStimulus` encoder'ı population-budget ve laterality kurallarıyla eklendi.
- Descending-neuron firing rate'lerinden `MotorCommand` üreten persistent decoder eklendi.
- Versioned JSON/WebSocket brain service ve Paper 1.21.11 Spider controller plugin'i eklendi.


## Gereksinimler

- Linux
- Python 3.10 veya 3.11
- C++ compiler (Brian2 Cython code generation için)
- `uv`
- Tam model için yeterli RAM; hedef 16 GB sistemde ayrıca ölçüm yapılmalıdır
- Paper 1.21.11 için Java 21 JDK

AMD RX 6700 XT için ilk backend **Brian2 CPU**. Upstream Brian2CUDA, NEST GPU, GeNN ve Brian2GeNN yolları CUDA gerektiriyor. Ayrıntı: [`docs/architecture.md`](docs/architecture.md).

## Başka cihazda hızlı kurulum

Repository büyük FAFB/Codex verilerini, Python virtual environment'ını, Paper
runtime'ını ve build çıktılarını içermez. Yeni Linux cihazda:

```bash
git clone git@github.com:kker4m/fruit-fly-minecraft-clone.git
cd fruit-fly-minecraft-clone

uv sync --extra dev
uv run python scripts/fetch_fly_brain_data.py
uv run python scripts/fetch_flywire_metadata.py
```

İndirme scriptleri beklenen upstream commit ve SHA-256 checksum'larını doğrular.
Ardından iki terminal kullan:

```bash
# Terminal 1
uv run python scripts/run_brain_service.py \
  --data-dir data/fly-brain

# Terminal 2
cd minecraft-plugin
./gradlew runServer
```

Paper ilk açılışta `minecraft-plugin/run/` altında oluşturulur. Minecraft
EULA'sını kabul ettikten sonra lokal/offline test için
`minecraft-plugin/run/server.properties` içinde:

```properties
online-mode=false
enforce-secure-profile=false
server-ip=127.0.0.1
```

değerlerini kullan ve server'ı yeniden başlat. Bu offline-mode ayarı yalnızca
loopback geliştirme server'ı içindir; portu LAN veya internete açma. Minecraft
istemcisinden `127.0.0.1:25565` adresine bağlanıp `/flycraft spawn` çalıştır.

İç ağda Gradle dependency/Paper indirmeleri için lokal proxy gerekiyorsa:

```bash
GRADLE_OPTS="-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=3128 \
-Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=3128" \
./gradlew runServer
```

## Kurulum

```bash
uv sync --extra dev
uv run python scripts/fetch_fly_brain_data.py
uv run python scripts/fetch_flywire_metadata.py
```

İndirilen model dosyaları `data/fly-brain/` altında tutulur ve Git'e eklenmez.

## Closed-loop çalıştırma

Önce persistent Python brain service'i başlat:

```bash
uv run python scripts/run_brain_service.py \
  --data-dir data/fly-brain \
  --host 127.0.0.1 \
  --port 8765
```

Service bütün connectome'u bir kez yükler. `BrainRuntime`, `SensoryEncoder` ve
`MotorDecoder` bağlantılar arasında korunur; her sensory frame aynı simülasyon
state'ini ilerletir.

Paper 1.21.11 plugin JAR'ını üret:

```bash
cd minecraft-plugin
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew build
```

Üretilen `build/libs/flycraft-paper-0.1.0.jar` dosyasını Paper server'ın
`plugins/` dizinine kopyala. Server başladıktan sonra:

```text
/flycraft spawn
/flycraft status
/flycraft remove
```

`spawn` komutu Spider'ın vanilla AI ve awareness özelliklerini kapatır; ground
physics için gravity açık kalır. Plugin her kontrol penceresinde light, en yakın
flower mesafe/açısı, üç block raycast'i, önden temas, damage latch ve water
state toplar; yalnızca bir WebSocket request'ini işlemde tutar. Cevap gecikirse
eski komut uygulanmaz; 750 ms sonra Spider'ın yatay hareketi durdurulur.

Yeni spawn edilen Spider, görünür `FlyCraft • FAFB v783 Neural Spider` isim
etiketini taşır. `diagnostic-logging: true` varsayılanıyla hem Python service hem
Paper konsolu her frame için şunları loglar:

- Minecraft sensory değerleri ve sensory-channel stimulus rate'leri;
- input/output spike ve active-neuron sayıları;
- descending candidate population ve left/right firing rate'leri;
- üretilen `forward`, `yaw`, `escape` komutu;
- Spider'a uygulanan yatay velocity ve brain wall time.

Neural `forward` dead-zone sonrası sıfırsa Paper, varsayılan
`idle-forward-drive: 0.15` ile yavaş bir engineered crawl uygular. Bu hareket
connectome kararı değildir; demo mob'un boş sahnede tamamen donmasını önleyen
açıkça etiketlenmiş gameplay policy'sidir. Logda `idle=true` olarak görünür.
Kapatmak için server config'inde `idle-forward-drive: 0.0` kullan.

Mevcut server config dosyasında alan bulunmasa da default `true` kullanılır.
Kapatmak için `minecraft-plugin/run/plugins/FlyCraft/config.yml` içinde:

```yaml
diagnostic-logging: false
```

Geliştirme server'ı:

```bash
cd minecraft-plugin
./gradlew runServer
```

İlk çalıştırmada `minecraft-plugin/run/eula.txt` içindeki Minecraft EULA
seçimini kullanıcı yapmalıdır. Plugin ayarları server oluşturulduktan sonra
`plugins/FlyCraft/config.yml` altındadır.

Wire sözleşmesi [`protocol/flycraft-v1.schema.json`](protocol/flycraft-v1.schema.json)
ile sürümlenir. Default endpoint yalnızca loopback
`ws://127.0.0.1:8765`'tir; uzaktan erişim için authentication ve TLS eklenmeden
port dış ağa açılmamalıdır.

## FlyWire metadata araçları

Araçlar varsayılan olarak yalnızca Eon modeline dahil edilen root ID'leri döndürür:

```bash
# Hiyerarşik annotation sorgusu
uv run python scripts/search_neurons.py \
  --super-class sensory --class gustatory --sub-class sugar/water

# Canonical primary type veya primary/additional alias inceleme
uv run python scripts/search_neurons.py --primary-type DNp09
uv run python scripts/inspect_cell_type.py DNa02

# Bir neuron'un yerel v783 bağlantıları
uv run python scripts/connectivity.py 720575940627652358 \
  --direction outputs --min-synapses 10

# Sürümlü tanımları root ID manifestine çözümle
uv run python scripts/resolve_populations.py
```

Population tanımları `brain/src/flycraft_brain/connectome/populations.json`
içindedir. Üretilen `data/fly-brain/populations-v783.json` yerel ve Git dışında
tutulur. FlyWire annotation verisi CC-BY-NC 4.0 koşullarına tabidir.

## Sensory encoder

```python
from flycraft_brain import BrainRuntime, SensoryEncoder, SensoryState
from flycraft_brain.connectome import CodexMetadata

metadata = CodexMetadata("data/fly-brain")
encoder = SensoryEncoder(metadata)
brain = BrainRuntime(data_dir="data/fly-brain", seed=783)

state = SensoryState(
    light=12,
    food_distance=4.8,
    food_angle=-0.31,
    obstacle_front=0.7,
    obstacle_left=3.1,
    obstacle_right=2.4,
    touch=False,
    damage=True,
    in_water=False,
)
stimulus = encoder.encode(state)
stimulus.apply(brain)
result = brain.step(50)
```

`NeuronStimulus.rates_hz`, Brian2 optogenetic input rate'idir; fiziksel membrane
current değildir. Her channel sabit bir **aggregate population rate budget**
kullanır ve budget'ı annotation ile çözümlenen neuron'lara dağıtır. Böylece
10,000 neuron'luk bir population her neuron'a maksimum rate uygulamaz.

Laterality kuralları:

- negatif `food_angle`: sol annotation side ağırlığı;
- pozitif `food_angle`: sağ annotation side ağırlığı;
- front obstacle: bilateral looming;
- left/right obstacle: ilgili annotation side ağırlığı.

Annotation `side` gerçek receptive field kalibrasyonu değildir; hemisphere
proxy'sidir. `damage`, ayrı bir nociceptive population bulunamadığı için
mechanosensory proxy kullanır. `in_water` şimdilik stimülasyona çevrilmez ve
`NeuronStimulus.unmapped_inputs` içinde raporlanır.

Gerçek metadata ve full connectome smoke testi:

```bash
uv run python scripts/run_sensory_smoke.py
```

## Motor decoder

```python
from flycraft_brain import MotorDecoder

decoder = MotorDecoder(metadata)
command = decoder.decode(result)

print(command.forward)
print(command.yaw)
print(command.escape)
```

Decoder ardışık `BrainStepResult` pencerelerini 100 ms rolling history içinde
birleştirir ve continuous komutlara exponential smoothing uygular:

- `DNp09/P9` population rate → positive `forward`;
- `MDN` population rate → `forward` değerinden çıkarılan backward drive;
- right-minus-left `DNa01` ve `DNa02` rate farkı → `yaw`;
- `DNp01/Giant Fiber` → ground escape flag'i.

`escape`, Paper actuator katmanında en az `0.8` forward drive uygular; dikey
komut üretilmez. Yaw işaret konvansiyonu Minecraft için pozitif-sağ olarak
tanımlanmıştır; biyolojik heading kalibrasyonu değildir.

Full-connectome optogenetic readout smoke testi:

```bash
uv run python scripts/run_motor_smoke.py
```

Bu smoke test motor population'ları doğrudan aktive eder. Çıktı decoder
kanallarını doğrular; doğal sensory input'un davranış ürettiğini kanıtlamaz.

## Persistent runtime

```python
from flycraft_brain import BrainRuntime

brain = BrainRuntime(data_dir="data/fly-brain", seed=783)
brain.stimulate(
    neuron_ids=[720575940624963786],
    intensity=200.0,  # Hz; upstream optogenetic input abstraction
)
result = brain.step(50)

print(result.spikes)
print(result.simulation_time_ms)
print(result.wall_time_ms)
```

Stimülasyon sonraki `stimulate` çağrısına kadar etkin kalır. Temizlemek için:

```python
brain.stimulate([], intensity=0.0)
```

Tam connectome üzerinde iki ardışık 50 ms pencere:

```bash
uv run python scripts/run_brain_smoke.py
```

İlk `step`, Cython kod üretimi/derlemesini de içerdiği için steady-state adımlardan belirgin biçimde yavaştır.

## Doğrulama

```bash
uv run pytest
uv run python scripts/run_brain_smoke.py
uv run python scripts/run_sensory_smoke.py
uv run python scripts/run_motor_smoke.py
uv run python scripts/smoke_brain_service.py  # service ayrı terminalde açıkken
cd minecraft-plugin && ./gradlew test build
```

Upstream benchmark'i bağımsız olarak yeniden çalıştırmak için upstream repository checkout'unda:

```bash
python main.py --brian2-cpu --t_run 0.1 --n_run 1 --experiment sugar --no_log_file
```

## Bilimsel sınır

Connectome, Codex annotation ve LIF spike propagation biyolojik veri/model
katmanıdır. Population filtreleri annotation ve literatürle desteklenen
**adayları** seçer; Minecraft değişkenlerinin doğal sinek uyaranları olduğunu
kanıtlamaz. `stimulate` optogenetik bir müdahale abstraction'ıdır. Gelecekteki
sinyal ölçekleme ve motor spike readout tasarlanmış mühendislik katmanları
olarak kalacaktır. Spike üretimini “sinek karar verdi” diye yorumlamıyoruz.
