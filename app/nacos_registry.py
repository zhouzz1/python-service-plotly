from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class NacosConfig:
    server_addr: str = "192.168.10.187:8848"
    namespace_id: str = ""
    service_name: str = "python-service"
    group_name: str = "DEFAULT_GROUP"
    cluster_name: str = "DEFAULT"
    ip: str = ""
    port: int = 5001
    healthy: bool = True
    enabled: bool = True
    weight: float = 1.0
    ephemeral: bool = True
    metadata: Optional[dict] = None


class NacosRegistrar:
    def __init__(self, cfg: NacosConfig) -> None:
        self.cfg = cfg
        self.cfg.ip = self.cfg.ip or self._detect_local_ip()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _base_url(self) -> str:
        return f"http://{self.cfg.server_addr}".rstrip("/")

    @staticmethod
    def _detect_local_ip() -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            sock.close()

    def _common_params(self) -> dict:
        params = {
            "serviceName": self.cfg.service_name,
            "groupName": self.cfg.group_name,
        }
        if self.cfg.namespace_id:
            params["namespaceId"] = self.cfg.namespace_id
        return params

    def instance_exists(self) -> bool:
        url = f"{self._base_url()}/nacos/v1/ns/instance/list"
        resp = requests.get(url, params=self._common_params(), timeout=5)
        resp.raise_for_status()
        data = resp.json()
        for host in data.get("hosts", []):
            if host.get("ip") == self.cfg.ip and int(host.get("port", 0)) == int(self.cfg.port):
                return True
        return False

    def register(self) -> None:
        if self.instance_exists():
            print(f"[nacos] instance already exists: {self.cfg.ip}:{self.cfg.port}")
            return

        url = f"{self._base_url()}/nacos/v1/ns/instance"
        params = {
            **self._common_params(),
            "ip": self.cfg.ip,
            "port": self.cfg.port,
            "clusterName": self.cfg.cluster_name,
            "healthy": str(self.cfg.healthy).lower(),
            "enabled": str(self.cfg.enabled).lower(),
            "weight": self.cfg.weight,
            "ephemeral": str(self.cfg.ephemeral).lower(),
            "metadata": json.dumps(self.cfg.metadata or {}, ensure_ascii=False),
        }
        resp = requests.post(url, params=params, timeout=5)
        resp.raise_for_status()
        print(f"[nacos] registered instance: {self.cfg.ip}:{self.cfg.port}")

    def deregister(self) -> None:
        url = f"{self._base_url()}/nacos/v1/ns/instance"
        params = {
            **self._common_params(),
            "ip": self.cfg.ip,
            "port": self.cfg.port,
            "clusterName": self.cfg.cluster_name,
            "ephemeral": str(self.cfg.ephemeral).lower(),
        }
        try:
            requests.delete(url, params=params, timeout=5)
            print(f"[nacos] deregistered instance: {self.cfg.ip}:{self.cfg.port}")
        except Exception as exc:
            print(f"[nacos] deregister failed: {exc}")

    def _beat_loop(self) -> None:
        url = f"{self._base_url()}/nacos/v1/ns/instance/beat"
        beat_payload = {
            "ip": self.cfg.ip,
            "port": self.cfg.port,
            "serviceName": self.cfg.service_name,
            "groupName": self.cfg.group_name,
            "cluster": self.cfg.cluster_name,
            "weight": self.cfg.weight,
            "metadata": self.cfg.metadata or {},
            "scheduled": False,
            "period": 5000,
            "stopped": False,
        }

        while not self._stop.is_set():
            params = {
                **self._common_params(),
                "ip": self.cfg.ip,
                "port": self.cfg.port,
                "clusterName": self.cfg.cluster_name,
                "ephemeral": str(self.cfg.ephemeral).lower(),
                "beat": json.dumps(beat_payload, ensure_ascii=False),
            }
            try:
                requests.put(url, params=params, timeout=5)
            except Exception as exc:
                print(f"[nacos] beat failed: {exc}")
            self._stop.wait(5)

    def start(self) -> None:
        self.register()
        if self.cfg.ephemeral:
            self._thread = threading.Thread(target=self._beat_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.deregister()

