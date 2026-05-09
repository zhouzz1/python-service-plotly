param(
  [string]$ServiceName = 'python-service',
  [string]$NacosServer = '192.168.xx.xx:8848'
)

$url = "http://$NacosServer/nacos/v1/ns/instance/list?serviceName=$ServiceName"
$content = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8).Content
Write-Output $content

