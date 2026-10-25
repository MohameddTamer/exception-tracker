# Design, Exception Tracker board

## Concept

Today's exceptions are not a list; they are the station's wall chart. The
report is an engineering drawing: shipments plotted as nodes inside the
zones they are actually stuck in, routes drawn from each exception to its
courier and on to the station, and the sheet closed by a title block in the
corner, like a real drawing. The reader reads geography first and paragraphs
second, which is how a station manager already thinks at the morning review.

## Palette

- Blueprint ground: `#123A6B`, on a deeper surround `#0C2A50`
- Line work: white, full strength for structure, 55% for zone frames,
  12% for the 25-unit drawing grid
- Muted callout blue (coordinates, metadata, rules): `#BFD4F2`
- Signal orange `#FF7A1A`: exceptions only, node fill, act-today tallies,
  the compass needle, the hover state. If a shipment is moving normally it
  never touches orange.

## Type

**Space Grotesk** for zone names and headings, a technical grotesk with a
draughtsman's confidence. **IBM Plex Mono** for everything a drawing would
stamp: tracking ids, coordinates beside each node, courier callouts, the
title block. Tabular numerals everywhere; coordinates are set from the node's
real plotted position, because on a drawing a callout that lies is worse than
no callout.

## Signature move

The routes draw themselves. On load, each exception's route line strokes in
from node to courier to station, staggered by zone, in about half a second,
then the board is still. Hover any exception node and its route turns signal
orange while the rest of the board dims to a third: the eye is led, not told.
The interaction is pure CSS (the board dims via `:has()`), the report stays a
single file with no JavaScript, and under `prefers-reduced-motion` every
route is simply present.

Position is data, enforced: zones come from the input file, nodes sit inside
their own zone, and a node that could be moved without lying about the
shipment does not ship. Shipments without zone data plot in an "Unzoned"
region and their routes run straight to the station, the drawing admits
what it does not know.

## Deliberate avoidances

- No list-first layout and no bar chart of action types; the tallies live in
  the title block where a drawing keeps its metadata.
- No cards, no radius, no shadows on the sheet, frames are 1px line work.
- No random scatter. Clusters are zones, lines are routes, the centre is the
  station; every coordinate is earned.
- No colour beyond the drawing's own logic: white lines, one muted blue for
  annotations, orange only where a human must act today.
