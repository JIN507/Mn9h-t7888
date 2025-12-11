# Bahith Al-Suwar - Migration Guide

## Project Overview
This project has been upgraded from a monolithic Flask+Templates application to a modern **React + Vite** frontend with a **Flask REST API** backend.

## New Architecture
- **Backend (`/`):** Flask application serving as a JSON API.
- **Frontend (`/frontend`):** React Single Page Application (SPA) using Tailwind CSS and Lucide Icons.

## Setup Instructions

### 1. Backend Setup
The backend now requires environment variables for security.

1. Create a `.env` file in the root directory (same level as `app.py`).
2. Add your API keys:
   ```env
   # .env
   IMGBB_API_KEY=your_imgbb_key
   AIORNOT_API_KEY=your_aiornot_key
   SERPAPI_API_KEY=your_serpapi_key
   ZENSERP_API_KEY=dc270410-8660-11f0-bccb-fb3d50c822e4
   ```
3. Install dependencies (if not already installed):
   ```bash
   pip install flask flask-cors python-dotenv requests opencv-python-headless
   ```
4. Run the backend:
   ```bash
   python app.py
   ```
   Server will start on `http://127.0.0.1:5000`.

### 2. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
   Frontend will start on `http://localhost:5173`.

### 3. Usage
- Open `http://localhost:5173` in your browser.
- The frontend proxies all `/api/*` requests to the Flask backend automatically.

## Key Changes
- **Security:** API keys are no longer hardcoded.
- **Direct Search:** New "Direct Search" tab (`/direct-search`) uses Zenserp to generate a timeline of media history.
- **UI/UX:** Complete redesign using Tailwind CSS with glassmorphism effects and responsiveness.

## Files
- **NEW:** `frontend/` (Entire React project)
- **MODIFIED:** `app.py` (Refactored to cleaner API, added Zenserp endpoint)
- **DEPRECATED:** `templates/*.html` (Can be removed after verifying the new frontend covers all features)
