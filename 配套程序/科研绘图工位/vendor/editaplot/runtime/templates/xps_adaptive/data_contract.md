# XPS Adaptive Data Contract

The public XPS workflow accepts cleaned CSV, TXT, XLS, and XLSX tables with
variable numeric columns. TXT delimiters may be comma, Tab, or semicolon; Excel
loading uses the first non-empty worksheet.

Required:
- At least two numeric columns.
- One explicitly identified energy column. Binding and kinetic energy are distinct
  coordinate conventions; a generic `Energy` title alone does not identify which.
- At least one intensity-like Y column.

Recognized optional columns:
- Raw intensity: `Raw`, `Counts / s`, `Intensity`, `Experimental`.
- Background: `Background`, `Backgnd.`, `BG`, `Baseline`.
- Envelope: `Envelope`, `Fit`, `Fit Total`, `Total`.
- Residuals: `Residuals`, `Residual`.
- Other numeric columns need confirmed component/series/ignored roles. Numeric
  shape or a monotonic column alone is not proof of scientific meaning.

The template does not add missing peak columns or alter source values. Temporary
Origin worksheet helper columns such as `PlotX` are generated only inside the
Origin project so the source table remains an auditable copy of the measured data.
Fill-baseline helper columns are also Origin-only. Raw curves and component/series
curves fill to the detected background column when it exists; otherwise they fill
to the automatically computed Y-axis floor. These helper columns must never be
written back into the user's cleaned input file.

Residual columns are recognized as residual diagnostics. They are preserved in
the Origin worksheet and verification report, but they are not plotted on the
main counts axis by default because their scale is not comparable with raw
counts, background, envelope, or component curves.

## Instrument-workbook preprocessing notes

Instrument workbooks may contain
metadata, titles, empty spacer columns, and plot objects before the numeric table.
They must first be reduced to one clean rectangular spectrum table; the cleaned
result may remain XLS/XLSX or be saved as CSV/TXT:

- Treat each measured-spectrum sheet as one input table; preserve its spectrum name
  in the file or worksheet name.
- Skip index/empty sheets such as `Titles` and `Sheet1`.
- Determine semantic header/unit/data rows from the specific workbook. Historical
  row 15/16/17 examples are not an instrument-independent parsing rule.
- Keep only columns that contain numeric data rows. Drop spacer columns and
  acquisition-parameter text.
- Do not create missing peaks, do not normalize values, and do not write helper
  columns into the cleaned input.
- Use the current `prepare_xps` mapping and energy-kind plan. The normal adaptive
  runner already consumes that preparation and distinguishes kinetic from binding
  energy. Do not use the legacy monotonic fallback or its default title as evidence
  for relabelling. Changing coordinate convention requires numerical conversion,
  known photon energy and the applicable reference/calibration convention; preserve
  the original column, conversion evidence and resulting coordinates.
