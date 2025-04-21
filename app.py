import json
import pandas as pd
import dash
from dash import html, dcc
import dash_leaflet as dl
from dash.dependencies import Input, Output, ALL
import os
import random
import warnings

# Base directory
BASE_DIR = os.path.dirname(__file__)
GEOJSON_PATH = os.path.join(BASE_DIR, "Suburbs_GDA2020.geojson")
EXCEL_PATH = os.path.join(BASE_DIR, "Adelaide.xlsx")
DRIVER_CSV = os.path.join(BASE_DIR, "Driver.csv")

# Load GeoJSON
with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
    geojson = json.load(f)

# Load region-to-postcodes mapping from Excel
mapping_df = pd.read_excel(EXCEL_PATH, sheet_name=0, dtype=str)
mapping_df.columns = mapping_df.columns.str.strip().str.lower()
if 'zone' not in mapping_df.columns or 'postcode' not in mapping_df.columns:
    raise KeyError("Adelaide.xlsx must contain 'zone' and 'postcode' columns")
postcode_zone = {}
for _, row in mapping_df.iterrows():
    region = row['zone']
    for pc in str(row['postcode']).split(','):
        pc = pc.strip()
        if pc:
            postcode_zone[pc] = region

# Load driver assignments: region -> responsible
driver_df = pd.read_csv(DRIVER_CSV, dtype=str)
driver_df.columns = driver_df.columns.str.strip().str.lower()
if 'zone' not in driver_df.columns or 'responsible' not in driver_df.columns:
    raise KeyError("Driver.csv must contain 'zone' and 'responsible' columns")
# Ensure driver entries for all regions
all_regions = sorted(mapping_df['zone'].unique())
zone_driver = {region: "" for region in all_regions}
for _, row in driver_df.iterrows():
    zone_driver[row['zone']] = row['responsible']

# Assign region property and colors to features
zone_colors = {r: f"#{random.randint(0, 0xFFFFFF):06x}" for r in all_regions}
for feat in geojson['features']:
    pc = str(feat['properties'].get('postcode')).strip()
    feat['properties']['zone'] = postcode_zone.get(pc, '未知区域')

# Create polygon layers per feature
polygons = []
for feat in geojson['features']:
    coords = feat['geometry']['coordinates']
    region = feat['properties']['zone']
    color = zone_colors.get(region, '#CCCCCC')
    rings = [coords] if feat['geometry']['type'] == 'Polygon' else coords
    for ring in rings:
        pts = ring[0] if isinstance(ring[0][0], list) else ring
        positions = [(lat, lon) for lon, lat in pts]
        polygons.append(
            dl.Polygon(
                positions=positions,
                color='black', weight=1,
                fill=True, fillColor=color, fillOpacity=0.5
            )
        )

# Compute region centers from features
region_centers = {}
# accumulate all lat/lon per region
accum = {r: [] for r in all_regions}
for feat in geojson['features']:
    region = feat['properties']['zone']
    coords = feat['geometry']['coordinates']
    rings = [coords] if feat['geometry']['type'] == 'Polygon' else coords
    for ring in rings:
        pts = ring[0] if isinstance(ring[0][0], list) else ring
        for lon, lat in pts:
            accum.setdefault(region, []).append((lat, lon))
# average
for region, pts in accum.items():
    if pts:
        lats, lons = zip(*pts)
        region_centers[region] = [sum(lats)/len(lats), sum(lons)/len(lons)]

# Create markers for region labels
markers = []
for region, center in region_centers.items():
    markers.append(
        dl.Marker(
            position=center,
            children=[dl.Tooltip(region, permanent=True, direction='center')],
            interactive=False
        )
    )

# Initialize Dash
app = dash.Dash(__name__)
server = app.server

# Sidebar: region buttons and input for driver ID
sidebar = html.Div([
    html.H2("配送区域负责人", style={'marginTop':'0'}),
    *[
        html.Div([
            html.Button(region, id={'type':'zone-btn','index':region}, n_clicks=0, style={'marginRight':'5px'}),
            dcc.Input(id={'type':'zone-input','index':region}, type='text', value=zone_driver[region], style={'flex':1})
        ], style={'display':'flex','alignItems':'center','marginBottom':'5px'})
        for region in all_regions
    ]
], style={'width':'20%','padding':'10px','backgroundColor':'#f8f9fa','overflowY':'auto','height':'100vh'})

# Layout: map and sidebar
app.layout = html.Div([
    dl.Map([dl.TileLayer()] + polygons + markers,
           id='map', center=[-34.9285,138.6007], zoom=10,
           style={'flex':1,'height':'100vh'}),
    sidebar
], style={'display':'flex','flexDirection':'row','margin':0,'padding':0})

# Helper to compute bounds for a region
def get_bounds(region):
    pts = []
    for feat in geojson['features']:
        if feat['properties']['zone'] == region:
            coords = feat['geometry']['coordinates']
            rings = [coords] if feat['geometry']['type']=='Polygon' else coords
            for ring in rings:
                pts_list = ring[0] if isinstance(ring[0][0], list) else ring
                for lon, lat in pts_list:
                    pts.append((lat, lon))
    if not pts:
        return None
    lats, lons = zip(*pts)
    return [[min(lats), min(lons)], [max(lats), max(lons)]]

# Callback: zoom and save driver ID on input change
@app.callback(
    Output('map','bounds'),
    [Input({'type':'zone-btn','index':ALL},'n_clicks'),
     Input({'type':'zone-input','index':ALL},'value')]
)
def update_map(btns, values):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    comp_id = ctx.triggered[0]['prop_id'].split('.')[0]
    region = json.loads(comp_id)['index']
    prop = ctx.triggered[0]['prop_id'].split('.')[1]
    # if input changed, save to CSV
    if prop == 'value':
        new_val = ctx.triggered[0]['value']
        df = pd.read_csv(DRIVER_CSV, dtype=str)
        df.columns = df.columns.str.strip().str.lower()
        df.loc[df['zone'] == region, 'responsible'] = new_val
        df.to_csv(DRIVER_CSV, index=False, encoding='utf-8-sig')
    # zoom
    bounds = get_bounds(region)
    if bounds:
        return bounds
    raise dash.exceptions.PreventUpdate

if __name__ == '__main__':
    app.run(debug=True)
