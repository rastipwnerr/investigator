#!/bin/bash
#
# ForensicParser Setup Script
# This script helps set up the forensic parser environment
#

set -e

echo "========================================"
echo "ForensicParser Setup"
echo "========================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Python 3 is installed
echo "[1/6] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}Found Python ${PYTHON_VERSION}${NC}"

# Create virtual environment
echo ""
echo "[2/6] Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}Virtual environment created${NC}"
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo ""
echo "[3/6] Activating virtual environment..."
source .venv/bin/activate

# Install Python dependencies
echo ""
echo "[4/6] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}Python dependencies installed${NC}"

# Create necessary directories
echo ""
echo "[5/6] Creating directory structure..."
mkdir -p evtx mft amcache lnk registry other
mkdir -p jsons_elk jsons_timesketch
echo -e "${GREEN}Directories created${NC}"

# Check for forensic tools
echo ""
echo "[6/6] Checking for forensic tool binaries..."
echo ""
echo "The following tools should be in your PATH or current directory:"
echo ""

TOOLS_NEEDED=false

check_tool() {
    if command -v "$1" &> /dev/null || [ -f "./$1" ]; then
        echo -e "  ${GREEN}✓${NC} $1"
    else
        echo -e "  ${RED}✗${NC} $1 - NOT FOUND"
        TOOLS_NEEDED=true
    fi
}

check_tool "evtx_dump"
check_tool "MFTECmd"
check_tool "AmcacheParser"
check_tool "LECmd"
check_tool "RECmd"
check_tool "log2timeline.py"

echo ""

if [ "$TOOLS_NEEDED" = true ]; then
    echo -e "${YELLOW}Some forensic tools are missing.${NC}"
    echo ""
    echo "Download from:"
    echo "  - evtx_dump: https://github.com/omerbenamram/evtx"
    echo "  - Eric Zimmerman Tools: https://ericzimmerman.github.io/"
    echo "  - Plaso: pip install plaso-tools"
    echo ""
    echo "Place binaries in the current directory or add to PATH."
else
    echo -e "${GREEN}All forensic tools found!${NC}"
fi

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment:"
echo "     source .venv/bin/activate"
echo ""
echo "  2. Configure your ELK stack in config.py"
echo ""
echo "  3. Run the application:"
echo "     python main_app.py --help"
echo ""
echo "  4. See README.md for usage examples"
echo ""
