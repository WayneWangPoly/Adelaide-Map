import json
import random
import dash
from dash import html, dcc
import dash_leaflet as dl
from dash.dependencies import Input, Output, ALL
import pandas as pd
import math

# 1. 读取数据
mapper = pd.read_excel('Adelaide.xlsx', dtype=str)
mapper.columns = mapper.columns.str.strip().str.lower()
postcode_zone = {}
for _, row in mapper.iterrows():
    for pc in str(row['postcode']).split(','):
        postcode_zone[pc.strip()] = row['zone']

driver_df = pd.read_csv('Driver.csv', dtype=str)
driver_df.columns = driver_df.columns.str.strip().str.lower()
all_zones = sorted(mapper['zone'].unique())
zone_driver = {z: '' for z in all_zones}
for _, row in driver_df.iterrows():
    zone_driver[row['zone']] = row['responsible']

# 2. 加载 GeoJSON 并构建 Polygon 图层
with open('Suburbs_GDA2020.geojson', 'r', encoding='utf-8') as f:
    geo = json.load(f)

# 颜色映射
tmp_colors = {z: f"#{random.randint(0,0xFFFFFF):06x}" for z in all_zones}

# 构建多边形和区域多边形列表
polygons = []
region_polygons = {z: [] for z in all_zones}
for feat in geo['features']:
    pc = str(feat['properties'].get('postcode')).strip()
    region = postcode_zone.get(pc)
    if not region:
        continue
    coords = feat['geometry']['coordinates']
    rings = [coords] if feat['geometry']['type']=='Polygon' else coords
    for ring in rings:
        pts = ring[0] if isinstance(ring[0][0], list) else ring
        positions = [(lat, lon) for lon, lat in pts]
        polygons.append(
            dl.Polygon(
                positions=positions,
                color='black', weight=1,
                fill=True, fillColor=tmp_colors[region], fillOpacity=0.5
            )
        )
        region_polygons[region].append(positions)

# 计算最大多边形质心
markers = []
def polygon_centroid(coords):
    # coords list of (lat, lon)
    pts = [(y, x) for x, y in coords]
    area = 0; Cx = 0; Cy = 0; n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i+1) % n]
        cross = x0*y1 - x1*y0
        area += cross; Cx += (x0+x1)*cross; Cy += (y0+y1)*cross
    area /= 2
    if abs(area) < 1e-9:
        return (sum(y for x,y in pts)/n, sum(x for x,y in pts)/n), 0
    Cx /= 6*area; Cy /= 6*area
    return (Cy, Cx), abs(area)

for region, poly_list in region_polygons.items():
    best = None; best_area = -1
    for coords in poly_list:
        (latc, lonc), area = polygon_centroid(coords)
        if area > best_area:
            best_area = area; best = (latc, lonc)
    if best:
        markers.append(
            dl.Marker(
                position=best,
                children=[dl.Tooltip(region, permanent=True, direction='center')],
                interactive=False
            )
        )

# 3. 构建侧边栏
sidebar = html.Div([
    html.H2('配送区域负责人'),
    *[
        html.Div([
            html.Button(z, id={'type':'btn','index':z}, n_clicks=0, style={'marginRight':'5px'}),
            dcc.Input(id={'type':'input','index':z}, type='text', value=zone_driver[z], style={'flex':1})
        ], style={'display':'flex','alignItems':'center','marginBottom':'5px'})
        for z in all_zones
    ]
], style={'width':'25%','padding':'10px','backgroundColor':'#f0f0f0','height':'100vh','overflowY':'auto'})

# 4. 初始化 Dash
dapp = dash.Dash(__name__)

dapp.layout = html.Div([
    dl.Map(children=[dl.TileLayer()] + polygons + markers,
           center=[-34.9285,138.6007], zoom=10,
           style={'flex':1,'height':'100vh'}, id='map'),
    sidebar
], style={'display':'flex','margin':0,'padding':0})

# 5. 回调：缩放 & 保存
@dapp.callback(
    Output('map','bounds'),
    [Input({'type':'btn','index':ALL},'n_clicks'),
     Input({'type':'input','index':ALL},'value')]
)
def update_map(btns, vals):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    comp, prop = ctx.triggered[0]['prop_id'].split('.')
    region = json.loads(comp)['index']
    if prop == 'value':
        new_val = ctx.triggered[0]['value']
        df = pd.read_csv('Driver.csv', dtype=str)
        df.columns = df.columns.str.strip().str.lower()
        df.loc[df['zone']==region, 'responsible'] = new_val
        df.to_csv('Driver.csv', index=False, encoding='utf-8-sig')
    # bounds
    poly_list = region_polygons.get(region, [])
    all_pts = [pt for coords in poly_list for pt in coords]
    if all_pts:
        lats, lons = zip(*all_pts)
        return [[min(lats), min(lons)], [max(lats), max(lons)]]
    raise dash.exceptions.PreventUpdate

if __name__=='__main__':
    dapp.run(debug=True)
