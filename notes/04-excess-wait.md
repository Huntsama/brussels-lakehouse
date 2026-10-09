# Measuring punctuality: Excess Wait Time

For frequent services, people don't follow the timetable, they just turn up. TfL measures those services with
Excess Wait Time:

- Actual wait (AWT): at a random moment, minutes until the next vehicle. Our 15-min
  snapshots are those random moments, so we take the minimum `minutes_until` per stop/line/snapshot and average it.
- Scheduled wait (SWT): `sum(h²) / (2·sum(h))` over the timetable headways `h` in that hour.
  Irregular gaps make the scheduled wait longer than half the headway.
- EWT = AWT − SWT. Computed per stop, line and hour, then the city-wide median.
