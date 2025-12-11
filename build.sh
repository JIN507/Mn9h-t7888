#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright Browsers..."
python -m playwright install chromium

echo "Installing Node.js..."
# Install Node.js
export NODE_VERSION=20.10.0
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install $NODE_VERSION
nvm use $NODE_VERSION

echo "Building Frontend..."
cd frontend
npm install
# Fix permission denied error for vite binary
chmod -R +x node_modules/.bin
npm run build
cd ..

echo "Creating necessary directories..."
mkdir -p uploads user-data static/uploads/audio

echo "Build Completed Successfully!"
