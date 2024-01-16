import datetime as dt
import httpx
import geopandas as gpd
import pandas as pd

import schemas


def get_zones(
    id: schemas.Id | None = None,
    area: str | None = "MT",
    region: str | None = None,
    type: schemas.Type | None = schemas.Type.PUBLIC.value,
    point: str | None = None,
    include_geometry: bool = True,
    limit: int | None = None,
    effective: dt.datetime | None = None,
) -> gpd.GeoDataFrame:
    params = {
        "id": id,
        "area": area,
        "region": region,
        "type": type,
        "point": point,
        "include_geometry": include_geometry,
        "limit": limit,
        "effective": effective,
    }

    params = {k: v for k, v in params.items() if v is not None}

    r = httpx.get("https://api.weather.gov/zones", params=params)

    response_json = r.json()
    # The include_geometry query parameter doesn't work...
    # We have to manually query each zone to get their geometry.
    if not response_json["features"][0]["geometry"] and include_geometry:
        gpd_out = []

        for feature in response_json["features"]:
            zone = httpx.get(feature["id"])
            tmp = gpd.read_file(zone.text, driver="GeoJSON")
            gpd_out.append(tmp)
        gdf = gpd.GeoDataFrame(pd.concat(gpd_out, ignore_index=True))
    else:
        gdf = gpd.read_file(r.text, driver="GeoJSON")

    return gdf


def get_active_alerts(
    status: schemas.Status | None = None,
    message_type: schemas.MessageType | None = None,
    event: str | None = None,
    code: str | None = None,
    area: str | None = None,
    point: str | None = None,
    region: str | None = None,
    region_type: schemas.RegionType | None = None,
    zone: str | None = None,
    urgency: schemas.Urgency | None = None,
    severity: schemas.Severity | None = None,
    certainty: schemas.Certainty | None = None,
    limit: int | None = 500,
) -> dict[str, list|dict|str]:
    params = {
        "status": status,
        "message_type": message_type,
        "event": event,
        "code": code,
        "area": area,
        "point": point,
        "region": region,
        "region_type": region_type,
        "zone": zone,
        "urgency": urgency,
        "severity": severity,
        "certainty": certainty,
        "limit": limit,
    }
    
    params = {k: v for k, v in params.items() if v is not None}


    r = httpx.get(
        "https://api.weather.gov/alerts/active/", 
        params=params, 
        follow_redirects=True
    )

    return r.json()

def get_active_alerts_from_zones(gdf: gpd.GeoDataFrame, *args: str) -> gpd.GeoDataFrame:
    zones = ",".join(gdf['id'])
    alerts = get_active_alerts(zone=zones)

    default_args = {
        "affectedZones", "onset", "ends", "severity", "certainty",
        "event", "headline", "description", "instruction"
    }

    for arg in args:
        default_args.up(arg)

    df_out = []
    for feature in alerts['features']:
        data = {x: feature['properties'].get(x, None) for x in default_args}
        df_out.append(pd.DataFrame(data))

    df_out = pd.concat(df_out)
    df_out = df_out.rename(
        columns={
            'affectedZones': '@id'
        }
    )
    gdf = gdf[['@id', 'name', 'geometry']]
    df_out = gpd.GeoDataFrame(
        df_out.merge(gdf, how='left', on='@id')
    )
    return df_out

gdf = get_zones()
gdf = get_active_alerts_from_zones(gdf)
gdf.plot(column='event', categorical=True, legend=True)