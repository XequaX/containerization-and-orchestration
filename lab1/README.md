# Лабораторная работа 1. Свой Docker

## 1. Архитектура

- **FastAPI** — тестовый API с эндпоинтами для проверки доступности, ошибок, задержек, нагрузки и потребления памяти.
- **Namespaces** — изоляция PID, mount, network, UTS, IPC и user.
- **cgroups v2** — ограничение памяти, CPU и количества процессов.
- **Docker** — сборка и запуск контейнера с заданными лимитами.
- **gVisor** — альтернативная среда выполнения контейнера через `runsc`.
- **Prometheus** — сбор метрик API и cAdvisor.
- **Grafana** — визуализация метрик и дашборд.
- **cAdvisor** — сбор метрик контейнеров.
- **seccomp** — демонстрация запрета системного вызова.

## 2. Структура проекта

```text
lab1/
├── app/
│   └── main.py
├── data/
│   └── volume-test.txt
├── prometheus/
│   ├── prometheus.yml
│   └── rules/
│       └── alerts.yml
├── seccomp/
│   ├── deny-getppid.json
│   ├── test_getppid.c
│   └── test_seccomp.c
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── mydocker.sh
└── requirements.txt
```

## 3. Предварительные требования

Используются Ubuntu в WSL2, Docker Engine, Docker Compose, Python и `runsc` (gVisor).

Проверка основных компонентов:

```bash
docker info
docker compose version
runsc --version
```

Перейти в каталог проекта:

```bash
cd ~/labs/lab1
```

## 4. API

Запущенный контейнер API доступен на порту `8001` хоста. Проверка:

```bash
curl -i --max-time 5 http://127.0.0.1:8001/health
```

Ожидаемый результат - HTTP 200 и JSON-ответ `{"status":"ok"}`.

Основные эндпоинты:

- `/health` - проверка доступности API;
- `/eat?mb=N` - выделение и удержание памяти;
- `/burn` - длительная нагрузка на CPU;
- `/fail` - тестовая ошибка HTTP 500;
- `/slow` - искусственная задержка;
- `/load` - создание дополнительной нагрузки;
- `/metrics` - метрики Prometheus.


## 5. Namespaces

Изоляция пространств имён проверялась с помощью `unshare`.

Пример проверки PID и user namespaces:

```bash
unshare --user --map-root-user --pid --fork sh -c \
  'echo "PID inside namespace: $$"; id; readlink /proc/self/ns/user; readlink /proc/self/ns/pid'
```

Внутри PID namespace процесс получает PID 1. В отдельном network namespace изначально виден только интерфейс `lo`; для сетевого взаимодействия его требуется поднять.

Пример запуска оболочки в нескольких namespaces:

```bash
unshare --user --map-root-user --mount --net --uts --ipc --pid --fork --mount-proc sh
```


## 6. cgroups v2

В системе доступны контроллеры `cpu`, `memory` и `pids`. Для тестовой группы применялись следующие ограничения:

| Ресурс | Значение | Назначение |
|---|---:|---|
| Память | 100 MiB (`104857600` байт) | Ограничение потребления памяти |
| CPU | `50000 100000` | До 50% одного CPU |
| Число процессов | 10 | Ограничение количества процессов |
| Swap | 0 байт | Отключение swap для тестовой группы |

Проверка доступных контроллеров:

```bash
cat /sys/fs/cgroup/cgroup.controllers
```

При тестировании CPU в `cpu.stat` увеличивались `nr_throttled` и `throttled_usec`, что подтверждает срабатывание ограничения CPU. При тесте памяти процесс был завершён OOM-механизмом; в `memory.events` увеличились счётчики `oom` и `oom_kill`. При тесте `pids.max` создание дополнительного процесса завершилось ошибкой `Resource temporarily unavailable`.

## 7. Скрипт mydocker.sh

Скрипт `mydocker.sh` запускает API с заданными ограничениями cgroups и использует namespaces для изоляции процесса.


## 8. Capabilities и seccomp

В Docker проверялись возможности Linux capabilities и режим seccomp. При запуске контейнера с `--cap-drop=ALL` эффективные capabilities были обнулены; параметр `--security-opt=no-new-privileges` включал `NoNewPrivs: 1`. Для стандартного Docker-контейнера `Seccomp: 2` показывал активный seccomp-фильтр.

Для отдельной демонстрации создан тест на C с libseccomp, который запрещает системный вызов `getppid`. После установки фильтра прямой вызов системного вызова возвращал `-1` с `errno = 1 (Operation not permitted)`.

Пользовательский профиль seccomp в Docker также пробовался, однако запуск с этим профилем в текущем окружении приводил к ошибке `runc` до старта контейнера. Поэтому успешный результат ограничения syscall демонстрируется отдельным тестом с libseccomp, а не пользовательским Docker-профилем.

## 9. Dockerfile и образ

`Dockerfile` использует многоэтапную сборку: зависимости устанавливаются на стадии `builder`, а приложение копируется в стадию `runtime`. Контейнер запускает приложение от непривилегированного пользователя `appuser`.

Сборка:

```bash
cd ~/labs/lab1
docker build -t mydocker-api:latest .
```

Проверка образа:

```bash
docker images mydocker-api:latest
```

В ходе сборки размер образа составлял около 249 MB на диске (значение может отличаться в зависимости от версии образа и Docker).

## 10. Запуск контейнера с Docker

Пример запуска API с ограничениями ресурсов:

