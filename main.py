from __future__ import annotations

import base64
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .histfit_minitab import HistogramFitRequest, render_histfit_response
from .nacos_registry import NacosConfig, NacosRegistrar

app = FastAPI(title="python-service", version="1.2.0")
_registrars: List[NacosRegistrar] = []


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_nacos_targets() -> List[Dict[str, str]]:
    """
    Multi-target format:
      NACOS_TARGETS=192.168.20.91:8848@ezbeta;192.168.20.94:8848@contabeta
    Backward compatible:
      NACOS_SERVER_ADDR + NACOS_NAMESPACE
    """
    raw = (os.getenv("NACOS_TARGETS", "") or "").strip()
    targets: List[Dict[str, str]] = []

    if raw:
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            if "@" in part:
                server, ns = part.split("@", 1)
                targets.append(
                    {
                        "server_addr": server.strip(),
                        "namespace_id": ns.strip(),
                    }
                )
            else:
                targets.append(
                    {
                        "server_addr": part.strip(),
                        "namespace_id": "",
                    }
                )

    if not targets:
        targets.append(
            {
                "server_addr": os.getenv("NACOS_SERVER_ADDR", "192.168.10.187:8848").strip(),
                "namespace_id": os.getenv("NACOS_NAMESPACE", "").strip(),
            }
        )

    return targets


def _percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("empty values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    w = pos - lo
    return sorted_values[lo] * (1.0 - w) + sorted_values[hi] * w


def _five_number_summary(values: List[float]) -> Dict[str, float]:
    arr = sorted(values)
    return {
        "min": arr[0],
        "q1": _percentile(arr, 0.25),
        "median": _percentile(arr, 0.50),
        "q3": _percentile(arr, 0.75),
        "max": arr[-1],
    }


def _normalize_series_to_stats(raw_series: List[Any]) -> List[Dict[str, Any]]:
    """
    Support two payload styles:
    1) {"name": "...", "values": [raw values...]}
    2) {"name": "...", "min":..,"q1":..,"median":..,"q3":..,"max":..}
    """
    out: List[Dict[str, Any]] = []
    for item in raw_series:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name") or f"FILE{len(out) + 1}")
        raw_vals = item.get("values")
        has_values_field = isinstance(raw_vals, list)
        values: List[float] = []
        for v in (raw_vals or []):
            fv = _safe_float(v)
            if fv is not None:
                values.append(fv)

        if values:
            s = _five_number_summary(values)
            out.append(
                {
                    "name": name,
                    "count": len(values),
                    "values": values,
                    "source_has_values_field": has_values_field,
                    "source_values_len": len(raw_vals) if has_values_field else None,
                    **s,
                }
            )
            continue

        mn = _safe_float(item.get("min"))
        q1 = _safe_float(item.get("q1"))
        md = _safe_float(item.get("median"))
        q3 = _safe_float(item.get("q3"))
        mx = _safe_float(item.get("max"))
        if None not in (mn, q1, md, q3, mx):
            out.append({
                "name": name,
                "count": None,
                "values": [],
                "source_has_values_field": has_values_field,
                "source_values_len": len(raw_vals) if has_values_field else None,
                "min": mn,
                "q1": q1,
                "median": md,
                "q3": q3,
                "max": mx,
            })

    return out


def _render_avg_box_chart_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_series = payload.get("series") or []
    title = str(payload.get("title") or "AvgBoxChart")
    lotnoname = str(payload.get("lotno") or "BoxChart")
    width = int(payload.get("width") or 1000)
    height = int(payload.get("height") or 360)
    lsl = _safe_float(payload.get("lsl"))
    usl = _safe_float(payload.get("usl"))
    show_spec_line = bool(payload.get("showSpecLine", True))
    center = _safe_float(payload.get("center"))
    output_mode = str(payload.get("outputMode") or "image").lower()
    label_mode = str(payload.get("labelMode") or "simple").lower()

    series = _normalize_series_to_stats(raw_series)
    if not series:
        raise ValueError("series is empty")

    fig = go.Figure()
    category_labels = [str((it or {}).get("name") or f"FILE{i + 1}") for i, it in enumerate(raw_series) if isinstance(it, dict)]
    added_count = 0
    for s in series:
        # Use Java-provided pointName directly for x-axis label.
        label = str(s.get("name") or "")

        vals: List[float] = []
        for v in (s.get("values") or []):
            fv = _safe_float(v)
            if fv is not None:
                vals.append(float(fv))

        if vals:
            # One box per group with all raw points shown vertically.
            fig.add_trace(
                go.Box(
                    y=vals,
                    name=label,
                    showlegend=False,
                    boxmean=False,
                    boxpoints="all",
                    jitter=0.38,
                    pointpos=0,
                    width=0.62,
                    whiskerwidth=0.6,
                    marker=dict(size=4.2, opacity=0.9, color="rgba(220,38,38,0.95)"),
                    line=dict(width=2.4, color="rgba(37,99,235,1.0)"),
                    fillcolor="rgba(37,99,235,0.45)",
                )
            )
            added_count += 1
            continue

        # If caller explicitly passed an empty values list for this category,
        # keep category label (x-axis) but do not render a fake box from fallback stats.
        if bool(s.get("source_has_values_field")) and (s.get("source_values_len") == 0):
            continue

        # Fallback to precomputed five-number summary if no raw values are present.
        mn = _safe_float(s.get("min"))
        q1 = _safe_float(s.get("q1"))
        md = _safe_float(s.get("median"))
        q3 = _safe_float(s.get("q3"))
        mx = _safe_float(s.get("max"))
        if None in (mn, q1, md, q3, mx):
            continue

        fig.add_trace(
            go.Box(
                x=[label],
                q1=[float(q1)],
                median=[float(md)],
                q3=[float(q3)],
                lowerfence=[float(mn)],
                upperfence=[float(mx)],
                name=label,
                showlegend=False,
                boxpoints=False,
                line=dict(width=1.4, color="#2563eb"),
                fillcolor="rgba(37,99,235,0.22)",
            )
        )
        added_count += 1

    if added_count == 0:
        raise ValueError("no valid box data")

    if show_spec_line:
        if lsl is not None:
            fig.add_hline(
                y=lsl,
                line_dash="dash",
                line_color="red",
                annotation_text=f"LSL: {lsl:.4f}",
                annotation_position="top right",
            )
        if usl is not None:
            fig.add_hline(
                y=usl,
                line_dash="dash",
                line_color="red",
                annotation_text=f"USL: {usl:.4f}",
                annotation_position="top right",
            )
        # center line is only valid when both USL and LSL are present.
        if lsl is not None and usl is not None:
            if center is None:
                center = (lsl + usl) / 2.0
            fig.add_hline(
                y=center,
                line_dash="dot",
                line_color="black",
                annotation_text=f"TGT: {center:.4f}",
                annotation_position="top right",
            )

    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            x=0.5,
            xanchor="center",
            font=dict(color="black", size=24),
        ),
        template="plotly_white",
        width=width,
        height=height,
        boxmode="group",
        xaxis_title="",
        yaxis_title="",
        xaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=category_labels if category_labels else None,
            tickangle=-65,
            ticklabelposition="outside",
            automargin=True,
        ),
        # Keep labels fully visible while staying near bottom.
        yaxis=dict(domain=[0.20, 1.0]),
        margin=dict(l=30, r=20, t=50, b=70),
    )

    # Debug: verify point count and five-number summary per file.
    try:
        brief = [
            {
                "name": s.get("name"),
                "count": s.get("count"),
                "min": s.get("min"),
                "q1": s.get("q1"),
                "median": s.get("median"),
                "q3": s.get("q3"),
                "max": s.get("max"),
            }
            for s in series
        ]
        # print("[avg-box] title=", title, " seriesCount=", len(series), " labelMode=", label_mode, " stats=", brief)
        # print("[avg-box] rawSeriesNames=", [str((it or {}).get("name")) for it in raw_series if isinstance(it, dict)])
    except Exception:
        pass

    if output_mode == "interactive":
        spec = fig.to_plotly_json()
        return {
            "status": "success",
            "message": "avg box chart generated",
            "data": {
                "renderer": "plotly",
                "spec": {
                    "data": spec.get("data", []),
                    "layout": spec.get("layout", {}),
                    "config": {"responsive": True, "displaylogo": False},
                },
                "stats": series,
            },
        }

    image_bytes = fig.to_image(format="png", width=width, height=height, scale=1)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return {
        "status": "success",
        "message": "avg box chart generated",
        "data": {
            "imageBase64": image_b64,
            "mimeType": "image/png",
            "stats": series,
        },
    }
