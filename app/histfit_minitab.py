from __future__ import annotations

import base64
import math
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

import plotly.graph_objects as go
from pydantic import BaseModel, Field


class HistogramFitRequest(BaseModel):
    values: List[Any] = Field(default_factory=list)
    title: str = ""
    lsl: Optional[float] = None
    usl: Optional[float] = None
    histogramfitr: Optional[str] = "7"
    histogramfit: List[str] = Field(default_factory=list)
    binwidths: Optional[int] = None
    editFitTitle: Optional[str] = None
    showSpecLine: Optional[bool] = True
    width: int = 1150
    height: int = 700


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None


def _clean_values(values: Sequence[Any]) -> List[float]:
    out: List[float] = []
    for v in values:
        fv = _safe_float(v)
        if fv is not None:
            out.append(fv)
    return out


def _downsample(values: Sequence[float], max_points: int = 120_000) -> List[float]:
    n = len(values)
    if n <= max_points:
        return list(values)
    step = n / float(max_points)
    out: List[float] = []
    idx = 0.0
    for _ in range(max_points):
        out.append(values[int(idx)])
        idx += step
    return out


def _nice_number(x: float) -> float:
    if x == 0:
        return 0.0
    exp = math.floor(math.log10(abs(x)))
    f = x / (10**exp)
    if f < 1.5:
        nice_f = 1.0
    elif f < 3.0:
        nice_f = 2.0
    elif f < 7.0:
        nice_f = 5.0
    else:
        nice_f = 10.0
    return nice_f * (10**exp)


def _x_tick_format(xmin: float, xmax: float) -> str:
    span = abs(xmax - xmin)
    if span < 1:
        return ".3f"
    if span < 10:
        return ".2f"
    if span < 100:
        return ".1f"
    return ".0f"


def _auto_min_nice_bin_width(data: Sequence[float]) -> float:
    if len(data) <= 1:
        return 1e-3
    uniq = sorted(set(data))
    if len(uniq) <= 1:
        return 1e-3
    min_diff = float("inf")
    for i in range(1, len(uniq)):
        d = uniq[i] - uniq[i - 1]
        if d > 0 and d < min_diff:
            min_diff = d
    if min_diff == float("inf") or min_diff <= 0:
        min_diff = 1e-3
    return max(_nice_number(min_diff), 1e-6)


def _calculate_minitab_bins(data: Sequence[float]) -> Tuple[int, float]:
    if not data:
        return 1, 1.0
    dmin = min(data)
    dmax = max(data)
    if dmin == dmax:
        return 1, 1.0
    n = len(data)
    lower = int(round((16.0 * n) ** (1.0 / 3.0) + 0.5))
    lower = max(lower, 2)
    upper = lower + int(round(0.5 * lower))
    raw_w = (dmax - dmin) / lower
    nice_w = _nice_number(raw_w)
    if nice_w <= 0:
        nice_w = raw_w if raw_w > 0 else 1.0
    start = math.floor(dmin / nice_w) * nice_w
    num_bins = int(math.ceil((dmax - start) / nice_w))
    num_bins = max(lower, min(upper, max(num_bins, 1)))
    return num_bins, nice_w


def _norm_pdf(x: float, mu: float, sigma: float) -> float:
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _fmt_stat(v: float, digits: int = 6) -> str:
    txt = f"{v:.{digits}f}"
    txt = txt.rstrip("0").rstrip(".")
    if txt == "-0":
        return "0"
    return txt


def _histogram_counts(data: Sequence[float], start: float, bin_w: float, bins: int) -> List[int]:
    counts = [0] * bins
    if bins <= 0 or bin_w <= 0:
        return counts
    for v in data:
        idx = int((v - start) / bin_w)
        if idx < 0:
            idx = 0
        elif idx >= bins:
            idx = bins - 1
        counts[idx] += 1
    return counts