```bash
docker run -d --name mydocker-api-limited \
  -p 8000:8000 \
  --memory=100m \
  --memory-swap=100m \
  --cpus=0.5 \
  --pids-limit=10 \
  mydocker-api:latest
```

Проверка состояния и ограничений:

```bash
docker stats --no-stream mydocker-api-limited
docker inspect mydocker-api-limited \
  --format 'Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}} NanoCpus={{.HostConfig.NanoCpus}} PidsLimit={{.HostConfig.PidsLimit}}'
```

В рамках теста контейнер API отвечал HTTP 200 на `/health`, а `docker stats` показывал потребление памяти и CPU.

## 11. Volumes

Проверялось монтирование каталога хоста в контейнер:

```bash
docker run --rm \
  -v "$HOME/labs/lab1/data:/data" \
  alpine:latest \
  sh -c 'echo "Hello from Docker volume" > /data/volume-test.txt && cat /data/volume-test.txt'
```

Файл появлялся в каталоге `data` на хосте, что подтверждает совместное использование данных через bind mount.

## 12. gVisor

Установлен `runsc` и зарегистрирован в локальном Docker Engine как дополнительная среда выполнения. Проверка версии:

```bash
runsc --version
```

Запуск API под gVisor выполнялся так:

```bash
docker run -d --rm --runtime=runsc \
  --name mydocker-api-gvisor \
  -p 8001:8000 \
  mydocker-api:latest
```

Проверить runtime и доступность API:

```bash
docker inspect mydocker-api-gvisor \
  --format 'Name={{.Name}} Runtime={{.HostConfig.Runtime}}'
curl -i --max-time 5 http://127.0.0.1:8001/health
```

В проверке контейнер был запущен с `Runtime=runsc` и возвращал HTTP 200. У gVisor в текущем окружении не отображались доступные из контейнера файлы cgroup, а cAdvisor не предоставлял метрику throttling для `mydocker-api-gvisor`; это ограничение учитывается при анализе мониторинга.

## 13. Prometheus и Grafana

Стек мониторинга запускается из каталога проекта:

```bash
cd ~/labs/lab1
docker compose up -d
docker compose ps
```

Веб-интерфейсы:

- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000>
- cAdvisor: <http://localhost:8080>

В Grafana настроен источник данных Prometheus с URL `http://prometheus:9090`. Дашборд `MyDocker API Monitoring` содержит метрики API и контейнера: RPS, долю ошибок, p95 latency, потребление памяти, использование CPU и скорость использования процессорного времени.

Примеры PromQL:

RPS:

```promql
sum(rate(api_requests_total[1m]))
```

Доля ошибок:

```promql
sum(rate(api_errors_total[1m]))
/
clamp_min(sum(rate(api_requests_total[1m])), 1e-9)
```

p95 задержки:

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(api_request_duration_seconds_bucket[5m]))
)
```

Память контейнера в MiB:

```promql
container_memory_working_set_bytes{name="mydocker-api-gvisor"} / 1024 / 1024
```

Использование CPU в процентах от одного ядра:

```promql
rate(container_cpu_usage_seconds_total{name="mydocker-api-gvisor"}[1m]) * 100
```

Скорость использования CPU в ядрах:

```promql
rate(container_cpu_usage_seconds_total{name="mydocker-api-gvisor"}[1m])
```

Метрики throttling проверялись через `container_cpu_cfs_throttled_periods_total`. В текущем окружении эта метрика доступна для других контейнеров, но не для `mydocker-api-gvisor`; поэтому её не следует считать работающей панелью для данного контейнера.

## 14. Правила оповещений

Правила находятся в `prometheus/rules/alerts.yml`:

- **HighErrorRate** — доля ошибок API превышает 5% в течение 30 секунд. Помогает обнаружить массовые сбои запросов.
- **HighRequestLatency** — p95 задержки превышает 1 секунду в течение 30 секунд. Помогает обнаружить замедление обслуживания запросов.
- **ApiDown** — Prometheus не может получить метрики API в течение 15 секунд. Позволяет обнаружить недоступность сервиса или сборщика метрик.

Проверить правила и активные оповещения можно в Prometheus:

- <http://localhost:9090/rules>
- <http://localhost:9090/alerts>

Правило `HighErrorRate` проверялось тестовыми запросами к `/fail`. CPU throttling дополнительно подтверждался в тесте cgroups через `cpu.stat`, но отдельное Prometheus-оповещение по throttling для gVisor в текущей конфигурации не настроено.

## 15. Проверка состояния стека

```bash
cd ~/labs/lab1
docker ps -a
docker compose ps
```

Проверить API и метрики:

```bash
curl -i --max-time 5 http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8001/metrics | head
```

## 16. Скриншоты для отчёта

Рекомендуется приложить сделанные во время работы скриншоты:

1. PID namespace и PID 1.
2. Изоляция network namespace.
3. User namespace.
4. Контроллеры и лимиты cgroups.
5. CPU throttling (`cpu.stat`).
6. OOM при превышении лимита памяти (`memory.events`).
7. Ограничение числа процессов (`pids.max`).
8. Запуск и проверка `mydocker.sh`.
9. Проверка capabilities и запрета системного вызова seccomp.
10. Сборка Docker-образа и его размер.
11. Работа API и `docker stats` с лимитами.
12. Проверка volume.
13. Установка и запуск gVisor, подтверждение `Runtime=runsc`.
14. Prometheus targets и правила оповещений.
15. Тест срабатывания `HighErrorRate`.
16. Итоговый дашборд Grafana с метриками API и контейнера.
