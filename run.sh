#!/bin/bash

# ============================================
#  DoraSuper Bot - Setup & Run Script
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
PYTHON="python3"
PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# Màu sắc
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║         DoraSuper Bot Setup           ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

# 1. Kiểm tra Python
echo -e "${YELLOW}[1/4] Kiểm tra Python...${NC}"
if ! command -v $PYTHON &> /dev/null; then
    echo -e "${RED}❌ Python3 chưa được cài đặt!${NC}"
    exit 1
fi
PYTHON_VERSION=$($PYTHON --version 2>&1)
echo -e "  ✅ $PYTHON_VERSION"

# 2. Tạo virtual environment nếu chưa có
echo -e "${YELLOW}[2/4] Kiểm tra Virtual Environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    echo "  📦 Đang tạo virtual environment..."
    $PYTHON -m venv $VENV_DIR
    echo "  ✅ Đã tạo virtual environment"
else
    echo "  ✅ Virtual environment đã tồn tại"
fi

# 3. Cài đặt dependencies
echo -e "${YELLOW}[3/4] Cài đặt dependencies...${NC}"
$PIP install --upgrade pip -q
$PIP install -r requirements.txt -q
echo "  ✅ Đã cài đặt xong dependencies"

# 4. Kiểm tra config.env
echo -e "${YELLOW}[4/4] Kiểm tra config...${NC}"
if [ ! -f "config.env" ]; then
    echo -e "${RED}❌ Không tìm thấy config.env!${NC}"
    echo "  Hãy copy config.env.example thành config.env và điền thông tin."
    exit 1
fi
echo "  ✅ config.env OK"

# Chạy bot
echo ""
echo -e "${GREEN}🚀 Đang khởi động DoraSuper Bot...${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

$PYTHON_VENV -m dorasuper
