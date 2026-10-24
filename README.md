Full name: Alabhya Sharma
Email: alabhya.sharma.btech2023@sitpune.edu.in
Video: https://drive.google.com/file/d/15817HdFhw9ZogNwr3PXB77i1zZcKQfSN/view?usp=sharing
Run: `python checker.py "C:\path\to\data-pack"`

# Aeron AI - Weather Data Quality Checker

**Program:** BTech (AIML), final year  
**Institute:** Symbiosis Institute of Technology, Pune

## Purpose

This program screens weather-station CSV data and GPS records for data-quality issues. It writes `flags.csv` to the current working directory and does not modify the supplied raw data.

## Requirements

- Python 3
- pandas

Install the dependency with:

```powershell
python -m pip install pandas
```

## Run

From the project folder, pass the path to the extracted data-pack directory:

```powershell
python .\checker.py "C:\path\to\data-pack"
```

The data-pack folder must contain the expected `data` and `gps` folders. The checker writes `flags.csv` in the current project directory.

## Output

The CSV columns are `station_id`, `channel`, `start_utc`, `end_utc`, `issue`, `action`, and `note`. Action values are `exclude`, `correct`, or `keep`.

## Limitations

Flags are rule-based screening results, not a guarantee that unflagged readings are accurate. Conflicting duplicates, long constant runs, and GPS void statuses may require human review. Raw input data is not changed.