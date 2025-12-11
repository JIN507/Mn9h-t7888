# Google Cloud Vision API Setup Guide

This guide will help you set up Google Cloud Vision API for the provenance feature (أصل المحتوى).

## Why Google Cloud Vision API?

✅ **More Reliable** - No timeouts like Zenserp  
✅ **Better Results** - Google's powerful image recognition  
✅ **Official API** - Direct from Google, not a third party  
✅ **Free Tier** - 1000 requests/month for free  

---

## Setup Steps

### 1. Create Google Cloud Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account
3. Accept the terms of service

### 2. Create a New Project

1. Click the project dropdown at the top
2. Click "New Project"
3. Name it: `reverse-image-search` (or any name you like)
4. Click "Create"

### 3. Enable Vision API

1. Go to [Vision API page](https://console.cloud.google.com/apis/library/vision.googleapis.com)
2. Make sure your project is selected
3. Click "Enable"
4. Wait for it to activate (takes a few seconds)

### 4. Create Service Account

1. Go to [Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Click "Create Service Account"
3. Name: `vision-api-service`
4. Click "Create and Continue"
5. Role: Select "Basic" → "Owner" (or "Cloud Vision AI User")
6. Click "Continue" then "Done"

### 5. Create Credentials (JSON Key)

1. Click on the service account you just created
2. Go to "Keys" tab
3. Click "Add Key" → "Create new key"
4. Choose "JSON" format
5. Click "Create"
6. **Save the downloaded JSON file** - you'll need it!

### 6. Set Up Credentials in Your App

#### Option A: Environment Variable (Recommended)

**Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your\service-account-key.json"
```

**Windows (Command Prompt):**
```cmd
set GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\your\service-account-key.json
```

**Linux/Mac:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```

#### Option B: Place in Project Directory

1. Rename the JSON file to `google-credentials.json`
2. Place it in your project root: `c:\Users\pcc\OneDrive\Desktop\clean\`
3. Add this to your `.env` file:
```
GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json
```

### 7. Install Python Library

```bash
pip install google-cloud-vision
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

### 8. Test the Setup

Run the app and try the provenance feature. If you see:
- ✅ "Google Cloud credentials not set up" → Check step 6
- ✅ "Permission denied" → Make sure Vision API is enabled (step 3)
- ✅ "Quota exceeded" → You've used your free tier, need to upgrade

---

## Pricing

**Free Tier:**
- 1,000 requests/month FREE
- No credit card required for free tier

**After Free Tier:**
- $1.50 per 1,000 requests
- Detailed pricing: [Vision API Pricing](https://cloud.google.com/vision/pricing)

---

## Security Best Practices

⚠️ **IMPORTANT:**
1. **Never commit the JSON credentials file to Git**
2. Add to `.gitignore`:
   ```
   google-credentials.json
   *.json
   ```
3. Keep the credentials file secure
4. Don't share your credentials

---

## Troubleshooting

### "Credentials not found"
- Check that `GOOGLE_APPLICATION_CREDENTIALS` is set correctly
- Verify the file path is absolute, not relative
- Make sure the JSON file exists at that location

### "Permission denied"
- Vision API might not be enabled
- Service account might not have correct role
- Try using "Owner" role for testing

### "Quota exceeded"
- You've used your 1,000 free requests
- Either wait for next month or upgrade to paid tier
- Check usage: [Cloud Console → Vision API → Quotas](https://console.cloud.google.com/apis/api/vision.googleapis.com/quotas)

### Still having issues?
- Check the terminal logs for specific error messages
- Verify your Google Cloud project is active
- Make sure billing is enabled (required even for free tier)

---

## Alternative: Use API Key (Simpler but Less Secure)

If you want a simpler setup (not recommended for production):

1. Go to [Credentials](https://console.cloud.google.com/apis/credentials)
2. Click "Create Credentials" → "API Key"
3. Copy the key
4. Use it in code (we can modify the app to support this)

**Note:** Service Account (JSON) is more secure and recommended.

---

## Next Steps

After setup:
1. Restart your Flask app
2. Go to "أصل المحتوى" (Provenance)
3. Upload an image
4. You should now get results from Google Cloud Vision API!

Good luck! 🚀
