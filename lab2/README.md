# Лабораторная работа 2. Мониторинг сервиса

## 1. Архитектура

-   **API (FastAPI)** - тестовый сервис с эндпоинтами `/health`,
    `/fail`, `/slow`, `/load` и `/metrics`.
-   **Prometheus** - сбор и хранение метрик.
-   **Grafana** - визуализация метрик и просмотр логов.
-   **Loki** - хранение логов.
-   **Grafana Alloy** - сбор логов Kubernetes и отправка в Loki.
-   **Jaeger** - просмотр распределённых трасс, передаваемых через
    OpenTelemetry.
-   **Alertmanager** - обработка оповещений Prometheus.
-   **Karma** - веб-интерфейс для просмотра оповещений Alertmanager.

## 2. Структура проекта

``` text
.
├── Dockerfile
├── app/
│   ├── main.py
│   └── requirements.txt
├── helm/
│   └── api/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
├── prometheus/
│   └── values.yaml
├── loki/
│   └── values.yaml
├── alloy/
│   └── values.yaml
├── jaeger/
│   └── values.yaml
├── karma/
│   └── values.yaml
└── k8s/
    └── alert-rules.yaml
```

## 3. Предварительные требования

Установлены команды `docker`, `kubectl` и `helm`. Docker
должен быть запущен, а пользователь WSL должен иметь возможность
обращаться к Docker Engine.

Проверка:

``` bash
docker info
kubectl version --client
helm version
```

## 4. Запуск и проверка Kubernetes

Перейти в каталог проекта:

``` bash
cd ~/monitoring-lab-2
```

Проверить кластер и неймспейс:

``` bash
kind get clusters
kubectl get nodes
kubectl get pods -n monitoring
```

## 5. API

Проверить состояние сервиса и поды:

``` bash
kubectl get pods -n monitoring | grep api
kubectl get svc -n monitoring api
```

Пробросить порт:

``` bash
kubectl port-forward -n monitoring service/api 8000:8000
```

В другом терминале проверить эндпоинты:

``` bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/slow
curl -i http://localhost:8000/fail
curl -i http://localhost:8000/metrics
```

Ожидаемое поведение: - `/health` возвращает HTTP 200; - `/slow`
возвращает HTTP 200 с искусственной задержкой; - `/fail` намеренно
возвращает HTTP 500; - `/metrics` выдаёт метрики Prometheus; - `/load` создаёт дополнительную нагрузку на API.

## 6. Prometheus и Grafana

Проверить под:

``` bash
kubectl get pods -n monitoring | grep -E 'prometheus|grafana'
```

Открыть Grafana:

``` bash
kubectl port-forward -n monitoring service/monitoring-grafana 3000:80
```

Перейти на <http://localhost:3000>. Использовать учётные данные,
заданные в `prometheus/values.yaml`.

RED-дашборд содержит: - **RPS** - число запросов в секунду; - **Error
rate** - долю ошибок; - **p95 latency** - 95-й перцентиль времени
ответа; - **Total requests** - общее количество запросов.

Запросы PromQL:

``` promql
sum(rate(api_requests_total[1m]))
```

``` promql
sum(rate(api_requests_total{status=~"5.."}[5m]))
/
clamp_min(sum(rate(api_requests_total[5m])), 1e-9)
```

``` promql
histogram_quantile(
  0.95,
  sum by (le) (rate(api_request_duration_seconds_bucket[5m]))
)
```

``` promql
sum(api_requests_total)
```

Пробросить порт для Prometheus:

``` bash
kubectl port-forward -n monitoring service/monitoring-kube-prometheus-prometheus 9090:9090
```

Перейти на <http://localhost:9090>.

## 7. Логи Loki, Alloy и Grafana

Проверить компоненты:

``` bash
kubectl get pods -n monitoring | grep -E 'loki|alloy'
```

В Grafana открыть **Explore** и выбрать источник данных `Loki`.

Запрос для просмотра логов API:

