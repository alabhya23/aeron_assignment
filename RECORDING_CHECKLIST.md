# Three-Minute Recording Checklist

## Before recording
- Open Clipchamp on Windows and start a screen recording with microphone audio enabled.
- Have `checker.py`, `flags.csv`, `report.html`, and `DECISIONS.md` ready to show.
- Keep the data pack outside the project repository.

## Recording outline
- **0:00–0:30:** Introduce the project and explain that it screens weather-station data for quality issues.
- **0:30–1:15:** Show `checker.py` and briefly explain the range, duplicate, gap, constant-run, and GPS checks.
- **1:15–2:00:** Run `python .\checker.py "C:\Users\alabhya\Downloads\aeron-data"` and show the generated `flags.csv`.
- **2:00–2:40:** Explain the S05 humidity evidence and the unresolved S06 duplicate records, including why flags do not automatically invalidate a whole station.
- **2:40–3:00:** Show `report.html` and `DECISIONS.md`, then conclude.

## After recording
- Export the video and upload it to a service the reviewer can access.
- Test the share link in a private browser window.
- Add the final video URL to the first four lines of `README.md`.