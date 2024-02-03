import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

import asyncio
import datetime as dt
import httpx
import geopandas as gpd
import pandas as pd
import json
from pathlib import Path
from aiolimiter import AsyncLimiter


try:
    from . import schemas
except ImportError:
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

    async def get_zone_data(
        client: httpx.AsyncClient, 
        # limiter: AsyncLimiter, 
        zone_id: str,
    ):
        resp = await client.get(zone_id)
        return gpd.read_file(resp.text, driver="GeoJSON")

    async def process_features(response_json):

        async with httpx.AsyncClient(limits=httpx.Limits(max_connections=5)) as client:

            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(get_zone_data(client, feature["id"])) for feature in response_json["features"]]
            
            completed_tasks = [task.result() for task in tasks]
        
        await asyncio.sleep(1)
        return gpd.GeoDataFrame(pd.concat(completed_tasks, ignore_index=True))

    # The include_geometry query parameter doesn't work...
    # We have to manually query each zone to get their geometry.
    if not response_json["features"][0]["geometry"] and include_geometry:
        gdf = asyncio.run(process_features(response_json))
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
) -> dict[str, list | dict | str]:
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
        "https://api.weather.gov/alerts/active/", params=params, follow_redirects=True
    )

    return r.json()


def description_to_html(description: str) -> str:
    if "WHAT..." in description:
        description = (
            description.replace("*", "<li>")
            .replace("\n\n", "</li>")
            .replace("\n", " ")
            .replace("</li>", "</li>\n")
        )
        if not description.endswith("</li>"):
            description += "</li>"
        description = f"<ul>\n{description}\n</ul>"
        description = (
            description.replace("WHAT...", "<b>WHAT: </b>")
            .replace("WHEN...", "<b>WHEN: </b>")
            .replace("WHERE...", "<b>WHERE: </b>")
            .replace("IMPACTS...", "<b>IMPACTS: </b>")
            .replace("ADDITIONAL DETAILS...", "<b>ADDITIONAL DETAILS: </b>")
            .replace(
                "PRECAUTIONARY / PREPAREDNESS ACTIONS...",
                "<b>PRECAUTIONARY / PREPAREDNESS ACTIONS: </b>",
            )
        )

    return description


def summarise_by_zone(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    gdf = gdf.assign(description=gdf["description"].apply(description_to_html))
    out = gdf.assign(
        nested=gdf.drop(columns=["@id"]).apply(lambda x: x.to_json(), axis=1)
    )
    out["first"] = out.groupby("name")["event"].transform("first")
    out = out.groupby(["name", "id", "first"])["nested"].agg(list).reset_index()
    return out


def get_active_alerts_from_zones(gdf: gpd.GeoDataFrame, *args: str) -> gpd.GeoDataFrame:
    alerts = get_active_alerts(zone=",".join(gdf["id"]))

    if len(alerts["features"]) == 0:
        return gpd.GeoDataFrame({"id": [], "first": []})

    default_args = {
        "affectedZones",
        "onset",
        "ends",
        "severity",
        "certainty",
        "event",
        "headline",
        "description",
        "instruction",
    }

    for arg in args:
        default_args.up(arg)

    df_out = []
    for feature in alerts["features"]:
        data = {x: feature["properties"].get(x, None) for x in default_args}
        tmp = pd.DataFrame(data)
        df_out.append(tmp)

    df_out = pd.concat(df_out)
    df_out = df_out.rename(columns={"affectedZones": "@id"})
    gdf = gdf[["@id", "name", "geometry"]]
    df_out = gpd.GeoDataFrame(df_out.merge(gdf, how="left", on="@id")).drop(
        columns="geometry"
    )
    df_out["id"] = df_out["@id"].str.extract(r"/([^/]+)$")
    df_out = summarise_by_zone(df_out)
    return df_out


def save_zones(zones: gpd.GeoDataFrame, f_name: Path) -> None:
    zones["id"] = zones["@id"].str.extract(r"/([^/]+)$")
    zones = zones.drop(
        columns=[
            "observationStations",
            "radarStation",
            "effectiveDate",
            "expirationDate",
            "cwa",
            "forecastOffices",
            "timeZone",
        ]
    )

    zones.to_file(f_name)


def save_zone_event_json(alerts: pd.DataFrame, f_name: Path) -> None:
    alerts = dict(zip(alerts["id"], alerts["first"]))

    with open(f_name, "w") as file:
        json.dump(alerts, file)
