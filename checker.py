
#!/usr/bin/env python3
"""
Weather-station data quality checker.

Usage:
    python checker.py "C:\\path\\to\\data_pack"

Writes flags.csv to the current working directory.
Required dependency: pandas
"""


import argparse
import math
from pathlib import Path

import pandas as pd


OUTPUT_COLUMNS = [
    "station_id",
    "channel",
    "start_utc",
    "end_utc",
    "issue",
    "action",
    "note",
]

# Broad screening limits, not calibration specifications.
LIMITS = {
    "temp_c": (-60, 60),
    "rh_pct": (0, 100),
    "pressure_hpa": (300, 1100),
    "wind_kmh": (0, 200),
    "wind_dir_deg": (0, 360),
    "rain_mm": (0, 100),
    "ghi_wm2": (0, 1500),
}

# Constant runs are only review signals for these channels.
# Rainfall and solar irradiance are intentionally excluded:
# long runs of zero rain and nighttime zero sunlight are normal.
CONSTANT_RUN_CHANNELS = {
    "temp_c",
    "rh_pct",
    "pressure_hpa",
    "wind_kmh",
    "wind_dir_deg",
}

EXPECTED_INTERVAL_MINUTES = 10
GAP_THRESHOLD_MINUTES = 20
CONSTANT_RUN_MIN_RECORDS = 37


def format_timestamp(value):
    """Format a timestamp consistently for CSV output."""
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def add_flag(flags, station, channel, start, end, issue, action, note):
    """Append one flag using the required output schema."""
    flags.append({
        "station_id": station,
        "channel": channel,
        "start_utc": format_timestamp(start),
        "end_utc": format_timestamp(end),
        "issue": issue,
        "action": action,
        "note": note,
    })


def add_contiguous_flags(
    flags, station, channel, timestamps, issue, action, note
):
    """
    Group consecutive flagged samples into intervals when timestamps
    are separated by the expected sampling interval.
    """
    if not timestamps:
        return

    times = sorted(pd.Timestamp(t) for t in timestamps)
    run_start = times[0]
    previous = times[0]
    run_count = 1

    for current in times[1:]:
        elapsed = (current - previous).total_seconds() / 60

        if elapsed <= EXPECTED_INTERVAL_MINUTES:
            run_count += 1
        else:
            run_note = f"{note} Flagged samples in interval: {run_count}."
            add_flag(
                flags, station, channel, run_start, previous,
                issue, action, run_note
            )
            run_start = current
            run_count = 1

        previous = current

    run_note = f"{note} Flagged samples in interval: {run_count}."
    add_flag(
        flags, station, channel, run_start, previous,
        issue, action, run_note
    )


