import argparse
from enum import Enum
from pathlib import Path
import geopandas as gpd
import pandas as pd

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
        default="MT",
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
        "--template-dir",
        type=Path, 
        help="The path to the directory with templates for alerts.",
        default=Path("./templates"),
    )
    parser.add_argument(
        "--alert-file",
        type=Path,
        help="Path to .csv with the latest alerts",
        default=Path("./data/latest_alerts.csv")
    )

    args = parser.parse_args()

    print("Getting Zones...")
    if Options.zones in args.funcs:
        zones = get.get_zones(area=args.zone_id)
        get.save_zones(zones, args.out_dir / f"{args.zone_id}-zones.fgb".lower())

    else: 
        zones = gpd.read_file(args.zones)
    
    print("Getting Latest Alerts...")
    if Options.alerts in args.funcs:
        alerts = get.get_active_alerts_from_zones(zones)
        get.save_zone_event_json(
            alerts,
            args.out_dir / "first_alerts.json"
        )
        alerts.to_csv(
            args.out_dir / "latest_alerts.csv"
        )
    else:
        alerts = pd.read_csv(args.alert_file)
    
    print("Making Template Files")
    if Options.templates in args.funcs:
        render_templates(
            latest_alerts=alerts,
            templates = args.template_dir,
            out_dir=args.out_dir / "alert_pages"
        )