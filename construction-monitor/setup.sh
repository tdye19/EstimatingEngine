#!/bin/bash
# ============================================================
# Construction Monitor — Fork Setup Script
# Run this once to initialize from the World Monitor fork
# ============================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "${BLUE}"
echo "  ██████╗ ██████╗ ███╗   ██╗███████╗████████╗██████╗ "
echo "  ██╔════╝██╔═══██╗████╗  ██║██╔════╝╚══██╔══╝██╔══██╗"
echo "  ██║     ██║   ██║██╔██╗ ██║███████╗   ██║   ██████╔╝"
echo "  ██║     ██║   ██║██║╚██╗██║╚════██║   ██║   ██╔══██╗"
echo "  ╚██████╗╚██████╔╝██║ ╚████║███████║   ██║   ██║  ██║"
echo "   ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝"
echo "  MONITOR — Real-Time Construction Intelligence"
echo -e "${NC}"

echo -e "${YELLOW}Step 1: Cloning World Monitor (base fork)...${NC}"
if [ ! -d "worldmonitor-base" ]; then
  git clone https://github.com/koala73/worldmonitor.git worldmonitor-base
  echo -e "${GREEN}✓ World Monitor cloned${NC}"
else
  echo -e "${GREEN}✓ Already cloned${NC}"
fi

echo -e "${YELLOW}Step 2: Initializing Construction Monitor project...${NC}"
if [ ! -d "construction-monitor" ]; then
  mkdir construction-monitor
  cd construction-monitor

  # Copy base structure from World Monitor
  cp -r ../worldmonitor-base/src ./
  cp -r ../worldmonitor-base/public ./
  cp -r ../worldmonitor-base/api ./
  cp ../worldmonitor-base/package.json ./
  cp ../worldmonitor-base/tsconfig.json ./
  cp ../worldmonitor-base/vite.config.ts ./
  cp ../worldmonitor-base/index.html ./

  # Initialize new git repo (don't inherit WM history)
  git init
  git add .
  git commit -m "chore: initial fork from World Monitor (MIT)"

  cd ..
  echo -e "${GREEN}✓ Construction Monitor project initialized${NC}"
else
  echo -e "${GREEN}✓ Project already initialized${NC}"
fi

echo -e "${YELLOW}Step 3: Installing dependencies...${NC}"
cd construction-monitor
npm install
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo -e "${YELLOW}Step 4: Setting up environment variables...${NC}"
if [ ! -f ".env.local" ]; then
  cat > .env.local << 'EOF'
# ============================================================
# CONSTRUCTION MONITOR — Environment Variables
# ============================================================

# Build Variant: estimator | field | owner
VITE_VARIANT=estimator
VITE_APP_TITLE="Construction Monitor"

# --- FREE TIER APIs (no signup required) ---
# BLS (Bureau of Labor Statistics)
# No key needed for most endpoints

# Census Bureau
# No key needed for Building Permits Survey

# FRED (Federal Reserve Economic Data)
# Get free key at: https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY=

# NOAA/NWS Weather
# No key needed

# SAM.gov (Federal Contracting)
# Get free key at: https://sam.gov/content/entity-information/api
SAM_GOV_API_KEY=

# --- CACHING (Upstash Redis — free tier: 10k req/day) ---
# Signup: https://upstash.com
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# --- AI LAYER (Groq — free tier: 30 req/min) ---
# Signup: https://console.groq.com
GROQ_API_KEY=

# --- PAID TIER (add when revenue justifies) ---
# Dodge Data & Analytics
# DODGE_API_KEY=
# D&B (Dun & Bradstreet) Contractor Scoring
# DNB_API_KEY=
# Random Lengths (Lumber Pricing)
# RANDOM_LENGTHS_API_KEY=
EOF
  echo -e "${GREEN}✓ .env.local created — fill in API keys before running${NC}"
else
  echo -e "${GREEN}✓ .env.local already exists${NC}"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Construction Monitor setup complete!           ${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. Fill in API keys in ${YELLOW}.env.local${NC}"
echo -e "  2. Run ${YELLOW}npm run dev${NC} to start development server"
echo -e "  3. Open ${YELLOW}http://localhost:5173${NC}"
echo ""
echo -e "Variants:"
echo -e "  ${BLUE}npm run dev${NC}          → Estimator variant (default)"
echo -e "  ${BLUE}npm run dev:field${NC}    → Field variant"
echo -e "  ${BLUE}npm run dev:owner${NC}    → Owner/Intel variant"
echo ""
