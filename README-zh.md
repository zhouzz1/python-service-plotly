# Python 图表报表服务

## 项目简介
本项目是一个用于图表渲染的 Python 微服务，支持与 Java Feign + Nacos 集成。  
主要用于生成直方图拟合图和 AvgBoxChart，服务于报表和 PPT 输出场景。

## 核心功能
- 直方图拟合图渲染（`/common/histfit-image`）
- AvgBoxChart 渲染
  - 静态图（PNG Base64）
  - 交互图（Plotly spec）
- Nacos 服务注册
  - 单命名空间注册
  - 多命名空间目标注册
- 面向 Java Feign 的接口协议

## 技术栈
- Python 3.10+
- FastAPI
- Plotly
- Pydantic
- Nacos
- Uvicorn

## 目录结构
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

## 环境要求
- Python 3.10 及以上
- 可访问 Nacos 服务地址
- 具备 Plotly 图像导出能力（必要时安装 kaleido）

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
APP_PORT=5001
NACOS_SERVICE_NAME=python-service
NACOS_SERVER_ADDR=192.168.xx.xx:8848
NACOS_NAMESPACE=public
NACOS_GROUP=DEFAULT_GROUP
NACOS_CLUSTER=DEFAULT
NACOS_DISCOVERY_IP=192.168.xx.xx
```

多目标注册（可选）：
```bash
NACOS_TARGETS=192.168.xx.xx:8848@public;192.168.xx.xx:8848@public
```

### 3. 启动服务
```bash
python -m app.main
```

或 Windows 一键脚本：
```bat
one_click_restart_check.cmd
```

### 4. 健康检查
```http
GET /common/receive-data
```

预期返回：
```text
"python-service is running"
```

## 接口说明

### POST `/common/histfit-image`
根据请求参数渲染图表：
- 默认：直方图拟合图
- `chartType=avg_box_subplots`：AvgBoxChart 渲染流程

示例请求：
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

示例响应（静态图）：
```json
{
  "status": "success",
  "data": {
    "imageBase64": "iVBORw0KGgoAAA...",
    "mimeType": "image/png"
  }
}
```

示例响应（交互图）：
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

## Java 接入示例
```java
@FeignClient(name = "python-service", path = "/common", configuration = PythonFeignConfig.class)
public interface PythonService {
    @PostMapping("/histfit-image")
    String generateHistogramFitImage(@RequestBody Map<String, Object> payload);
}
```

## Nacos 对齐检查
排查 `Load balancer does not contain an instance for the service python-service` 时，需确保：

1. `server-addr` 一致  
2. `namespace` 一致  
3. `group` 一致  
4. `serviceName` 一致（`python-service`）  
5. Python 实例健康

## 常见问题

### 1) Java 返回 503
通常是服务发现不一致，不是 Python 接口逻辑问题。  
请先核对 Nacos 地址、命名空间、分组、服务名。

### 2) 健康检查可用但 Java 调不到
`/common/receive-data` 只说明进程活着，不代表 Java 一定能通过 Nacos 发现该实例。

### 3) 图显示 No Data
请检查：
- `values` 是否为有效数字
- `chartType` 是否正确
- Python 控制台是否有异常栈

## 部署建议
- 建议“一套包多环境”，通过环境变量切换
- 多命名空间场景建议显式使用 `NACOS_TARGETS`
- 优先走内网访问，不直接暴露公网接口

## 许可证
请根据公司规范填写内部协议或开源许可证。
