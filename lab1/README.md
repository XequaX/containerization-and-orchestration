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

Запуск оболочки в нескольких namespace:

```bash
unshare --user --map-root-user --mount --net --uts --ipc --pid --fork --mount-proc sh
```


## 6. cgroups

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

При тестировании CPU в `cpu.stat` увеличивались `nr_throttled` и `throttled_usec`, что подтверждает срабатывание ограничения CPU. При тесте памяти процесс был завершён OOM-killerом; в `memory.events` увеличились счётчики `oom` и `oom_kill`. При тесте `pids.max` создание дополнительного процесса завершилось ошибкой `Resource temporarily unavailable`.

## 7. mydocker.sh

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

В ходе сборки размер образа составлял около 249 MB.

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

В проверке контейнер был запущен с `Runtime=runsc` и возвращал HTTP 200. У gVisor в текущем окружении не отображались доступные из контейнера файлы cgroup, а cAdvisor не предоставлял метрику throttling для `mydocker-api-gvisor`.

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

PromQL:

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

Метрики throttling проверялись через `container_cpu_cfs_throttled_periods_total`.


## 14. Скриншоты для отчёта

Рекомендуется приложить сделанные во время работы скриншоты:

1. PID namespace и PID 1.
<img width="1106" height="443" alt="2" src="https://github.com/user-attachments/assets/b7039f5e-9017-4c13-9a82-f4c043731723" />

2. Изоляция network namespace.
<img width="678" height="156" alt="5" src="https://github.com/user-attachments/assets/beadd6bb-79bd-494a-846a-0fc4e8bd4b5c" />

3. Лимиты cgroups.
<img width="865" height="131" alt="8" src="https://github.com/user-attachments/assets/26b3c89d-bc5b-4dfe-9583-3849832a27b2" />

4. CPU throttling (`cpu.stat`).
<img width="1321" height="378" alt="9" src="https://github.com/user-attachments/assets/9dd357e3-7576-4676-812a-cc47a5712854" />

5. OOM при превышении лимита памяти (`memory.events`).
<img width="1347" height="454" alt="10" src="https://github.com/user-attachments/assets/01164923-9232-4cf1-bcfd-d63e382b99c4" />

6. Запуск и проверка `mydocker.sh`.
<img width="1177" height="280" alt="11" src="https://github.com/user-attachments/assets/295e7be1-9bcf-4f0d-9d16-7007bdf3ca82" />

7. Проверка capabilities и запрета системного вызова seccomp.
<img width="1043" height="177" alt="12" src="https://github.com/user-attachments/assets/3fd3558a-379a-4118-9750-7a0722c78ef4" />
<img width="1347" height="195" alt="13" src="https://github.com/user-attachments/assets/91da9af6-e297-4e65-b8cb-6c9c9cb60441" />
<img width="1210" height="79" alt="16" src="https://github.com/user-attachments/assets/cf566128-b0f9-4c2b-ae9d-d80da79e40fe" />

8. Сборка Docker-образа и его размер.
<img width="1340" height="216" alt="15" src="https://github.com/user-attachments/assets/c75096ed-5a9e-401f-a243-8b916b7bcda8" />

9. Итоговый дашборд Grafana с метриками API и контейнера.
<img width="1864" height="982" alt="17" src="https://github.com/user-attachments/assets/f25c97e9-997f-4741-b5e3-796570d574b4" />
