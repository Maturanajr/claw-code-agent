#!/bin/bash

# ── colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ██████╗██╗      █████╗ ██╗    ██╗"
echo " ██╔════╝██║     ██╔══██╗██║    ██║"
echo " ██║     ██║     ███████║██║ █╗ ██║"
echo " ██║     ██║     ██╔══██║██║███╗██║"
echo " ╚██████╗███████╗██║  ██║╚███╔███╔╝"
echo "  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ "
echo -e "${NC}"
echo -e "${CYAN}🐾 Claw Code Agent — startup check${NC}"
echo ""

# ── detect python ─────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python py; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
        if [ "$VER" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}❌ Python 3.10+ not found. Please install it from https://python.org${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python: $($PYTHON --version)${NC}"

# ── package check & install ───────────────────────────────────────────────────
# Format: "import_name|pip_name|extra_install_cmd"
# extra_install_cmd is optional (used for playwright browsers)
PACKAGES=(
    "streamlit|streamlit|"
    "playwright|playwright|playwright install chromium"
)

MISSING=()
MISSING_PIP=()
MISSING_EXTRA=()

for entry in "${PACKAGES[@]}"; do
    IFS='|' read -r import_name pip_name extra_cmd <<< "$entry"
    if ! $PYTHON -c "import $import_name" &>/dev/null; then
        MISSING+=("$import_name")
        MISSING_PIP+=("$pip_name")
        MISSING_EXTRA+=("$extra_cmd")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Missing packages:${NC}"
    for pkg in "${MISSING[@]}"; do
        echo -e "   ${RED}✗${NC} $pkg"
    done
    echo ""
    read -p "Install missing packages now? [Y/n] " CONFIRM
    CONFIRM=${CONFIRM:-Y}

    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        for i in "${!MISSING_PIP[@]}"; do
            pip_name="${MISSING_PIP[$i]}"
            extra_cmd="${MISSING_EXTRA[$i]}"

            echo -e "${CYAN}📦 Installing $pip_name...${NC}"
            $PYTHON -m pip install "$pip_name" --quiet

            if [ -n "$extra_cmd" ]; then
                echo -e "${CYAN}🔧 Running: $PYTHON -m $extra_cmd${NC}"
                $PYTHON -m $extra_cmd
            fi

            echo -e "${GREEN}✅ $pip_name installed.${NC}"
        done
    else
        echo -e "${RED}❌ Cannot start without required packages. Exiting.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ All packages present.${NC}"
fi

# ── check playwright browsers ─────────────────────────────────────────────────
if $PYTHON -c "import playwright" &>/dev/null; then
    if ! $PYTHON -c "
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        b.close()
except Exception:
    exit(1)
" &>/dev/null 2>&1; then
        echo ""
        echo -e "${YELLOW}⚠️  Playwright browsers not installed.${NC}"
        read -p "Install Chromium browser now? [Y/n] " CONFIRM_PW
        CONFIRM_PW=${CONFIRM_PW:-Y}
        if [[ "$CONFIRM_PW" =~ ^[Yy]$ ]]; then
            echo -e "${CYAN}🔧 Installing Chromium...${NC}"
            $PYTHON -m playwright install chromium
            echo -e "${GREEN}✅ Chromium installed.${NC}"
        else
            echo -e "${YELLOW}⚠️  Browser tools will not work without Chromium.${NC}"
        fi
    else
        echo -e "${GREEN}✅ Playwright Chromium ready.${NC}"
    fi
fi

# ── load .env ─────────────────────────────────────────────────────────────────
echo ""
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating template...${NC}"
    cat > .env << 'EOF'
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o-mini
EOF
    echo -e "${YELLOW}   Edit .env with your API key before using the agent.${NC}"
fi

export $(sed 's/\r//' .env | sed 's/"//g' | grep -v '^#' | grep '=' | xargs)

echo -e "${GREEN}✅ Config loaded:${NC}"
echo "   OPENAI_BASE_URL=$OPENAI_BASE_URL"
echo "   OPENAI_MODEL=$OPENAI_MODEL"
echo ""

# ── launch ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}🚀 Starting Claw Code Agent UI...${NC}"
echo ""
$PYTHON -m streamlit run app.py
