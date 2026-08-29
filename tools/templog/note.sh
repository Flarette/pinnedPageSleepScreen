#!/bin/sh
# note.sh <text> — log a manual observation (ambient temp, location, activity)
# as a sample row with event "note:<text>" so it lands inline with the data.
# Example: ./note.sh "ambient 24.5C desk"
TXT=$(echo "$*" | tr ',' ';')
/home/root/templog/templog.sh "note:$TXT"