def render_histfit_png_base64(req: HistogramFitRequest) -> str:
    data = _downsample(_clean_values(req.values))
    if not data:
        raise ValueError("values is empty")

    dmin = min(data)
    dmax = max(data)
    n = len(data)
    title = req.editFitTitle.strip() if req.editFitTitle else req.title or "HistogramFit"

    mu = mean(data)
    sigma = stdev(data) if n > 1 else 0.0

    # Data-driven x range to avoid spec limits crushing the distribution.
    xmin = dmin
    xmax = dmax
    p = 0.05
    if xmin == xmax:
        delta = abs(xmin) * p if xmin != 0 else p
        xmin -= delta
        xmax += delta
    base_span = max(xmax - xmin, 1e-12)
    pad = base_span * p
    xmin -= pad
    xmax += pad

    if bool(req.showSpecLine):
        if req.lsl is not None:
            xmin = min(xmin, req.lsl)
        if req.usl is not None:
            xmax = max(xmax, req.usl)
        if xmin == xmax:
            delta = abs(xmin) * p if xmin != 0 else p
            xmin -= delta
            xmax += delta
        pad2 = (xmax - xmin) * p
        xmin -= pad2
        xmax += pad2

    # Follow Java control logic: 7=ShowLineBar, 8=ShowLine, 9=ShowBar
    mode = str(req.histogramfitr or "7")
    show_line = mode in ("7", "8")
    show_bar = mode in ("7", "9")
    opt_set = {str(v) for v in (req.histogramfit or [])}

    bins, nice_w = _calculate_minitab_bins(data)
    if req.binwidths is not None and req.binwidths > 0:
        bins = int(req.binwidths)

    min_nice_w = _auto_min_nice_bin_width(data)
    rng = max(xmax - xmin, 0.0)
    max_allowed_bins = int(math.floor(rng / min_nice_w)) if min_nice_w > 0 else bins
    if max_allowed_bins > 0:
        bins = min(bins, max_allowed_bins)
    bins = max(1, bins)

    # Keep one consistent bin width/start for histogram and fit curve.
    if dmax == dmin:
        bin_w = nice_w if nice_w > 0 else 1.0
    else:
        bin_w = nice_w if nice_w > 0 else (dmax - dmin) / bins
        if bin_w <= 0:
            bin_w = 1.0

    start = math.floor(dmin / bin_w) * bin_w
    end = start + bins * bin_w

    uniq_count = len({round(v, 12) for v in data})
    if uniq_count == 1 and bins == 1:
        center = dmin
        narrow_half = max(abs(center) * 0.0005, 0.0005)  # 0.05%, min 5e-4
        start = center - narrow_half
        end = center + narrow_half
        bin_w = max(end - start, 1e-6)

