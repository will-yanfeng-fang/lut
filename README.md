# LUT Photo Processor

A lightweight HTML app for applying LUT (Look-Up Table) color grading to photos — no heavy software like DaVinci Resolve required.

## Background

DaVinci Resolve is overkill just for applying a LUT to still photos. Mobile apps exist, but aren't suitable for professional shooters. This tool lets you batch-process an unlimited number of photos at once and walk away — just like dropping off a roll of film.

## Setup

1. Place `lut.py`, your `.cube` LUT file(s), and your photos into a directory of your choice.
2. Open the `.html` file and update **lines 93–95** with your working directory path.

## Usage

1. Open the HTML file in your browser.
2. Pick the LUT you want to apply.
3. Generate the command to apply the LUT to your photos.
4. Run the command — then go do your own thing while it processes.

## Why Use This?

| Problem | This App |
|---|---|
| DaVinci Resolve is too heavy for stills | This runs in any browser |
| Phone apps aren't for professionals | This does desktop-based workflow |
| Want to process many photos at once | This batch process unlimited photos |
| Don't want to babysit the process | Just fire and forget |
