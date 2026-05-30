#!/bin/bash
# EdgeHub build script for Raspberry Pi
# Usage: ./build.sh [--clean]

set -e

cd "$(dirname "$0")"

BUILD_DIR="build"

if [ "$1" = "--clean" ]; then
    rm -rf "$BUILD_DIR"
    echo "Cleaned build directory."
fi

# Check for mongoose
MONGOOSE_DIR="third_party/mongoose"
if [ ! -f "$MONGOOSE_DIR/mongoose.c" ] || [ ! -f "$MONGOOSE_DIR/mongoose.h" ]; then
    echo "=== Downloading Mongoose ==="
    mkdir -p "$MONGOOSE_DIR"
    curl -sL "https://raw.githubusercontent.com/cesanta/mongoose/master/mongoose.h" -o "$MONGOOSE_DIR/mongoose.h"
    curl -sL "https://raw.githubusercontent.com/cesanta/mongoose/master/mongoose.c" -o "$MONGOOSE_DIR/mongoose.c"
    echo "Mongoose downloaded to $MONGOOSE_DIR/"
fi

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

echo ""
echo "Build complete: $BUILD_DIR/edgehub"
echo "Run: ./edgehub"