``` logql
{namespace="monitoring", pod=~"api-.*"}
```

Запрос для поиска тестовых ошибок:

``` logql
{namespace="monitoring", pod=~"api-.*"} |= "Intentional test error"
```

## 8. OpenTelemetry и Jaeger

Проверить состояние Jaeger:

``` bash
kubectl get pods,svc -n monitoring | grep jaeger
```

Пробросить порт для Jaeger:

``` bash
kubectl port-forward -n monitoring service/jaeger 16686:16686
```

Перейти на <http://localhost:16686>.

Для создания тестовых трейсов отправить запросы:

``` bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/slow
curl -i http://localhost:8000/fail
```

В Jaeger выбрать сервис `api`, указать подходящий временной диапазон и
нажать **Find Traces**. Открыть трейс, чтобы посмотрет спаны.

## 9. PrometheusRule и Alertmanager

Пользовательские правила находятся в `k8s/alert-rules.yaml`. Проверить
их наличие:

``` bash
kubectl get prometheusrules -n monitoring
kubectl get prometheusrule api-alert-rules -n monitoring
```

В проекте определены правила: - `HighErrorRate` - доля HTTP 5xx
превышает 5%; - `HighRequestLatency` - p95 задержки превышает 1
секунду; - `ApiDown` - метрики API недоступны для Prometheus.

Проверить правила в Prometheus: <http://localhost:9090/rules> и активные
оповещения: <http://localhost:9090/alerts>.

Проброс порта для Alertmanager:

``` bash
kubectl port-forward -n monitoring service/monitoring-kube-prometheus-alertmanager 9093:9093
```

Перейти на <http://localhost:9093>.

## 10. Karma

Проверить состояние Karma:

``` bash
kubectl get pods,svc -n monitoring | grep karma
```

Проброс порта:

``` bash
kubectl port-forward -n monitoring service/karma 8080:80
```

Перейти на <http://localhost:8080>. В интерфейсе отображаются
оповещения, полученные из Alertmanager.

## 11. Проверка состояния всего стека

``` bash
kubectl get pods -n monitoring
kubectl get svc -n monitoring
kubectl get prometheusrules -n monitoring
```

## 12. Скриншоты

Рекомендуется приложить следующие скриншоты:

1.  **Kubernetes**
<img width="865" height="269" alt="Kuber" src="https://github.com/user-attachments/assets/6546fd21-8338-4b4b-8474-bcbbe94326f8" />

2.  **Grafana RED dashboard**
<img width="1912" height="1028" alt="RED_Grafana" src="https://github.com/user-attachments/assets/eaaa9749-e7bc-459c-8f04-4dacf72a0065" />

3.  **Loki в Grafana Explore**
<img width="1916" height="1028" alt="loki_logs" src="https://github.com/user-attachments/assets/c37df20c-75ae-4dec-b049-28681a1e9be2" />

4.  **Jaeger**
<img width="1916" height="1028" alt="jaeger" src="https://github.com/user-attachments/assets/a300acb3-76fa-4cb2-bfdd-9bcdbdfff428" />
<img width="1865" height="985" alt="Jaeger_slow" src="https://github.com/user-attachments/assets/72f50efb-35c6-4a9e-824f-09dbba2fde3e" />
<img width="1865" height="990" alt="Jaeger_fail" src="https://github.com/user-attachments/assets/37711f61-b3e1-4b25-8b38-380afb0af615" />


5.  **Prometheus Rules**
<img width="1917" height="1028" alt="api_alerts_prometheus" src="https://github.com/user-attachments/assets/6519feae-a32f-408b-bab6-e0eff911afe8" />

6. **Alertmanager**
<img width="1863" height="993" alt="alertmanager" src="https://github.com/user-attachments/assets/f40639f5-7c73-4631-af58-b12578ad496c" />

7.  **Karma**
<img width="1917" height="1028" alt="karma" src="https://github.com/user-attachments/assets/743deb3b-2f2c-412b-a3d8-1f89a8e687af" />

