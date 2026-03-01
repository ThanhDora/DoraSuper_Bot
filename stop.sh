#!/bin/bash

# ============================================
#  DoraSuper Bot - Dừng bot (treo / chạy nền)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SCREEN_NAME="dorasuper"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Đang dừng DoraSuper Bot...${NC}"

# 1. Dừng session screen (nếu chạy bằng ./screen.sh)
if screen -ls 2>/dev/null | grep -q "\.$SCREEN_NAME\s"; then
    screen -S "$SCREEN_NAME" -X quit 2>/dev/null && echo -e "  ${GREEN}✅ Đã thoát session screen \"$SCREEN_NAME\"${NC}" || true
else
    echo -e "  (Không có session screen \"$SCREEN_NAME\")"
fi

# 2. Dừng process python -m dorasuper (nếu chạy bằng ./run.sh ở nền hoặc cách khác)
if pgrep -f "python.*dorasuper" >/dev/null 2>&1; then
    pkill -f "python.*dorasuper" 2>/dev/null && echo -e "  ${GREEN}✅ Đã dừng process bot${NC}" || true
else
    echo -e "  (Không có process bot đang chạy)"
fi

echo ""
echo -e "${GREEN}Dừng bot xong. Chạy ./run.sh hoặc ./screen.sh để chạy lại.${NC}"
