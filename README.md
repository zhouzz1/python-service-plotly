# python-service 部署与运维手册

本文档用于在新机器快速部署 `python-service`，并与 `win-tms`（Java）联调。

## 目录结构

服务目录：`如 D:\python-service-plotly`

关键文件：
- `run.ps1`：服务启动脚本（自动找 Python、建 venv、装依赖、启动）
- `start.cmd`：一键启动（当前窗口）
- `start_and_check.cmd`：一键启动 + 自动检查 Nacos 注册
- `one_click_restart_check.cmd`：一键重启（先清理5001旧进程）+ 健康检查 + Nacos检查
- `check.cmd`：仅检查 Nacos 注册
- `app\main.py`：FastAPI 服务
- `app\nacos_registry.py`：Nacos 注册/心跳/反注册逻辑

## 一、首次部署（新机器）

### 1. 安装 Python（推荐 3.11）

管理员 PowerShell 执行：

```powershell
winget install -e --id Python.Python.3.11
```

安装后关闭当前终端，重新打开 PowerShell。

验证：

```powershell
python --version
```

期望看到真实版本号（例如 `Python 3.11.x`），而不是 WindowsApps 占位错误。

### 2. 一键启动并检查注册

```powershell
D:\python-service-plotly\start_and_check.cmd
```

该命令会自动：
- 启动 PowerShell（Bypass 执行策略）
- 执行 `run.ps1`
- 自动创建 `.venv`
- 安装依赖
- 启动服务
- 调用 Nacos 查询实例

## 二、日常启动/停止

### 启动

方式1（推荐）：

```powershell
D:\python-service-plotly\start_and_check.cmd
```

方式1.5（强推荐，排障时使用）：

```powershell
D:\python-service-plotly\one_click_restart_check.cmd
```

方式2（仅启动）：

```powershell
D:\python-service-plotly\start.cmd
```

### 停止

关闭运行服务的 PowerShell 窗口（Ctrl + C 或直接关闭窗口）。

停止时服务会调用反注册逻辑（deregister）。

## 三、注册状态检查

```powershell
D:\python-service-plotly\check.cmd
```

返回示例（成功）：
- `hosts` 数组非空，且包含本机 `ip/port`。

返回示例（失败）：
- `hosts: []`，说明服务未成功注册（或未启动）。

## 四、环境变量（可选）

默认值如下：
- `APP_PORT=5001`
- `NACOS_SERVER_ADDR=192.168.xx.1xx:8848`
- `NACOS_SERVICE_NAME=python-service`
- `NACOS_GROUP=DEFAULT_GROUP`
- `NACOS_NAMESPACE=`（空=public）

如需临时覆盖：

```powershell
$env:APP_PORT='5002'
$env:NACOS_SERVER_ADDR='192.168.xx.xx:8848'
D:\python-service-plotly\start.cmd
```

## 五、与 Java 对接说明

Java Feign 服务名：`python-service`

Java 调用接口：
- `POST /common/generate-report`

Python 返回包含：
- `fileName`
- `fileBase64`

Java 侧会：
- 解析返回
- 保存附件到系统 `Pattachment`
- 回传 `downloadUrl` 给前端下载

## 六、常见问题

### 1) `run.ps1` 被执行策略拦截
使用 `start.cmd` / `start_and_check.cmd`，脚本已内置 `-ExecutionPolicy Bypass`。

### 2) `Activate.ps1` 找不到
本项目 `run.ps1` 已不依赖 `Activate.ps1`，直接调用 `.venv\Scripts\python.exe`。

### 3) `hosts: []`
按顺序排查：
1. `python --version` 是否正常
2. 服务窗口是否仍在运行
3. Nacos 地址是否可达（`192.168.xx.xx:8848`）
4. 防火墙是否阻断（5001 端口）
5. 再执行 `check.cmd`

### 4) 无法联网安装依赖
离线环境请准备内部 PyPI 源，或提前下载 wheel 包后本地安装。

## 七、接口清单（Python）

- `GET /common/receive-data`
- `POST /common/generate-report`
- `GET /common/report-status`
- `POST /common/saveAttachment`


## 八、generate-report 输出说明（更新）

- POST /common/generate-report 现在默认生成 **PPTX**。
- 规则：每个参数（llTestName 中的 N:Name）生成一页 slide。
- 返回字段：data.fileName（.pptx）、data.fileBase64（PPT 文件内容）、contentType 为 pplication/vnd.openxmlformats-officedocument.presentationml.presentation。
- 依赖：python-pptx、kaleido（用于 Plotly 导出 PNG）。

