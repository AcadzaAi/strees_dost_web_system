# Testing Category Images - Step by Step

## What We Fixed

The system now stores your selected category in a **global cache** that survives sessionStorage clearing. This ensures all 3 images (Q1, Q2, Q3) use images from YOUR selected category, not random categories.

## How to Test

### Step 1: Open Browser
- Go to http://127.0.0.1:5002
- **Open Browser Console (F12)** - this is crucial for debugging

### Step 2: Login
- Enter any name
- Click continue

### Step 3: Select ONE Category
- Example: Select **"Phone Addiction"**
- Click "Continue"

### Step 4: Skip or Fill Details
- Either skip or add details
- Click "Start Session"

### Step 5: Watch Console Logs
Look for these specific log messages in the browser console:

```
[Focus Selection] ========================================
[Focus Selection] CACHING FOCUS DATA
[Focus Selection] Challenges: [{text: "Phone Addiction", ...}]
[Focus Selection] ✓✓✓ STORED IN GLOBAL CACHE
[Focus Selection] ========================================
```

### Step 6: Check Image Requests
When images are fetched, you should see:

```
[img payload] ========== BUILDING IMAGE PAYLOAD ==========
[img payload] ✓✓✓ Using GLOBAL CACHE: {challenges: [...]}
[img payload] Challenges: [{text: "Phone Addiction", ...}]
```

### Step 7: Verify Backend
Check the server terminal. You should see:

```
Request body keys: ['initial_text', 'followup_answers', 'focus_selection']
has_focus=True
✓✓✓ USING CATEGORY IMAGES ✓✓✓
Selected challenges: ['Phone Addiction']
Q1: Category 'Phone Addiction': using local image 'category_images/phone_addiction_X.jpg'
Q2: Category 'Phone Addiction': using local image 'category_images/phone_addiction_Y.jpg'
Q3: Category 'Phone Addiction': using local image 'category_images/phone_addiction_Z.jpg'
```

### Step 8: Test Questions Q1, Q2, Q3
- All 3 questions should show images from **Phone Addiction** category
- Images will be random selections from the 5 available phone_addiction images (1-5)

## Expected Behavior

✅ **If you select 1 category:** All 3 images from that category  
✅ **If you select 2 categories:** Images alternate between them  
✅ **If you select 3+ categories:** First 3 categories used  

## What to Report

If it's still showing random categories, copy and paste:

1. **Browser console logs** (lines with `[Focus Selection]` and `[img payload]`)
2. **Server logs** (lines with "DISTRACTION-IMAGE" and "focus_selection")

This will help me see exactly where the data is getting lost.

## Available Categories

Each category has 5 pre-stored images:
- Phone Addiction
- Social Media Addiction
- Entertainment Distraction
- Sports & Gaming Distraction
- Exam Stress & Anxiety
- Overthinking
- Low Motivation
- Lack of Consistency
- Poor Time Management
- Sleep Issues
- Difficulty Understanding Concepts
- Low Confidence & Self-Doubt
- Family Pressure
- Study Burnout
- Poor Concentration