# -----------------------------
# app lifecycle
# -----------------------------
@app.on_event("startup")
def _startup() -> None:
    global _registrars
    _registrars = []
    service_name = os.getenv("NACOS_SERVICE_NAME", "python-service")
    group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    cluster = os.getenv("NACOS_CLUSTER", "DEFAULT")
    port = int(os.getenv("APP_PORT", os.getenv("NACOS_DISCOVERY_PORT", "5001")))
    ip = os.getenv("NACOS_DISCOVERY_IP", "")
    targets = _parse_nacos_targets()

    for t in targets:
        cfg = NacosConfig(
            server_addr=t["server_addr"],
            namespace_id=t["namespace_id"],
            service_name=service_name,
            group_name=group,
            cluster_name=cluster,
            ip=ip,
            port=port,
            metadata={"protocol": "http", "contextPath": "/common"},
        )
        registrar = NacosRegistrar(cfg)
        registrar.start()
        _registrars.append(registrar)
        print(
            f"[nacos] started target={t['server_addr']} namespace={t['namespace_id'] or 'public'} "
            f"service={service_name} instance={cfg.ip}:{cfg.port}"
        )


@app.on_event("shutdown")
def _shutdown() -> None:
    global _registrars
    for registrar in _registrars:
        try:
            registrar.stop()
        except Exception as exc:
            print(f"[nacos] stop failed: {exc}")
    _registrars = []


@app.get("/common/receive-data")
def receive_data() -> str:
    return "python-service is running"

REPORT_DIR = Path(
    os.getenv(
        "REPORT_OUTPUT_DIR",
        str(Path(tempfile.gettempdir()) / "python-service" / "reports"),
    )
)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/common/histfit-image")
def generate_histfit_image(req: Dict[str, Any]) -> Dict[str, Any]:
    try:
        chart_type = str((req or {}).get("chartType") or "histfit").lower()
        if chart_type == "avg_box_subplots":
            return _render_avg_box_chart_response(req)

        histfit_req = HistogramFitRequest(**(req or {}))
        return render_histfit_response(histfit_req)
    except Exception as ex:
        tb = traceback.format_exc()
        print("[histfit-image-error]", str(ex))
        print(tb)
        return {
            "status": "error",
            "message": f"histfit-image failed: {ex}",
            "trace": tb[-4000:],
        }
