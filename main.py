import os
import xml.etree.ElementTree as ET
from collections import defaultdict
import yaml
from bioio import BioImage
import plotly.colors
import plotly.graph_objects as go
from plotly.subplots import make_subplots


if __name__ == "__main__":
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    czi_filepath = config["czi_filepath"]
    print(f"  Analyzing file: {czi_filepath}")

    subblocks_path = "subblocks.xml"
    use_cache = os.path.exists(subblocks_path)

    img = BioImage(
        czi_filepath,
        reconstruct_mosaic=False,
        include_subblock_metadata=not use_cache,
    )

    if use_cache:
        subblocks = ET.parse(subblocks_path).getroot().findall("./Subblock")
        print(f"  Loaded {len(subblocks)} subblocks from {subblocks_path}")
    else:
        subblocks = img.metadata.findall("./Subblocks/Subblock")
        subblocks_root = ET.Element("Subblocks")
        subblocks_root.extend(subblocks)
        ET.indent(subblocks_root)
        ET.ElementTree(subblocks_root).write(
            subblocks_path, encoding="utf-8", xml_declaration=True
        )
        print(f"  Saved {len(subblocks)} subblocks to {subblocks_path}")
    subblocks_count = len(subblocks)

    print(f"  Dimensions: {img.dims}")
    print(f"  Scenes ({len(img.scenes)}): {img.scenes}")
    print(f"  Channels ({len(img.channel_names)}): {[str(c) for c in img.channel_names]}")

    # positions[scene][tile][channel] -> [(T, x, y, focus), ...] sorted by T
    positions = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for sb in subblocks:
        tags = sb.find("./METADATA/Tags")
        if tags is None:
            continue
        x, y, z = (
            float(tags.findtext(name))
            for name in ("StageXPosition", "StageYPosition", "FocusPosition")
        )
        s, m, c, t = (int(sb.get(k, 0)) for k in ("S", "M", "C", "T"))
        positions[s][m][c].append((t, x, y, z))
    for tiles in positions.values():
        for channels in tiles.values():
            for series in channels.values():
                series.sort()

    # Scenes in a 2x3 grid; each scene cell is an XY panel next to a focus panel.
    channel = 1
    grid_rows, grid_cols = 2, 3
    fig = make_subplots(
        rows=grid_rows,
        cols=2 * grid_cols,
        subplot_titles=[
            f"{name} {kind}"
            for name in img.scenes
            for kind in ("XY", "Focus")
        ],
    )
    colors = plotly.colors.qualitative.Plotly
    shown_tiles = set()
    for s, name in enumerate(img.scenes):
        row, col = s // grid_cols + 1, 2 * (s % grid_cols) + 1
        for i, (m, channels) in enumerate(sorted(positions[s].items())):
            ts, xs, ys, zs = zip(*channels[channel])
            common = dict(
                mode="lines+markers",
                name=f"M{m}",
                legendgroup=f"M{m}",
                line_color=colors[i % len(colors)],
            )
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    customdata=ts,
                    hovertemplate=f"{name}<br>"
                    "T=%{customdata}<br>x=%{x}<br>y=%{y}",
                    showlegend=m not in shown_tiles,
                    **common,
                ),
                row=row,
                col=col,
            )
            fig.add_trace(
                go.Scatter(x=ts, y=zs, showlegend=False, **common),
                row=row,
                col=col + 1,
            )
            shown_tiles.add(m)
        xy = fig.get_subplot(row, col)
        xy.xaxis.title.text = "StageXPosition"
        xy.yaxis.title.text = "StageYPosition"
        xy.yaxis.scaleanchor = xy.yaxis.anchor
        xy.yaxis.scaleratio = 1
        fig.get_subplot(row, col + 1).xaxis.title.text = "T"
    fig.update_layout(
        title=f"Channel {channel}: {img.channel_names[channel]}",
        template="plotly_dark",
    )
    figure_path = "positions.html"
    fig.write_html(figure_path)
    print(f"  Saved figure to {figure_path}")
    fig.show()