#jiejue zhuzi guokuan
    # if dmax == dmin:
    #     # Constant-data special case:
    #     # choose a local, small bin width around the point instead of wide [1,2]-style bin.
    #     if req.binwidths is not None and req.binwidths > 0:
    #         # 如果前端显式传了 bins，按规格窗口估一个窄 bin
    #         if req.lsl is not None and req.usl is not None and req.usl > req.lsl:
    #             bin_w = max((req.usl - req.lsl) / float(max(int(req.binwidths), 1)), 1e-6)
    #         else:
    #             ref = abs(dmin) if dmin != 0 else 1.0
    #             bin_w = max(ref * 0.002, 1e-6)  # 0.2%
    #     else:
    #         # 优先用 nice_w，但限制不要过宽
    #         ref = abs(dmin) if dmin != 0 else 1.0
    #         auto_w = max(ref * 0.002, 1e-6)    # 0.2%
    #         if nice_w is not None and nice_w > 0:
    #             bin_w = min(nice_w, auto_w)
    #         else:
    #             bin_w = auto_w

    #     # 单柱围绕数据点居中
    #     start = dmin - 0.5 * bin_w
    #     end = dmin + 0.5 * bin_w
    #     bins = 1
    # else:
    #     bin_w = nice_w if nice_w > 0 else (dmax - dmin) / bins
    #     if bin_w <= 0:
    #         bin_w = 1.0
    #     start = math.floor(dmin / bin_w) * bin_w
    #     end = start + bins * bin_w


    # 有规格线时，避免柱子越过规格线视觉边界
    # if bool(req.showSpecLine):
    #     if req.lsl is not None and dmin >= req.lsl:
    #         start = req.lsl
    #         end = start + bins * bin_w
    #     if req.usl is not None and dmax <= req.usl and end > req.usl:
    #         end = req.usl
    #         start = end - bins * bin_w
    print(data, start, bin_w, bins)
    fig = go.Figure()

    counts = _histogram_counts(data, start, bin_w, bins)
    max_count = max(counts) if counts else 0
    if show_bar:
        fig.add_trace(
            go.Histogram(
                x=data,
                xbins=dict(start=start, end=end, size=bin_w),
                marker=dict(color="rgb(91,155,213)", line=dict(color="rgb(70,95,130)", width=0.6)),
                opacity=1.0,
                hovertemplate="x=%{x:.6f}<br>count=%{y}<extra></extra>",
            )
        )

    if show_line and sigma > 0 and bin_w > 0:
        span = max(xmax - xmin, 1e-12)
        sample_count = max(400, min(2400, bins * 20))
        step = span / float(sample_count - 1)
        xs: List[float] = []
        ys: List[float] = []
        x = xmin
        for _ in range(sample_count):
            y = _norm_pdf(x, mu, sigma) * n * bin_w
            xs.append(x)
            ys.append(y)
            x += step
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line=dict(color="rgb(170,0,0)", width=2),
                hovertemplate="x=%{x:.6f}<br>y=%{y:.2f}<extra></extra>",
            )
        )
    if bool(req.showSpecLine):
        if req.lsl is not None:
            fig.add_vline(
                x=req.lsl,
                line_color="red",
                line_width=1.5,
                line_dash="dash",
                annotation_text=_fmt_stat(req.lsl, 6),
                annotation_position="top left",
                annotation_font=dict(size=10, color="red"),
            )
        if req.usl is not None:
            fig.add_vline(
                x=req.usl,
                line_color="red",
                line_width=1.5,
                line_dash="dash",
                annotation_text=_fmt_stat(req.usl, 6),
                annotation_position="top right",
                annotation_font=dict(size=10, color="red"),
            )

    # Right stats panel follows Java checkbox options.
    stat_lines: List[str] = []
    show_mean = "6" in opt_set
    if show_mean:
        stat_lines.append(f"Avg       {_fmt_stat(mu, 6)}")
    show_stdev = ("10" in opt_set) or (not opt_set)
    show_n = ("11" in opt_set) or (not opt_set)
    if show_stdev:
        stat_lines.append(f"Stdev     {_fmt_stat(sigma, 6)}")
    if show_n:
        stat_lines.append(f"N         {n}")
    lsl_txt = _fmt_stat(req.lsl, 6) if req.lsl is not None else "*"
    usl_txt = _fmt_stat(req.usl, 6) if req.usl is not None else "*"
    stat_lines.append(f"LSL       {lsl_txt}")
    stat_lines.append(f"USL       {usl_txt}")
    if "0" in opt_set:
        stat_lines.append(f"Overall   {_fmt_stat(sigma, 6)}")
    if "1" in opt_set:
        # Java current behavior is close to overall in this flow.
        stat_lines.append(f"Within    {_fmt_stat(sigma, 6)}")

    has_spec = req.lsl is not None and req.usl is not None and sigma > 0
    cpk_txt = "*"
    cpu_txt = "*"
    cpl_txt = "*"
    total_txt = "*"
    if has_spec:
        cpk = min((mu - req.lsl) / (3.0 * sigma), (req.usl - mu) / (3.0 * sigma))
        cpu = (req.usl - mu) / (3.0 * sigma)
        cpl = (mu - req.lsl) / (3.0 * sigma)
        z_lower = (req.lsl - mu) / sigma
        z_upper = (req.usl - mu) / sigma
        ppm_total = (_norm_cdf(z_lower) + (1.0 - _norm_cdf(z_upper))) * 1_000_000.0
        cpk_txt = f"{cpk:.2f}"
        cpu_txt = f"{cpu:.2f}"
        cpl_txt = f"{cpl:.2f}"
        if 0.0 < ppm_total < 0.01:
            total_txt = "<0.01"
        else:
            total_txt = _fmt_stat(ppm_total, 2)
    if "2" in opt_set:
        stat_lines.append(f"CPK       {cpk_txt}")
    if "3" in opt_set:
        stat_lines.append(f"CPU       {cpu_txt}")
    if "4" in opt_set:
        stat_lines.append(f"CPL       {cpl_txt}")
    if "5" in opt_set:
        stat_lines.append(f"Total     {total_txt}")
    # Option "6" controls the mean row.

    info_text = "<br>".join(stat_lines)
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.81,
        y=0.98,
        text=info_text,
        showarrow=False,
        font=dict(size=12, color="#222", family="Microsoft YaHei, SimHei, sans-serif"),
        align="left",
        xanchor="left",
        yanchor="top",
    )

    y_top = max(20.0, float(max_count))
    y_dtick = _nice_number(y_top / 6.0) if y_top > 0 else 10.0
    if y_dtick <= 0:
        y_dtick = 10.0
    y_max = max(y_dtick, math.ceil(y_top / y_dtick) * y_dtick)
