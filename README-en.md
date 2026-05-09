# Python Service Plotly Report

## Overview
This project is a Python microservice for chart rendering, designed to integrate with Java Feign + Nacos.  
It is mainly used to generate histogram-fit charts and AvgBoxChart outputs for reporting and PPT workflows.

## Key Features
- Histogram/Fit rendering (`/common/histfit-image`)
- AvgBoxChart rendering
  - Static PNG Base64
  - Interactive Plotly spec
- Nacos service registration
  - Single namespace
  - Multi-target namespace registration
- Java Feign-friendly API contract

## Tech Stack
- Python 3.10+
- FastAPI
- Plotly
- Pydantic
- Nacos
- Uvicorn

## Project Structure
```text
python-service-plotly/
├─ app/
│  ├─ main.py
│  ├─ histfit_minitab.py
│  ├─ nacos_registry.py
│  └─ ...
├─ requirements.txt
├─ run.ps1
├─ one_click_restart_check.cmd
└─ check.cmd
```

## Prerequisites
- Python 3.10+
- Network access to Nacos server
- Plotly image export capability (install kaleido if required)

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment variables
```bash
APP_PORT=5001
NACOS_SERVICE_NAME=python-service
NACOS_SERVER_ADDR=192.168.xx.xx:8848
NACOS_NAMESPACE=public
NACOS_GROUP=DEFAULT_GROUP
NACOS_CLUSTER=DEFAULT
NACOS_DISCOVERY_IP=192.168.xx.xx
```

Optional multi-target registration:
```bash
NACOS_TARGETS=192.168.xx.xx:8848@public;192.168.xx.xx:8848@public
```

### 3. Run service
```bash
python -m app.main
```

Or use Windows helper script:
```bat
one_click_restart_check.cmd
```

### 4. Health check
```http
GET /common/receive-data
```

Expected:
```text
"python-service is running"
```

## API

### POST `/common/histfit-image`
Render chart based on request payload:
- Default: histogram/fit rendering
- `chartType=avg_box_subplots`: AvgBoxChart rendering flow

Sample request:
```json
{
  "chartType": "histfit",
  "title": "aaa",
  "values": [1.993, 1.993, 1.993],
  "lsl": 1.9,
  "usl": 2.1,
  "showSpecLine": true,
  "histogramfitr": "7",
  "histogramfit": ["10", "11"],
  "width": 1150,
  "height": 700
}
```

Sample response (static image):
```json
{
  "status": "success",
  "data": {
    "imageBase64": "iVBORw0KGgoAAA...",
    "mimeType": "image/png"
  }
}
```

Sample response (interactive):
```json
{
  "status": "success",
  "data": {
    "renderer": "plotly",
    "spec": {
      "data": [],
      "layout": {},
      "config": {
        "responsive": true,
        "displaylogo": false
      }
    }
  }
}
```

## Java Integration Example
```java
@FeignClient(name = "python-service", path = "/common", configuration = PythonFeignConfig.class)
public interface PythonService {
    @PostMapping("/histfit-image")
    String generateHistogramFitImage(@RequestBody Map<String, Object> payload);
}
```

## Nacos Alignment Checklist
To avoid:
`Load balancer does not contain an instance for the service python-service`

Make sure:
1. Same `server-addr`
2. Same `namespace`
3. Same `group`
4. Same `serviceName` (`python-service`)
5. Python instance is healthy in Nacos

## Troubleshooting

### 1) Java returns 503
Usually caused by service-discovery mismatch, not Python business logic.

### 2) Health endpoint is OK but Java cannot call
`/common/receive-data` only proves process availability, not discovery alignment.

### 3) Chart shows No Data
Check:
- numeric validity of `values`
- `chartType`
- Python runtime stack trace logs

## Deployment Notes
- Prefer one artifact for multiple environments
- Drive environment via runtime variables
- Prefer explicit `NACOS_TARGETS` in multi-namespace deployments
- Keep the service internal (intranet/gateway controlled)

## License
Add your internal or open-source license here.
