#!/bin/sh

# This script allows for easy testing of the conversion commands built into
# imagepipe without the hassle of firing up the service

usage() {
    echo "Usage: $0 input output resize|composite|crop width height"
}

if [ $# -lt 5 ]; then
    usage
    exit 1
fi

I="$1"
O="$2"
T="$3"
W="$4"
H="$5"

RESIZE="convert $I -resize ${W}x${H}> ${O}"
COMPOSITE="convert -size ${W}x${H} xc:none null: $I -resize ${W}x${H}> -gravity center -layers composite ${O}"
CROP="convert $I -resize ${W}x${H}^ -gravity center -crop ${W}x${H}+0+0! +repage ${O}"

if [ "$T" = "resize" ]; then
    echo "$RESIZE"
    $RESIZE
elif [ "$T" = "composite" ]; then
    echo "$COMPOSITE"
    $COMPOSITE
elif [ "$T" = "crop" ]; then
    echo "$CROP"
    $CROP
else
    usage
    exit 1
fi
