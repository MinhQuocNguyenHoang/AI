#!/usr/bin/env python3
"""Create task-specific, traceable CSV files from the paper's figure data.

The source files are figure-oriented: several unrelated tables can be placed
side-by-side and some figures repeat data from earlier figures.  This script
extracts only the canonical observations for each downstream task and keeps
source row/panel metadata so every output value can be traced back.

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import re
from pathlib import Path
from typing import Iterable, Sequence


MMOL_L_TO_MG_DL = 18.0182

PAIR_FIELDS = [
    "pair_id",
    "population",
    "subject_id",
    "session_id",
    "session_day",
    "flow_rate_ul_min",
    "blood_glucose_mmol_l",
    "blood_glucose_mg_dl",
    "skin_glucose_umol_l",
    "skin_glucose_sd_umol_l",
    "sample_collection_period",
    "blood_measurement_time",
    "source_file",
    "source_panel",
    "source_row",
]


def read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def value_at(row: Sequence[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def converted_mg_dl(mmol_l: float) -> float:
    return round(mmol_l * MMOL_L_TO_MG_DL, 6)


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def extract_figure2(raw_dir: Path, output_dir: Path) -> dict[str, int]:
    """Extract summarized calibration, LOD and unpaired glucose distributions."""
    source = raw_dir / "Figure2.csv"
    rows = read_csv(source)

    calibration = []
    calibration_columns = {
        "glucose": (2, 3, 4),
        "lactate": (7, 8, 9),
    }
    for sensor_type, (concentration_col, current_col, sd_col) in calibration_columns.items():
        sensor_code = sensor_type[0].upper()
        for source_row, row in enumerate(rows[3:], start=4):
            concentration = maybe_float(value_at(row, concentration_col))
            mean_current = maybe_float(value_at(row, current_col))
            current_sd = maybe_float(value_at(row, sd_col))
            if concentration is None:
                continue
            if mean_current is None or current_sd is None:
                raise ValueError(f"Incomplete Figure2 calibration at source row {source_row}")
            calibration.append(
                {
                    "calibration_id": f"{sensor_code}{len([x for x in calibration if x['sensor_type'] == sensor_type]) + 1:03d}",
                    "sensor_type": sensor_type,
                    "concentration_umol_l": concentration,
                    "mean_current_pa": mean_current,
                    "current_sd_pa": current_sd,
                    "source_file": source.name,
                    "source_panel": "calibration",
                    "source_row": source_row,
                }
            )

    lod = []
    lod_columns = {
        "glucose": (20, 21),
        "lactate": (22, 23),
    }
    for sensor_type, (lod_col, sd_col) in lod_columns.items():
        sensor_index = 0
        for source_row, row in enumerate(rows[3:], start=4):
            lod_value = maybe_float(value_at(row, lod_col))
            lod_sd = maybe_float(value_at(row, sd_col))
            if lod_value is None:
                continue
            sensor_index += 1
            lod.append(
                {
                    "sensor_type": sensor_type,
                    "sensor_index": sensor_index,
                    "lod_umol_l": lod_value,
                    "lod_sd_umol_l": lod_sd if lod_sd is not None else "",
                    "source_file": source.name,
                    "source_panel": "limit_of_detection",
                    "source_row": source_row,
                }
            )

    distributions = []
    distribution_columns = [
        ("skin", 26, "umol_l"),
        ("blood", 30, "mmol_l"),
    ]
    for matrix, column, unit in distribution_columns:
        sample_index = 0
        for source_row, row in enumerate(rows[2:], start=3):
            concentration = maybe_float(value_at(row, column))
            if concentration is None:
                continue
            sample_index += 1
            distributions.append(
                {
                    "sample_id": f"{matrix[0].upper()}{sample_index:03d}",
                    "matrix": matrix,
                    "analyte": "glucose",
                    "concentration": concentration,
                    "unit": unit,
                    "is_blood_skin_pair": 0,
                    "source_file": source.name,
                    "source_panel": "glucose_distribution",
                    "source_row": source_row,
                }
            )

    if len(calibration) != 6:
        raise ValueError(f"Expected 6 Figure2 calibration points, found {len(calibration)}")
    if len(lod) != 16:
        raise ValueError(f"Expected 16 Figure2 LOD observations, found {len(lod)}")
    skin_count = sum(row["matrix"] == "skin" for row in distributions)
    blood_count = sum(row["matrix"] == "blood" for row in distributions)
    if (skin_count, blood_count) != (224, 17):
        raise ValueError(
            f"Expected 224 skin and 17 blood distributions, found {skin_count} and {blood_count}"
        )

    counts = {}
    counts["Figure2_calibration_cleaned.csv"] = write_csv(
        output_dir / "Figure2_calibration_cleaned.csv",
        [
            "calibration_id",
            "sensor_type",
            "concentration_umol_l",
            "mean_current_pa",
            "current_sd_pa",
            "source_file",
            "source_panel",
            "source_row",
        ],
        calibration,
    )
    counts["Figure2_lod_cleaned.csv"] = write_csv(
        output_dir / "Figure2_lod_cleaned.csv",
        [
            "sensor_type",
            "sensor_index",
            "lod_umol_l",
            "lod_sd_umol_l",
            "source_file",
            "source_panel",
            "source_row",
        ],
        lod,
    )
    counts["Figure2_glucose_distributions_cleaned.csv"] = write_csv(
        output_dir / "Figure2_glucose_distributions_cleaned.csv",
        [
            "sample_id",
            "matrix",
            "analyte",
            "concentration",
            "unit",
            "is_blood_skin_pair",
            "source_file",
            "source_panel",
            "source_row",
        ],
        distributions,
    )
    return counts


def extract_neonate_pairs(raw_dir: Path) -> list[dict]:
    source = raw_dir / "Figure3.csv"
    rows = read_csv(source)
    pairs = []
    for source_row, row in enumerate(rows[2:], start=3):
        blood = maybe_float(value_at(row, 22))
        skin = maybe_float(value_at(row, 23))
        skin_sd = maybe_float(value_at(row, 24))
        if blood is None and skin is None:
            continue
        if blood is None or skin is None or skin_sd is None:
            raise ValueError(f"Incomplete neonatal pair at {source}:{source_row}")
        pairs.append(
            {
                "pair_id": f"N{len(pairs) + 1:03d}",
                "population": "neonate",
                # Figure3C reports 17 samples from 15 babies but does not map rows to babies.
                "subject_id": "",
                "session_id": "",
                "session_day": "",
                "flow_rate_ul_min": 0.5,
                "blood_glucose_mmol_l": blood,
                "blood_glucose_mg_dl": converted_mg_dl(blood),
                "skin_glucose_umol_l": skin,
                "skin_glucose_sd_umol_l": skin_sd,
                "sample_collection_period": "",
                "blood_measurement_time": "",
                "source_file": source.name,
                "source_panel": "Figure3C",
                "source_row": source_row,
            }
        )
    if len(pairs) != 17:
        raise ValueError(f"Expected 17 neonatal pairs, found {len(pairs)}")
    return pairs


ADULT_SECTION_RE = re.compile(r"^Adult\s+(?P<subject>\d+)(?:\s+Day\s+(?P<day>\d+))?$")


def extract_adult_pairs(raw_dir: Path) -> list[dict]:
    source = raw_dir / "Figure4.csv"
    rows = read_csv(source)
    pairs = []
    section: re.Match[str] | None = None

    for source_row, row in enumerate(rows[1:], start=2):
        first = value_at(row, 0)
        match = ADULT_SECTION_RE.match(first)
        if match:
            section = match
            continue

        blood = maybe_float(first)
        skin = maybe_float(value_at(row, 1))
        skin_sd = maybe_float(value_at(row, 2))
        if blood is None and skin is None:
            continue
        if section is None:
            raise ValueError(f"Adult data before section header at {source}:{source_row}")
        if blood is None or skin is None or skin_sd is None:
            raise ValueError(f"Incomplete adult pair at {source}:{source_row}")

        subject_number = int(section.group("subject"))
        day_text = section.group("day")
        session_day: int | str = int(day_text) if day_text is not None else ""
        session_id = f"day_{session_day}" if day_text is not None else "single_session"
        pairs.append(
            {
                "pair_id": f"A{len(pairs) + 1:03d}",
                "population": "adult",
                "subject_id": f"adult_{subject_number}",
                "session_id": session_id,
                "session_day": session_day,
                "flow_rate_ul_min": 0.5,
                "blood_glucose_mmol_l": blood,
                "blood_glucose_mg_dl": converted_mg_dl(blood),
                "skin_glucose_umol_l": skin,
                "skin_glucose_sd_umol_l": skin_sd,
                "sample_collection_period": value_at(row, 3),
                "blood_measurement_time": value_at(row, 4),
                "source_file": source.name,
                "source_panel": "Figure4",
                "source_row": source_row,
            }
        )

    if len(pairs) != 54:
        raise ValueError(f"Expected 54 adult pairs, found {len(pairs)}")
    if len({row["subject_id"] for row in pairs}) != 7:
        raise ValueError("Expected 7 unique adult subjects")
    return pairs


def extract_figure6(raw_dir: Path, output_dir: Path) -> dict[str, int]:
    source = raw_dir / "Figure6.csv"
    rows = read_csv(source)
    cleaned = []
    for source_row, row in enumerate(rows[2:], start=3):
        flow_rate = maybe_float(value_at(row, 3))
        if flow_rate is None:
            continue
        candidate_flow_columns = (8, 13, 18, 23)
        for column in candidate_flow_columns:
            repeated_flow = maybe_float(value_at(row, column))
            if repeated_flow is None or abs(repeated_flow - flow_rate) > 1e-12:
                raise ValueError(f"Figure6 flow columns disagree at source row {source_row}")
        cleaned.append(
            {
                "flow_rate_ul_min": flow_rate,
                "in_vitro_glucose_umol_l": maybe_float(value_at(row, 4)),
                "in_vitro_glucose_sd_umol_l": maybe_float(value_at(row, 5)),
                "in_vitro_glucose_removed_umol_min": maybe_float(value_at(row, 9)),
                "on_skin_glucose_removed_umol_min": maybe_float(value_at(row, 10)),
                "on_skin_glucose_umol_l": maybe_float(value_at(row, 14)),
                "on_skin_glucose_sd_umol_l": maybe_float(value_at(row, 15)),
                "in_vitro_recovery_pct": maybe_float(value_at(row, 19)),
                "collection_time_min": maybe_float(value_at(row, 20)),
                "on_skin_recovery_pct": maybe_float(value_at(row, 24)),
                "delay_time_min": maybe_float(value_at(row, 25)),
                "source_file": source.name,
                "source_panels": "Figure6B-F",
                "source_row": source_row,
            }
        )
    if len(cleaned) != 5:
        raise ValueError(f"Expected 5 Figure6 flow conditions, found {len(cleaned)}")
    fields = [
        "flow_rate_ul_min",
        "in_vitro_glucose_umol_l",
        "in_vitro_glucose_sd_umol_l",
        "in_vitro_glucose_removed_umol_min",
        "on_skin_glucose_removed_umol_min",
        "on_skin_glucose_umol_l",
        "on_skin_glucose_sd_umol_l",
        "in_vitro_recovery_pct",
        "collection_time_min",
        "on_skin_recovery_pct",
        "delay_time_min",
        "source_file",
        "source_panels",
        "source_row",
    ]
    return {
        "Figure6_cleaned.csv": write_csv(
            output_dir / "Figure6_cleaned.csv", fields, cleaned
        )
    }


def nearest_index(sorted_times: Sequence[float], target: float) -> int:
    insertion = bisect.bisect_left(sorted_times, target)
    candidates = []
    if insertion < len(sorted_times):
        candidates.append(insertion)
    if insertion > 0:
        candidates.append(insertion - 1)
    return min(candidates, key=lambda index: abs(sorted_times[index] - target))


def extract_continuous(
    raw_dir: Path,
    output_dir: Path,
    figure_number: int,
) -> dict[str, int]:
    if figure_number not in (7, 8):
        raise ValueError("Continuous extraction supports only Figure7 and Figure8")

    source = raw_dir / f"Figure{figure_number}.csv"
    rows = read_csv(source)
    signals = []
    references = []
    paired_values = []

    for source_row, row in enumerate(rows[2:], start=3):
        time_hr = maybe_float(value_at(row, 0))
        raw_skin = maybe_float(value_at(row, 1))
        filtered_skin = maybe_float(value_at(row, 2))
        if time_hr is not None:
            if raw_skin is None or filtered_skin is None:
                raise ValueError(f"Incomplete continuous signal at {source}:{source_row}")
            signals.append(
                {
                    "sample_index": len(signals),
                    "time_hr": time_hr,
                    "skin_glucose_raw_umol_l": raw_skin,
                    "skin_glucose_filtered_umol_l": filtered_skin,
                    "source_signal_row": source_row,
                }
            )

        blood_time = maybe_float(value_at(row, 3))
        blood_glucose = maybe_float(value_at(row, 4))
        if blood_time is not None or blood_glucose is not None:
            if blood_time is None or blood_glucose is None:
                raise ValueError(f"Incomplete blood reference at {source}:{source_row}")
            references.append((blood_time, blood_glucose, source_row))

        if figure_number == 7:
            paired_blood = maybe_float(value_at(row, 7))
            paired_skin = maybe_float(value_at(row, 8))
            paired_sd = maybe_float(value_at(row, 9))
            if paired_blood is not None or paired_skin is not None:
                if paired_blood is None or paired_skin is None or paired_sd is None:
                    raise ValueError(f"Incomplete Figure7 paired value at source row {source_row}")
                paired_values.append((paired_blood, paired_skin, paired_sd, source_row))
        else:
            # Columns 7-9 repeat the 17 offline Figure3 points.  Columns 10-11
            # contain the single online Figure8 observation.
            paired_blood = maybe_float(value_at(row, 10))
            paired_skin = maybe_float(value_at(row, 11))
            if paired_blood is not None or paired_skin is not None:
                if paired_blood is None or paired_skin is None:
                    raise ValueError(f"Incomplete Figure8 online pair at source row {source_row}")
                paired_values.append((paired_blood, paired_skin, None, source_row))

    expected_references = 9 if figure_number == 7 else 1
    expected_signals = 65049 if figure_number == 7 else 80604
    if len(signals) != expected_signals:
        raise ValueError(
            f"Expected {expected_signals} Figure{figure_number} signal samples, found {len(signals)}"
        )
    if len(references) != expected_references or len(paired_values) != expected_references:
        raise ValueError(
            f"Expected {expected_references} Figure{figure_number} blood references, "
            f"found {len(references)} references and {len(paired_values)} paired values"
        )

    times = [row["time_hr"] for row in signals]
    if times != sorted(times):
        raise ValueError(f"Figure{figure_number} time series is not monotonically increasing")

    markers = {}
    for reference_index, ((blood_time, blood, reference_source_row), paired) in enumerate(
        zip(references, paired_values), start=1
    ):
        paired_blood, paired_skin, paired_sd, pair_source_row = paired
        if abs(blood - paired_blood) > 1e-9:
            raise ValueError(
                f"Figure{figure_number} blood reference and paired table disagree at item {reference_index}"
            )
        signal_index = nearest_index(times, blood_time)
        if signal_index in markers:
            raise ValueError(f"Two blood references mapped to sample {signal_index}")
        markers[signal_index] = {
            "reference_id": f"F{figure_number}R{reference_index:02d}",
            "blood_reference_time_hr": blood_time,
            "blood_glucose_mmol_l": blood,
            "blood_glucose_mg_dl": converted_mg_dl(blood),
            "paired_skin_glucose_umol_l": paired_skin,
            "paired_skin_glucose_sd_umol_l": paired_sd if paired_sd is not None else "",
            "reference_time_error_s": round(abs(times[signal_index] - blood_time) * 3600, 6),
            "source_reference_row": reference_source_row,
            "source_pair_row": pair_source_row,
        }

    population = "adult" if figure_number == 7 else "neonate"
    subject_id = "adult_online_1" if figure_number == 7 else "neonate_online_1"
    cleaned = []
    for signal_index, signal in enumerate(signals):
        marker = markers.get(signal_index)
        cleaned.append(
            {
                "sample_index": signal["sample_index"],
                "time_hr": signal["time_hr"],
                "skin_glucose_raw_umol_l": signal["skin_glucose_raw_umol_l"],
                "skin_glucose_filtered_umol_l": signal["skin_glucose_filtered_umol_l"],
                "is_blood_reference": int(marker is not None),
                "reference_id": marker["reference_id"] if marker else "",
                "blood_reference_time_hr": marker["blood_reference_time_hr"] if marker else "",
                "blood_glucose_mmol_l": marker["blood_glucose_mmol_l"] if marker else "",
                "blood_glucose_mg_dl": marker["blood_glucose_mg_dl"] if marker else "",
                "paired_skin_glucose_umol_l": marker["paired_skin_glucose_umol_l"] if marker else "",
                "paired_skin_glucose_sd_umol_l": marker["paired_skin_glucose_sd_umol_l"] if marker else "",
                "reference_time_error_s": marker["reference_time_error_s"] if marker else "",
                "flow_rate_ul_min": 0.3,
                "population": population,
                "subject_id": subject_id,
                "source_file": source.name,
                "source_signal_panel": f"Figure{figure_number}A",
                "source_pair_panel": f"Figure{figure_number}B",
                "source_signal_row": signal["source_signal_row"],
                "source_reference_row": marker["source_reference_row"] if marker else "",
                "source_pair_row": marker["source_pair_row"] if marker else "",
            }
        )

    fields = [
        "sample_index",
        "time_hr",
        "skin_glucose_raw_umol_l",
        "skin_glucose_filtered_umol_l",
        "is_blood_reference",
        "reference_id",
        "blood_reference_time_hr",
        "blood_glucose_mmol_l",
        "blood_glucose_mg_dl",
        "paired_skin_glucose_umol_l",
        "paired_skin_glucose_sd_umol_l",
        "reference_time_error_s",
        "flow_rate_ul_min",
        "population",
        "subject_id",
        "source_file",
        "source_signal_panel",
        "source_pair_panel",
        "source_signal_row",
        "source_reference_row",
        "source_pair_row",
    ]
    filename = f"Figure{figure_number}_cleaned.csv"
    return {filename: write_csv(output_dir / filename, fields, cleaned)}


def validate_pairs(neonates: list[dict], adults: list[dict]) -> None:
    if {row["pair_id"] for row in neonates} & {row["pair_id"] for row in adults}:
        raise ValueError("Pair IDs overlap")
    for row in neonates + adults:
        if row["blood_glucose_mmol_l"] <= 0 or row["skin_glucose_umol_l"] < 0:
            raise ValueError(f"Non-physiological negative value in {row['pair_id']}")
        expected = converted_mg_dl(row["blood_glucose_mmol_l"])
        if row["blood_glucose_mg_dl"] != expected:
            raise ValueError(f"Unit conversion failed for {row['pair_id']}")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=repo_root / "dataset" / "dienhoa_gucose",
        help="Directory containing the original Figure*.csv files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "dataset" / "cleaned",
        help="Directory for cleaned CSV files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_dir = args.raw_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Raw dataset directory not found: {raw_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    counts.update(extract_figure2(raw_dir, output_dir))

    neonates = extract_neonate_pairs(raw_dir)
    adults = extract_adult_pairs(raw_dir)
    validate_pairs(neonates, adults)
    counts["Figure3_cleaned.csv"] = write_csv(
        output_dir / "Figure3_cleaned.csv", PAIR_FIELDS, neonates
    )
    counts["Figure4_cleaned.csv"] = write_csv(
        output_dir / "Figure4_cleaned.csv", PAIR_FIELDS, adults
    )
    counts["cleaned_pairs.csv"] = write_csv(
        output_dir / "cleaned_pairs.csv", PAIR_FIELDS, neonates + adults
    )

    counts.update(extract_figure6(raw_dir, output_dir))
    counts.update(extract_continuous(raw_dir, output_dir, 7))
    counts.update(extract_continuous(raw_dir, output_dir, 8))

    print(f"Cleaned data written to: {output_dir}")
    for filename, count in counts.items():
        print(f"  {filename}: {count:,} data rows")


if __name__ == "__main__":
    main()
