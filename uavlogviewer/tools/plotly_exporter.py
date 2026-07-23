"""
plotly_exporter.py — Styled Plotly engine with Option 3: Vibrant Teal & Coral Theme,
dynamic truncated Y-axis labels, JS relayout listener for visible range stats updates,
clean empty annotation text on multi-row subplots, generous vertical spacing, and no top header title.

Dependencies: plotly, numpy, chart_store.
"""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore

def truncate_text(text: str, max_len: int = 24) -> str:
    """Truncates text exceeding max_len and appends '...'."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text

def generate_plotly_html(parsed_log: ParsedLog, chart_store: ChartStore) -> str:
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

    active_charts = [c for c in chart_store.charts if len(c.expressions) > 0]
    num_charts = len(active_charts)

    if num_charts == 0:
        return "<html><body style='background-color:#fafafa;'></body></html>"

    specs = [[{"secondary_y": True}] for _ in range(num_charts)]

    # Increase vertical spacing to 0.16 to prevent X-axis tick label overlap with lower subplot titles
    fig = make_subplots(
        rows=num_charts,
        cols=1,
        shared_xaxes=chart_store.sync_zoom,
        vertical_spacing=0.16 if num_charts > 1 else 0.10,
        specs=specs,
        subplot_titles=[f"Chart #{i + 1}" for i in range(num_charts)]
    )

    for c_idx, chart in enumerate(active_charts):
        row = c_idx + 1

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

            y_arr = parsed_log.time_series[field_key]

            if len(t_arr) != len(y_arr):
                t_arr = np.arange(len(y_arr))

            use_secondary = (expr.axis == 1)
            if use_secondary:
                axis2_fields.append(field_key)
            else:
                axis1_fields.append(field_key)

            fig.add_trace(
                go.Scatter(
                    x=t_arr,
                    y=y_arr,
                    mode='lines',
                    name=field_key,
                    line=dict(color=expr.color, width=2),
                    hovertemplate=f"<b>{field_key}</b><br>Time: %{{x:.2f}}s<br>Val: %{{y:.4f}}<extra></extra>"
                ),
                row=row,
                col=1,
                secondary_y=use_secondary
            )

        # Set dynamic truncated Y-axis labels
        label1 = truncate_text(", ".join(axis1_fields)) if axis1_fields else "Axis 1"
        label2 = truncate_text(", ".join(axis2_fields)) if axis2_fields else "Axis 2"

        fig.update_yaxes(title_text=label1, secondary_y=False, row=row, col=1)
        fig.update_yaxes(title_text=label2, secondary_y=True, row=row, col=1)

        # Hide X-axis tick labels for intermediate subplots when shared_xaxes is True to prevent overlap with titles
        if chart_store.sync_zoom and row < num_charts:
            fig.update_xaxes(showticklabels=False, row=row, col=1)
        else:
            fig.update_xaxes(showticklabels=True, title_text="Time (seconds)", row=row, col=1)

        # Add Flight Mode background color bands with empty string on row > 1 to prevent "new text"
        if parsed_log.flight_modes:
            for span in parsed_log.flight_modes:
                fig.add_vrect(
                    x0=span.start_time,
                    x1=span.end_time,
                    fillcolor=span.color,
                    opacity=0.20,
                    layer="below",
                    line_width=0,
                    annotation_text=span.name if row == 1 else "",
                    annotation_position="top left",
                    annotation_font=dict(size=10, color="#0f766e"),
                    row=row,
                    col=1
                )

    # Style Layout matching Option 3: Vibrant Teal & Coral Theme (NO top title header)
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#fafafa",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
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

    # Inject JavaScript listener to communicate visible X-axis time range to Python via document.title
    js_listener = """
    <script>
    window.addEventListener('DOMContentLoaded', function() {
        var checkPlot = setInterval(function() {
            var gd = document.getElementsByClassName('plotly-graph-div')[0];
            if (gd && gd.on) {
                clearInterval(checkPlot);
                gd.on('plotly_relayout', function(eventdata) {
                    var x0 = null, x1 = null;
                    if (eventdata['xaxis.range[0]'] !== undefined) {
                        x0 = eventdata['xaxis.range[0]'];
                        x1 = eventdata['xaxis.range[1]'];
                    } else if (eventdata['xaxis.range'] !== undefined && Array.isArray(eventdata['xaxis.range'])) {
                        x0 = eventdata['xaxis.range'][0];
                        x1 = eventdata['xaxis.range'][1];
                    }
                    if (x0 !== null && x1 !== null) {
                        document.title = "RANGE:" + x0 + ":" + x1;
                    } else if (eventdata['xaxis.autorange'] === true) {
                        document.title = "RANGE:RESET";
                    }
                });
            }
        }, 100);
    });
    </script>
    </body>
    """
    return html_str.replace("</body>", js_listener)
