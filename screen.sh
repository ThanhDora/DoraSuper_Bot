#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
SCREEN_NAME="dorasuper"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -d "$VENV_DIR" ] || [ ! -f "config.env" ]; then
    echo -e "${RED}Chạy ./run.sh trước để setup${NC}"
    exit 1
fi

screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
screen -dmS "$SCREEN_NAME" bash -c "
    cd $SCRIPT_DIR &&
    source $VENV_DIR/bin/activate &&
    python -m dorasuper &&
    echo '=== BOT ĐÃ DỪNG ==='
"

echo -e "${GREEN}BOT MỚI ĐÃ TREO THÀNH CÔNG${NC}"
echo -e "  Gắn lại: screen -r $SCREEN_NAME"
echo -e "  Dừng: screen -S $SCREEN_NAME -X quit"
