"""
plotly_exporter.py — Styled Plotly engine with Option 3: Vibrant Teal & Coral Theme,
dynamic truncated Y-axis labels, JS relayout listener for visible range stats updates,
clean empty annotation text on multi-row subplots, generous vertical spacing, and no top header title.

Dependencies: plotly, numpy, chart_store.
"""
import json
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from uavlogviewer.parsers.base_parser import ParsedLog, detect_segments_from_timestamps
from uavlogviewer.models.chart_store import ChartStore

def truncate_text(text: str, max_len: int = 24) -> str:
    """Truncates text exceeding max_len and appends '...'."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text

def sanitize_array(arr: np.ndarray) -> np.ndarray:
    """Ensures bytes/objects in numpy arrays are decoded to string or clean numbers for Plotly JSON serialization."""
    if arr is None or len(arr) == 0:
        return np.array([])
    if arr.dtype == object or arr.dtype.kind in ('S', 'U', 'O'):
        clean = []
        for v in arr:
            if isinstance(v, bytes):
                clean.append(v.decode('utf-8', errors='ignore'))
            else:
                clean.append(v)
        return np.array(clean)
    return arr

def filter_by_segment(t_arr: np.ndarray, y_arr: np.ndarray, segment_filter: str) -> tuple:
    """Slices t_arr and y_arr to match the chosen segment filter ('longest', 'all', or segment index)."""
    if segment_filter == "all" or t_arr is None or len(t_arr) == 0:
        return t_arr, y_arr

    segs = detect_segments_from_timestamps(t_arr)
    if not segs:
        return t_arr, y_arr

    target_seg = None
    if segment_filter == "longest":
        target_seg = next((s for s in segs if s.is_longest), segs[0])
    elif str(segment_filter).isdigit():
        idx = int(segment_filter)
        if 0 <= idx < len(segs):
            target_seg = segs[idx]

    if target_seg:
        s_idx = target_seg.start_idx
        e_idx = target_seg.end_idx + 1
        return t_arr[s_idx:e_idx], y_arr[s_idx:e_idx]

    return t_arr, y_arr

def generate_plotly_html(parsed_log: ParsedLog, chart_store: ChartStore, visible_range: tuple = None) -> str:
    if not parsed_log or not chart_store or not chart_store.has_any_expressions():
        return """
        <html>
        <body style='background-color:#fafafa; color:#525252; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align:center; padding-top:100px;'>
            <div style='border: 1px solid #e5e5e5; display: inline-block; padding: 40px 60px; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);'>
                <h2 style='color: #0d9488; margin-bottom: 10px;'>✈️ UAV Log Viewer</h2>
                <p style='font-size: 14px;'>Double-click telemetry fields in the sidebar tree to generate interactive plots.</p>
            </div>
        </body>
        </html>
        """

    active_charts = [
        c for c in chart_store.charts
        if (c.chart_type == "timeseries" and len(c.expressions) > 0) or
           (c.chart_type == "scatter" and (c.x_field != "" or c.y_field != ""))
    ]

    if not active_charts:
        return "<html><body style='background-color:#fafafa;'></body></html>"

    active_seg_bounds = None
    if chart_store.segment_filter != "all":
        primary_segs = parsed_log.get_segments()
        if primary_segs:
            target_seg = None
            if chart_store.segment_filter == "longest":
                target_seg = next((s for s in primary_segs if s.is_longest), primary_segs[0])
            elif str(chart_store.segment_filter).isdigit():
                idx = int(chart_store.segment_filter)
                if 0 <= idx < len(primary_segs):
                    target_seg = primary_segs[idx]
            if target_seg:
                active_seg_bounds = (target_seg.start_time, target_seg.end_time)

    # Compute row heights, specs, titles, and row mappings
    specs = []
    titles = []
    row_heights = []
    chart_row_map = {}

    row_counter = 1
    for c_idx, chart in enumerate(active_charts):
        if chart.chart_type == "scatter":
            chart_row_map[c_idx] = {'scatter_row': row_counter, 'timeline_row': row_counter + 1}
            specs.append([{"secondary_y": False}])
            specs.append([{"secondary_y": True}])
            row_heights.append(1.0)
            row_heights.append(0.20) # 0.2x height compact timeline
            titles.append(f"XY Scatter: {chart.y_field} vs {chart.x_field}")
            titles.append("") # No title for bound timeline
            row_counter += 2
        else:
            chart_row_map[c_idx] = {'ts_row': row_counter}
            specs.append([{"secondary_y": True}])
            row_heights.append(1.0)
            titles.append(f"Chart #{c_idx + 1}")
            row_counter += 1

    total_rows = len(specs)

    time_axis_ids = []
    for c_idx, chart in enumerate(active_charts):
        if chart.chart_type == "scatter":
            r_tl = chart_row_map[c_idx]['timeline_row']
            time_axis_ids.append("xaxis" if r_tl == 1 else f"xaxis{r_tl}")
        else:
            r_ts = chart_row_map[c_idx]['ts_row']
            time_axis_ids.append("xaxis" if r_ts == 1 else f"xaxis{r_ts}")

    fig = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=False,
        row_heights=row_heights,
        vertical_spacing=0.14 if any(c.chart_type == "scatter" for c in active_charts) else 0.10,
        specs=specs,
        subplot_titles=titles
    )

    for c_idx, chart in enumerate(active_charts):
        if chart.chart_type == "scatter":
            r_scatter = chart_row_map[c_idx]['scatter_row']
            r_timeline = chart_row_map[c_idx]['timeline_row']

            last_x_key, last_y_key = "", ""

            for pair in chart.pairs:
                x_key = pair.x_field
                y_key = pair.y_field
                pair_color = pair.color or '#ea580c'

                if not x_key and not y_key:
                    continue

                if x_key: last_x_key = x_key
                if y_key: last_y_key = y_key

                x_t_arr, x_y_arr = np.array([]), np.array([])
                y_t_arr, y_y_arr = np.array([]), np.array([])

                if x_key in parsed_log.time_series:
                    x_y_arr = sanitize_array(parsed_log.time_series[x_key])
                    x_t_arr = parsed_log.timestamps.get(x_key, parsed_log.timestamps.get(x_key.split('.')[0], np.arange(len(x_y_arr))))
                    x_t_arr, x_y_arr = filter_by_segment(x_t_arr, x_y_arr, chart_store.segment_filter)

                if y_key in parsed_log.time_series:
                    y_y_arr = sanitize_array(parsed_log.time_series[y_key])
                    y_t_arr = parsed_log.timestamps.get(y_key, parsed_log.timestamps.get(y_key.split('.')[0], np.arange(len(y_y_arr))))
                    y_t_arr, y_y_arr = filter_by_segment(y_t_arr, y_y_arr, chart_store.segment_filter)

                if len(x_y_arr) > 0 and len(y_y_arr) > 0:
                    # 1. Filter top XY Scatter plot by visible_range if specified
                    if visible_range and len(visible_range) == 2 and visible_range[0] is not None and visible_range[1] is not None:
                        x0, x1 = visible_range
                        mask_x = (x_t_arr >= x0) & (x_t_arr <= x1)
                        mask_y = (y_t_arr >= x0) & (y_t_arr <= x1)
                        x_t_sub, x_y_sub = x_t_arr[mask_x], x_y_arr[mask_x]
                        y_t_sub, y_y_sub = y_t_arr[mask_y], y_y_arr[mask_y]
                    else:
                        x_t_sub, x_y_sub = x_t_arr, x_y_arr
                        y_t_sub, y_y_sub = y_t_arr, y_y_arr

                    if len(x_t_sub) > 0 and len(y_t_sub) > 0:
                        if len(x_t_sub) == len(y_t_sub) and np.array_equal(x_t_sub, y_t_sub):
                            final_x, final_y, final_t = x_y_sub, y_y_sub, x_t_sub
                        else:
                            final_x = x_y_sub
                            final_t = x_t_sub
                            try:
                                final_y = np.interp(final_t, y_t_sub, y_y_sub)
                            except Exception:
                                final_y = y_y_sub[:len(final_x)] if len(y_y_sub) >= len(final_x) else np.pad(y_y_sub, (0, len(final_x) - len(y_y_sub)), 'edge')

                        final_x = sanitize_array(final_x)
                        final_y = sanitize_array(final_y)

                        max_pts = getattr(chart, 'max_points', 5000)
                        if max_pts > 0 and len(final_x) > max_pts:
                            step = max(1, len(final_x) // max_pts)
                            scat_x, scat_y, scat_t = final_x[::step], final_y[::step], final_t[::step]
                        else:
                            scat_x, scat_y, scat_t = final_x, final_y, final_t

                        # Top Row: WebGL Accelerated XY Scatter Plot (Y vs X)
                        fig.add_trace(
                            go.Scattergl(
                                x=scat_x,
                                y=scat_y,
                                mode='markers+lines',
                                name=f"{y_key} vs {x_key}",
                                marker=dict(size=4, color=pair_color),
                                line=dict(color=pair_color, width=1, dash='dot'),
                                customdata=scat_t,
                                hovertemplate=f"<b>XY Scatter</b><br>X ({x_key}): %{{x}}<br>Y ({y_key}): %{{y}}<br>Time: %{{customdata:.2f}}s<extra></extra>"
                            ),
                            row=r_scatter,
                            col=1,
                            secondary_y=False
                        )

                    # Downsample timeline if > 5000 points
                    step_x = max(1, len(x_t_arr) // 5000) if len(x_t_arr) > 5000 else 1
                    step_y = max(1, len(y_t_arr) // 5000) if len(y_t_arr) > 5000 else 1

                    # Bottom Row: Bound Compact Timeline Chart (X(t) and Y(t) vs Time)
                    fig.add_trace(
                        go.Scattergl(
                            x=x_t_arr[::step_x],
                            y=x_y_arr[::step_x],
                            mode='lines',
                            name=f"{x_key}",
                            line=dict(color=pair_color, width=1.5),
                            hovertemplate=f"<b>{x_key}</b><br>Time: %{{x:.2f}}s<br>Val: %{{y}}<extra></extra>"
                        ),
                        row=r_timeline,
                        col=1,
                        secondary_y=False
                    )

                    if y_key != x_key:
                        fig.add_trace(
                            go.Scattergl(
                                x=y_t_arr[::step_y],
                                y=y_y_arr[::step_y],
                                mode='lines',
                                name=f"{y_key}",
                                line=dict(color=pair_color, width=1.5, dash='dash'),
                                hovertemplate=f"<b>{y_key}</b><br>Time: %{{x:.2f}}s<br>Val: %{{y}}<extra></extra>"
                            ),
                            row=r_timeline,
                            col=1,
                            secondary_y=True
                        )

            fig.update_xaxes(title_text=f"X: {last_x_key or 'None'}", showticklabels=True, row=r_scatter, col=1)
            fig.update_yaxes(title_text=f"Y: {last_y_key or 'None'}", secondary_y=False, row=r_scatter, col=1)

            first_time_r = int(time_axis_ids[0].replace("xaxis", "")) if time_axis_ids[0] != "xaxis" else 1
            first_match_key = "x" if first_time_r == 1 else f"x{first_time_r}"

            # Bound Timeline Row Y-Axis: No Y-ticks, no Y-label
            fig.update_yaxes(showticklabels=False, title_text="", showgrid=False, zeroline=False, row=r_timeline, col=1, secondary_y=False)
            fig.update_yaxes(showticklabels=False, title_text="", showgrid=False, zeroline=False, row=r_timeline, col=1, secondary_y=True)
            
            # Persist timeline range if visible_range is active so it doesn't snap back to full range!
            if visible_range and len(visible_range) == 2 and visible_range[0] is not None and visible_range[1] is not None:
                fig.update_xaxes(range=[visible_range[0], visible_range[1]], title_text="Time (seconds)", showticklabels=True, row=r_timeline, col=1)
            elif active_seg_bounds:
                fig.update_xaxes(range=[active_seg_bounds[0], active_seg_bounds[1]], title_text="Time (seconds)", showticklabels=True, row=r_timeline, col=1)
            else:
                fig.update_xaxes(title_text="Time (seconds)", showticklabels=True, row=r_timeline, col=1)

            if chart_store.sync_zoom and r_timeline != first_time_r:
                fig.update_xaxes(matches=first_match_key, row=r_timeline, col=1)

        else:
            r_ts = chart_row_map[c_idx]['ts_row']
            first_time_r = int(time_axis_ids[0].replace("xaxis", "")) if time_axis_ids[0] != "xaxis" else 1
            first_match_key = "x" if first_time_r == 1 else f"x{first_time_r}"

            axis1_fields = []
            axis2_fields = []

            for expr in chart.expressions:
                field_key = expr.name
                if field_key not in parsed_log.time_series:
                    continue

                if field_key in parsed_log.timestamps:
                    t_arr = parsed_log.timestamps[field_key]
                else:
                    msg_type = field_key.split('.')[0]
                    t_arr = parsed_log.timestamps.get(msg_type, np.array([]))

                y_arr = sanitize_array(parsed_log.time_series[field_key])

                if len(t_arr) != len(y_arr):
                    t_arr = np.arange(len(y_arr))

                t_arr, y_arr = filter_by_segment(t_arr, y_arr, chart_store.segment_filter)

                use_secondary = (expr.axis == 1)
                if use_secondary:
                    axis2_fields.append(field_key)
                else:
                    axis1_fields.append(field_key)

                # Downsample if > 10000 points for smooth performance
                step_ts = max(1, len(t_arr) // 10000) if len(t_arr) > 10000 else 1

                fig.add_trace(
                    go.Scattergl(
                        x=t_arr[::step_ts],
                        y=y_arr[::step_ts],
                        mode='lines',
                        name=field_key,
                        line=dict(color=expr.color, width=2),
                        hovertemplate=f"<b>{field_key}</b><br>Time: %{{x:.2f}}s<br>Val: %{{y}}<extra></extra>"
                    ),
                    row=r_ts,
                    col=1,
                    secondary_y=use_secondary
                )

            label1 = truncate_text(", ".join(axis1_fields)) if axis1_fields else "Axis 1"
            label2 = truncate_text(", ".join(axis2_fields)) if axis2_fields else "Axis 2"

            fig.update_yaxes(title_text=label1, secondary_y=False, row=r_ts, col=1)
            fig.update_yaxes(title_text=label2, secondary_y=True, row=r_ts, col=1)

            if visible_range and len(visible_range) == 2 and visible_range[0] is not None and visible_range[1] is not None:
                fig.update_xaxes(range=[visible_range[0], visible_range[1]], showticklabels=(not chart_store.sync_zoom or r_ts == total_rows), row=r_ts, col=1)
            elif active_seg_bounds:
                fig.update_xaxes(range=[active_seg_bounds[0], active_seg_bounds[1]], showticklabels=(not chart_store.sync_zoom or r_ts == total_rows), title_text="Time (seconds)", row=r_ts, col=1)
            elif chart_store.sync_zoom and r_ts < total_rows:
                fig.update_xaxes(showticklabels=False, row=r_ts, col=1)
            else:
                fig.update_xaxes(showticklabels=True, title_text="Time (seconds)", row=r_ts, col=1)

            if chart_store.sync_zoom and r_ts != first_time_r:
                fig.update_xaxes(matches=first_match_key, row=r_ts, col=1)

            if parsed_log.flight_modes:
                spans_to_draw = parsed_log.flight_modes[:100]
                for span in spans_to_draw:
                    if active_seg_bounds:
                        s_min, s_max = active_seg_bounds
                        if span.end_time < s_min or span.start_time > s_max:
                            continue
                        v0 = max(span.start_time, s_min)
                        v1 = min(span.end_time, s_max)
                    else:
                        v0 = span.start_time
                        v1 = span.end_time

                    fig.add_vrect(
                        x0=v0,
                        x1=v1,
                        fillcolor=span.color,
                        opacity=0.20,
                        layer="below",
                        line_width=0,
                        annotation_text=span.name if r_ts == 1 else "",
                        annotation_position="top left",
                        annotation_font=dict(size=10, color="#0f766e"),
                        row=r_ts,
                        col=1
                    )

    has_scatter = any(c.chart_type == "scatter" for c in active_charts)

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#fafafa",
        plot_bgcolor="#ffffff",
        hovermode="closest" if has_scatter else "x unified",
        autosize=True,
        margin=dict(l=50, r=50, t=30, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color="#404040"),
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="#e5e5e5",
            borderwidth=1
        )
    )

    fig.update_xaxes(
        gridcolor="#f5f5f5",
        zerolinecolor="#d4d4d4",
        fixedrange=False
    )
    fig.update_yaxes(
        gridcolor="#f5f5f5",
        zerolinecolor="#d4d4d4",
        fixedrange=False
    )

    config_dict = {
        'scrollZoom': True,
        'responsive': True,
        'displayModeBar': True,
        'displaylogo': False
    }

    html_str = fig.to_html(include_plotlyjs=True, full_html=True, config=config_dict)

    time_axis_ids_json = json.dumps(time_axis_ids)

    # Inject JavaScript listener to communicate visible X-axis time range to Python via document.title (strictly for time-series X-axes)
    js_listener = f"""
    <script>
    window.addEventListener('DOMContentLoaded', function() {{
        var validTimeAxes = {time_axis_ids_json};
        var checkPlot = setInterval(function() {{
            var gd = document.getElementsByClassName('plotly-graph-div')[0];
            if (gd && gd.on) {{
                clearInterval(checkPlot);
                gd.on('plotly_relayout', function(eventdata) {{
                    var x0 = null, x1 = null;
                    for (var key in eventdata) {{
                        var axisPrefix = key.split('.')[0].split('[')[0];
                        if (validTimeAxes.indexOf(axisPrefix) !== -1) {{
                            if (key.indexOf('[0]') !== -1) {{
                                var baseKey = key.split('[0]')[0];
                                x0 = eventdata[baseKey + '[0]'];
                                x1 = eventdata[baseKey + '[1]'];
                                break;
                            }} else if (Array.isArray(eventdata[key]) && eventdata[key].length === 2) {{
                                x0 = eventdata[key][0];
                                x1 = eventdata[key][1];
                                break;
                            }}
                        }}
                    }}
                    if (x0 !== null && x1 !== null) {{
                        document.title = "RANGE:" + x0 + ":" + x1;
                    }} else {{
                        for (var k in eventdata) {{
                            var aPrefix = k.split('.')[0].split('[')[0];
                            if (validTimeAxes.indexOf(aPrefix) !== -1 && k.indexOf('autorange') !== -1) {{
                                document.title = "RANGE:RESET";
                                break;
                            }}
                        }}
                    }}
                }});
                gd.on('plotly_click', function(data) {{
                    if (data && data.points && data.points.length > 0) {{
                        var pt = data.points[0];
                        var clickTime = pt.x;
                        if (pt.customdata !== undefined && pt.customdata !== null) {{
                            clickTime = pt.customdata;
                        }}
                        var isAltKey = false;
                        if (data.event && (data.event.altKey || data.event.metaKey)) {{
                            isAltKey = true;
                        }}
                        if (isAltKey && clickTime !== undefined && clickTime !== null) {{
                            document.title = "CLICK_TIME:" + clickTime;
                        }}
                    }}
                }});
            }}
        }}, 100);
    }});
    </script>
    </body>
    """
    return html_str.replace("</body>", js_listener)