def check_weather_file(csv_path, station, flags):
    """Check timestamps and weather channels for one station."""
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        add_flag(
            flags, station, "all", None, None,
            "file_read_error", "keep",
            f"Could not read weather CSV: {exc}"
        )
        return

    required = ["timestamp_utc", *LIMITS.keys()]
    missing_columns = [col for col in required if col not in df.columns]

    if missing_columns:
        add_flag(
            flags, station, "all", None, None,
            "missing_columns", "keep",
            "Required columns missing: " + ", ".join(missing_columns)
        )
        return

    df["_original_row"] = range(len(df))
    df["_parsed_ts"] = pd.to_datetime(
        df["timestamp_utc"], errors="coerce", utc=True
    )

    # Invalid or unparseable timestamps.
    bad_ts = df["_parsed_ts"].isna()
    if bad_ts.any():
        add_flag(
            flags, station, "timestamp", None, None,
            "invalid_timestamp", "exclude",
            f"{int(bad_ts.sum())} rows have an invalid timestamp."
        )

    valid = df.loc[~bad_ts].copy()

    if valid.empty:
        return

    # Duplicate timestamps: distinguish exact duplicates from conflicting rows.
    duplicate_mask = valid["_parsed_ts"].duplicated(keep=False)
    duplicate_rows = valid.loc[duplicate_mask]

    if not duplicate_rows.empty:
        for timestamp, group in duplicate_rows.groupby("_parsed_ts"):
            channel_columns = list(LIMITS.keys())
            values = group[channel_columns].astype(str)
            exact_duplicate = not values.drop_duplicates().shape[0] > 1

            if exact_duplicate:
                issue = "duplicate_timestamp"
                action = "correct"
                note = (
                    f"{len(group)} rows share this timestamp and their "
                    "weather-channel values match. Retain one copy after "
                    "confirming the duplicate rows are truly redundant."
                )
            else:
                issue = "conflicting_duplicate_timestamp"
                action = "keep"
                note = (
                    f"{len(group)} rows share this timestamp but have "
                    "different channel values. Investigate before choosing "
                    "which record, if any, to remove."
                )

            add_flag(
                flags, station, "all", timestamp, timestamp,
                issue, action, note
            )

    # Sort timestamps for time-series checks.
    ordered = valid.sort_values("_parsed_ts").reset_index(drop=True)

    # Gaps between consecutive unique timestamps.
    unique_times = (
        ordered["_parsed_ts"].drop_duplicates().sort_values().reset_index(drop=True)
    )
    if len(unique_times) > 1:
        differences = unique_times.diff().dt.total_seconds().div(60)

        for index in range(1, len(unique_times)):
            gap_minutes = differences.iloc[index]
            if gap_minutes > GAP_THRESHOLD_MINUTES:
                previous_ts = unique_times.iloc[index - 1]
                current_ts = unique_times.iloc[index]
                add_flag(
                    flags, station, "all", previous_ts, current_ts,
                    "timestamp_gap", "keep",
                    f"Gap of {gap_minutes:g} minutes between records; "
                    "the missing period has no observed values to recover "
                    "from this file alone."
                )

    # Physical-range checks, grouped into contiguous intervals.
    for channel, (minimum, maximum) in LIMITS.items():
        numeric = pd.to_numeric(ordered[channel], errors="coerce")
        invalid_numeric = numeric.isna()
        outside = (numeric < minimum) | (numeric > maximum)

        if invalid_numeric.any():
            bad_times = ordered.loc[
                invalid_numeric, "_parsed_ts"
            ].tolist()
            add_contiguous_flags(
                flags, station, channel, bad_times,
                "non_numeric_or_missing_value", "keep",
                f"Missing or non-numeric values; expected numeric data. "
                "Inspect before imputing."
            )

        if outside.any():
            bad_times = ordered.loc[outside, "_parsed_ts"].tolist()
            add_contiguous_flags(
                flags, station, channel, bad_times,
                "outside_physical_range", "exclude",
                f"Values outside broad screening range [{minimum}, {maximum}]. "
                "Exclude affected channel samples unless a documented "
                "instrument-specific range justifies them."
            )

    # Long exact constant runs in selected channels only.
    # These are review flags, not automatic exclusions.
    unique_ordered = (
        ordered.drop_duplicates("_parsed_ts", keep="first")
        .sort_values("_parsed_ts")
        .reset_index(drop=True)
    )

    for channel in CONSTANT_RUN_CHANNELS:
        values = pd.to_numeric(unique_ordered[channel], errors="coerce")
        timestamps = unique_ordered["_parsed_ts"]

        run_start = 0
        run_length = 1

        for pos in range(1, len(unique_ordered)):
            same_value = (
                pd.notna(values.iloc[pos])
                and pd.notna(values.iloc[pos - 1])
                and values.iloc[pos] == values.iloc[pos - 1]
            )
            consecutive = (
                timestamps.iloc[pos] - timestamps.iloc[pos - 1]
            ).total_seconds() == EXPECTED_INTERVAL_MINUTES * 60

            if same_value and consecutive:
                run_length += 1
            else:
                if run_length >= CONSTANT_RUN_MIN_RECORDS:
                    add_flag(
                        flags, station, channel,
                        timestamps.iloc[run_start],
                        timestamps.iloc[pos - 1],
                        "long_constant_run", "keep",
                        f"Same value for {run_length} consecutive samples "
                        f"(at least about 6 hours). Review against other "
                        "channels and maintenance notes; constant values "
                        "can also occur naturally."
                    )
                run_start = pos
                run_length = 1

        if run_length >= CONSTANT_RUN_MIN_RECORDS:
            add_flag(
                flags, station, channel,
                timestamps.iloc[run_start],
                timestamps.iloc[len(unique_ordered) - 1],
                "long_constant_run", "keep",
                f"Same value for {run_length} consecutive samples "
                f"(at least about 6 hours). Review against other channels "
                "and maintenance notes; constant values can also occur "
                "naturally."
            )


def nmea_to_decimal(raw_value, hemisphere):
    """Convert an NMEA latitude/longitude field to decimal degrees."""
    if not raw_value:
        return None

    try:
        number = float(raw_value)
        degrees = math.floor(number / 100)
        minutes = number - degrees * 100
        decimal = degrees + minutes / 60

        if hemisphere in ("S", "W"):
            decimal = -decimal
        elif hemisphere not in ("N", "E"):
            return None

        return decimal
    except (TypeError, ValueError):
        return None


