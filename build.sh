#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Node.js..."
# Install Node.js - specific version to ensure compatibility
export NODE_VERSION=20.10.0
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install $NODE_VERSION
nvm use $NODE_VERSION

echo "Building Frontend..."
cd frontend
npm install
npm run build
cd ..

echo "Downloading Dependencies..."
# Ensure directories exist
mkdir -p /tmp/chromium
mkdir -p /tmp/user-data

# Download Chromium if not present (logic specific to the user's setup in render.yaml)
wget -O chromium.zip "https://s3.eu-north-1.amazonaws.com/chromium.file/chromium.zip"
unzip -o chromium.zip -d /tmp/chromium/

wget -O user_data.zip "https://s3.eu-north-1.amazonaws.com/chromium.file/userdata/user_data.zip"
unzip -o user_data.zip -d /tmp/

echo "Build Completed Successfully!"
