import json
import random
import dash
from dash import html, dcc
import dash_leaflet as dl
from dash.dependencies import Input, Output, ALL
import pandas as pd
import colorsys

# 1. 读取区域与邮编映射
mapper = pd.read_excel('Adelaide.xlsx', dtype=str)
mapper.columns = mapper.columns.str.strip().str.lower()
postcode_zone = {}
for _, row in mapper.iterrows():
    zone = row['zone']
    for pc in str(row['postcode']).split(','):
        postcode_zone[pc.strip()] = zone

# 2. 读取区域负责人
driver_df = pd.read_csv('Driver.csv', dtype=str)
driver_df.columns = driver_df.columns.str.strip().str.lower()
all_zones = sorted(mapper['zone'].unique())
zone_driver = {z: '' for z in all_zones}
for _, row in driver_df.iterrows():
    zone_driver[row['zone']] = row['responsible']

# 3. 加载裁剪后的 GeoJSON
with open('clipped_bbox.geojson', 'r', encoding='utf-8') as f:
    geo = json.load(f)

# 4. 生成无重复颜色映射（HSL + 金比例序列）
zone_colors = {}
n = len(all_zones)
phi = 0.618033988749895  # 黄金比例倒数，避免相邻色相相近
for i, z in enumerate(all_zones):
    h = (i * phi) % 1
    r, g, b = colorsys.hsv_to_rgb(h, 0.6, 0.85)
    zone_colors[z] = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

# 5. 构建多边形层并收集各区域点列表 构建多边形层并收集各区域点列表
polygons = []
region_polys = {z: [] for z in all_zones}
for feat in geo['features']:
    pc = str(feat['properties'].get('postcode', '')).strip()
    z = postcode_zone.get(pc)
    if not z:
        continue
    coords = feat['geometry']['coordinates']
    rings = [coords] if feat['geometry']['type'] == 'Polygon' else coords
    for ring in rings:
        pts = ring[0] if isinstance(ring[0][0], list) else ring
        positions = [(lat, lon) for lon, lat in pts]
        polygons.append(
            dl.Polygon(
                positions=positions,
                color='black', weight=1,
                fill=True, fillColor=zone_colors[z], fillOpacity=0.6
            )
        )
        region_polys[z].append(positions)

# 6. 读取预先计算的质心文件
with open('region_centroids.json', 'r', encoding='utf-8') as f:
    region_centroids = json.load(f)
markers = []
for z in all_zones:
    coord = region_centroids.get(z)
    if coord:
        markers.append(
            dl.Marker(
                position=coord,
                children=[dl.Tooltip(z, permanent=True, direction='center')],
                interactive=False
            )
        )

# 7. 构建侧边栏布局
sidebar = html.Div([
    html.H2('配送区域负责人'),
    *[
        html.Div([
            html.Button(z, id={'type':'btn','index':z}, n_clicks=0,
                        style={'marginRight':'5px'}),
            dcc.Input(id={'type':'input','index':z}, type='text', value=zone_driver[z],
                      style={'flex':1})
        ], style={'display':'flex', 'alignItems':'center', 'marginBottom':'5px'})
        for z in all_zones
    ]
], style={'width': '25%', 'padding': '10px', 'backgroundColor': '#fafafa',
          'overflowY': 'auto', 'height': '100vh'})

# 8. 初始化 Dash 应用并布局
app = dash.Dash(__name__)
app.layout = html.Div([
    dl.Map(
        children=[dl.TileLayer(), *polygons, *markers],
        center=[-34.9285, 138.6007], zoom=10,
        style={'flex':1, 'height':'100vh'}, id='map'
    ),
    sidebar
], style={'display':'flex', 'margin':0, 'padding':0})

# 9. 回调：缩放与保存
@app.callback(
    Output('map', 'bounds'),
    [Input({'type':'btn','index':ALL}, 'n_clicks'),
     Input({'type':'input','index':ALL}, 'value')]
)
def update_map(btns, vals):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    comp, prop = ctx.triggered[0]['prop_id'].split('.')
    region = json.loads(comp)['index']
    # 如果是输入框变更，保存到 CSV
    if prop == 'value':
        df = pd.read_csv('Driver.csv', dtype=str)
        df.columns = df.columns.str.strip().str.lower()
        df.loc[df['zone'] == region, 'responsible'] = ctx.triggered[0]['value']
        df.to_csv('Driver.csv', index=False, encoding='utf-8-sig')
    # 缩放到预设质心附近
    coord = region_centroids.get(region)
    if coord:
        lat, lon = coord
        d = 0.01
        return [[lat - d, lon - d], [lat + d, lon + d]]
    raise dash.exceptions.PreventUpdate

# Expose the WSGI callable for Gunicorn
application = app.server

if __name__ == '__main__':
    app.run(debug=True)