#\u7684\u76f4\u65b9\u56fe

#################
    # is_constant = abs(dmax - dmin) < 1e-9
    # if bool(req.showSpecLine) and (req.lsl is not None or req.usl is not None):
    #     xmin = dmin
    #     xmax = dmax
    #     if req.lsl is not None:
    #         xmin = min(xmin, req.lsl)
    #     if req.usl is not None:
    #         xmax = max(xmax, req.usl)
    #     pad = max((xmax - xmin) * 0.05, 1e-6)
    #     xmin -= pad
    #     xmax += pad
    # else:
    #     if is_constant:
    #         half = max(abs(dmin) * 0.003, 0.001)
    #         xmin = dmin - half
    #         xmax = dmin + half
    #     else:
    #         pad = max((dmax - dmin) * 0.05, 1e-6)
    #         xmin = dmin - pad
    #         xmax = dmax + pad
####################
    fig.update_layout(
        title=dict(
            text=f"<b>{title} </b>",
            x=0.5,
            xanchor="center",
            y=0.93,
            font=dict(size=20, color="#333", family="Dialog, Microsoft YaHei, SimHei, sans-serif"),
        ),
        template="plotly_white",
        bargap=0.0,
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=55, r=25, t=96, b=55),
        showlegend=False,
        xaxis=dict(
            domain=[0.0, 0.80],
            range=[xmin, xmax],
            #title=dict(text=title, font=dict(size=14, family="Microsoft YaHei, SimHei, sans-serif")),
            showgrid=True,
            gridcolor="rgb(205,205,205)",
            zeroline=False,
            tickformat=_x_tick_format(xmin, xmax),
            tickfont=dict(size=10, family="Microsoft YaHei, SimHei, sans-serif"),
        ),
        yaxis=dict(
            title=dict(text="", font=dict(size=14, family="Microsoft YaHei, SimHei, sans-serif")),
            showgrid=True,
            gridcolor="rgb(205,205,205)",
            zeroline=False,
            dtick=y_dtick,
            range=[0, y_max],
            tickformat=",",
            tickfont=dict(size=10, family="Microsoft YaHei, SimHei, sans-serif"),
             showticklabels=False,  # 隐藏左侧Y轴数字
        ),
    )

    img_bytes = fig.to_image(format="png", width=req.width, height=req.height, scale=2)
    return base64.b64encode(img_bytes).decode("utf-8")


def render_histfit_response(req: HistogramFitRequest) -> Dict[str, Any]:
    image_base64 = render_histfit_png_base64(req)
    return {
        "status": "success",
        "message": "histogram fit image generated",
        "data": {
            "imageBase64": image_base64,
            "contentType": "image/png",
        },
    }