def check_gps_file(gps_path, station, flags):
    """
    Basic GPS review:
    - missing file
    - invalid RMC navigation status
    - position spread that merits inspection

    GPS cadence is not assumed to match the 10-minute weather cadence.
    """
    if not gps_path.exists():
        add_flag(
            flags, station, "gps", None, None,
            "gps_file_missing", "keep",
            f"Expected GPS file not found: {gps_path.name}"
        )
        return

    parsed_positions = []
    invalid_status_times = []

    try:
        lines = gps_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except Exception as exc:
        add_flag(
            flags, station, "gps", None, None,
            "gps_file_read_error", "keep",
            f"Could not read GPS file: {exc}"
        )
        return

    for line in lines:
        # Pack lines start with a timestamp, then a comma, then NMEA.
        if "," not in line:
            continue

        prefix, sentence = line.split(",", 1)
        if not sentence.startswith(("$GPRMC", "$GNRMC")):
            continue

        fields = sentence.split(",")

        try:
            gps_time = pd.to_datetime(prefix, errors="coerce", utc=True)
        except Exception:
            gps_time = pd.NaT

        if len(fields) < 7:
            if pd.notna(gps_time):
                invalid_status_times.append(gps_time)
            continue

        status = fields[2].strip()

        if status != "A":
            if pd.notna(gps_time):
                invalid_status_times.append(gps_time)
            continue

        latitude = nmea_to_decimal(fields[3], fields[4].strip())
        longitude = nmea_to_decimal(fields[5], fields[6].strip())

        if latitude is None or longitude is None:
            if pd.notna(gps_time):
                invalid_status_times.append(gps_time)
            continue

        if pd.notna(gps_time):
            parsed_positions.append((gps_time, latitude, longitude))

    if invalid_status_times:
        add_contiguous_flags(
            flags, station, "gps", invalid_status_times,
            "invalid_gps_fix", "keep",
            "GPS RMC record has invalid navigation status or unusable "
            "coordinates. Check neighbouring GPS records before excluding "
            "any associated weather data."
        )

    if len(parsed_positions) >= 3:
        lats = pd.Series([p[1] for p in parsed_positions])
        lons = pd.Series([p[2] for p in parsed_positions])
        median_lat = float(lats.median())
        median_lon = float(lons.median())

        # Approximate coordinate spread threshold (~2 km latitude-wise).
        # This is a review threshold, not proof that a station moved.
        spread = []
        for timestamp, lat, lon in parsed_positions:
            distance_approx_km = math.sqrt(
                ((lat - median_lat) * 111.0) ** 2
                + ((lon - median_lon) * 111.0
                   * math.cos(math.radians(median_lat))) ** 2
            )
            if distance_approx_km > 2.0:
                spread.append((timestamp, distance_approx_km))

        if spread:
            start = min(item[0] for item in spread)
            end = max(item[0] for item in spread)
            add_flag(
                flags, station, "gps", start, end,
                "gps_position_spread", "keep",
                f"{len(spread)} valid GPS fixes are more than approximately "
                "2 km from the file's median position. Inspect station "
                "metadata and individual fixes; GPS jitter or bad fixes "
                "can mimic movement."
            )


def main():
    parser = argparse.ArgumentParser(
        description="Check weather station CSVs and GPS files."
    )
    parser.add_argument(
        "data_pack",
        help="Path to the extracted data-pack folder."
    )
    args = parser.parse_args()

    data_root = Path(args.data_pack).expanduser().resolve()
    data_dir = data_root / "data"
    gps_dir = data_root / "gps"

    if not data_root.exists():
        parser.error(f"Data-pack folder does not exist: {data_root}")

    if not data_dir.is_dir():
        parser.error(f"Expected a 'data' folder inside: {data_root}")

    station_files = sorted(data_dir.glob("S*.csv"))
    if not station_files:
        parser.error(f"No station CSV files found in: {data_dir}")

    flags = []

    for csv_path in station_files:
        station = csv_path.stem
        check_weather_file(csv_path, station, flags)
        check_gps_file(gps_dir / f"{station}.nmea", station, flags)

    result = pd.DataFrame(flags, columns=OUTPUT_COLUMNS)
    output_path = Path.cwd() / "flags.csv"
    result.to_csv(output_path, index=False)

    print(f"Checked {len(station_files)} station files.")
    print(f"Wrote {len(result)} flags to {output_path.resolve()}")

    if result.empty:
        print("No issues were flagged.")
    else:
        print("\nFlag counts by issue:")
        print(
            result.groupby("issue")
            .size()
            .sort_values(ascending=False)
            .to_string()
        )
        print("\nFlag counts by action:")
        print(
            result.groupby("action")
            .size()
            .sort_values(ascending=False)
            .to_string()
        )


if __name__ == "__main__":
    main()
