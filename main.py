import argparse
from enum import Enum
from pathlib import Path
import geopandas as gpd
import pandas as pd
from typing import Optional

from nws_spatial import get
from nws_spatial.utils import render_templates


class Options(Enum):
    zones = "zones"
    alerts = "alerts"
    templates = "templates"

    def __str__(self):
        return self.value


option_mapper = {
    "zones": get.get_zones,
    "alerts": get.get_active_alerts_from_zones,
    "templates": render_templates,
}


def valid_option(value):
    if value not in Options.__members__:
        raise argparse.ArgumentTypeError(f"Invalid option: {value}")
    return Options[value]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "funcs",
        type=valid_option,
        nargs="+",
        choices=list(Options),
        help="List of options: zones, alerts, templates",
    )

    parser.add_argument(
        "--zone-id",
        type=str,
        help="Two-letter state code",
        default=None,
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Directory to save files out to.",
        default=Path("./data"),
    )
    parser.add_argument(
        "--zones",
        type=Path,
        help="Path where the zones .geojson either exists or will be saved to",
        default=Path("./data/mt-zones.fgb"),
    )
    parser.add_argument(
        "--counties",
        type=Path,
        help="Path where the counties .geojson either exists or will be saved to",
        default=Path("./data/mt-counties.fgb"),
    )
    parser.add_argument(
        "--template-dir",
        type=Path,
        help="The path to the directory with templates for alerts.",
        default=Path("./templates"),
    )
    parser.add_argument(
        "--alert-file",
        type=Path,
        help="Path to .csv with the latest alerts",
        default=Path("./data/latest_alerts.csv"),
    )

    args = parser.parse_args()

    if Options.zones in args.funcs:
        print("Getting Zones...")
        zones = get.get_zones(area=args.zone_id)
        if args.zone_id is None:
            out_name = "all-zones.fgb"
        else:
            out_name = f"{args.zone_id}-zones.fgb".lower()
        get.save_zones(zones, args.out_dir / out_name)

        counties = get.get_zones(area=args.zone_id, type="county")
        get.save_zones(counties, args.out_dir / out_name.replace("zones", "counties"))

    else:
        zones = gpd.read_file(args.zones)
        counties = gpd.read_file(args.counties)

    if Options.alerts in args.funcs:
        print("Getting Latest Alerts...")
        zone_alerts = get.get_active_alerts_from_zones(zones)
        county_alerts = get.get_active_alerts_from_zones(counties)

        get.save_zone_event_json(zone_alerts, Path("./data") / "first_alerts_zone.json")
        zone_alerts.to_csv(args.out_dir / "latest_alerts_zone.csv")

        get.save_zone_event_json(
            county_alerts, Path("./data") / "first_alerts_county.json"
        )
        county_alerts.to_csv(args.out_dir / "latest_alerts_county.csv")

    else:
        alerts = pd.read_csv(args.alert_file)

    if Options.templates in args.funcs:
        print("Making Template Files")
        template_dir = args.out_dir / "alert_pages"
        for f in template_dir.iterdir():
            if f.is_file():
                f.unlink()

        if len(zone_alerts) != 0:
            render_templates(
                latest_alerts=zone_alerts,
                templates=args.template_dir,
                out_dir=args.out_dir / "alert_pages",
                for_county=False,
            )

        if len(county_alerts) != 0:
            render_templates(
                latest_alerts=county_alerts,
                templates=args.template_dir,
                out_dir=args.out_dir / "alert_pages",
                for_county=True,
            )
