# IRIS Frontend - Demo Mode Guide (DEPRECATED)

> **⚠️ WARNING**: This documentation refers to the deprecated React frontend. The current production frontend is the **Vanilla JS** implementation in the root directory (`iris_frontend.html`).

## Overview

Demo Mode allows you to explore the IRIS frontend **without needing the backend database**. All features work with mock data, so you can test the UI, interactions, and overall user experience.

---

## 🚀 How to Enable Demo Mode

### Method 1: Environment Variable (Automatic)

Demo mode is now **enabled by default** in the `.env` file:

```env
VITE_DEMO_MODE=true
```

With this setting, you'll be automatically logged in as "Demo User" when you load the app.

### Method 2: Username Login (Manual)

1. Start the app normally
2. On the login or signup page, enter:
   - **Username:** `demo` (or `Demo User`)
   - **Password:** `anything` (any password works)
3. Click "Log In" or "Sign Up"

You'll be instantly logged in with demo data!

### Method 3: Browser Console (Advanced)

Open your browser's developer console and type:

```javascript
localStorage.setItem('demo_mode', 'true');
location.reload();
```

This will enable demo mode and reload the page.

---

## 📦 What's Included in Demo Mode

### ✅ Chat Tab
- **Sample conversation** with IRIS
- Send messages and get demo responses
- History persists during the session
- Demo response: "This is a demo response. In the real app, I would analyze your message..."

### ✅ Habits Tab
- **3 pre-loaded habits:**
  1. **Morning Meditation** (Completion type, 7-day streak)
  2. **Reading** (Duration type, 180/300 minutes weekly)
  3. **Exercise** (Count type, 3/7 times weekly)

- **Fully functional buttons:**
  - ✓ Complete habits
  - Skip with reason modal
  - Log progress for duration/count habits

- **Weekly Summary:**
  - Shows 4 sample habits with completion stats
  - Visual grid display

### ✅ Reflections Tab
- **2 sample reflections:**
  1. Recent entry about productivity (Mood: great, Energy: 4/5)
  2. Entry about feeling anxious (Mood: okay, Energy: 3/5)

- **Create new reflections:**
  - Add content, mood, energy level, tags
  - Form validation works

- **30-Day Mood Trend:**
  - Distribution: Great (8), Good (5), Okay (4), Bad (2)
  - Average energy: 3.8/5

### ✅ All UI Features
- Tab navigation works
- Toast notifications appear
- Modals open and close
- Forms validate input
- Buttons have hover effects
- Animations and transitions
- Responsive design

---

## 🎨 What Demo Mode Looks Like

When you load the app with demo mode enabled:

```
┌────────────────────────────────────────┐
│  [Logout]                              │
│          IRIS                          │
│    Welcome back, Demo User             │
│                                        │
│  [  Chat  ]  [ Habits ]  [Reflections]│
│  ─────────                             │
└────────────────────────────────────────┘
```

You'll see "Demo User" as the logged-in username.

---

## 🔄 Testing Interactions

### Create a New Habit
1. Go to **Habits** tab
2. Click **+ New Habit**
3. Fill out the form (try duration or count types!)
4. Click **Create**
5. Toast notification appears (but habit won't persist - demo only!)

### Log Habit Progress
1. Click **+ Log** on Reading or Exercise
2. Modal opens asking for value
3. For duration: Choose minutes or hours
4. Enter a number and click **Save Progress**
5. Toast confirms (demo mode simulates success)

### Skip a Habit
1. Click **Skip** on any habit
2. Modal asks for optional reason
3. Type a reason or leave blank
4. Click **Confirm Skip**
5. Toast appears with encouraging message

### Chat with IRIS
1. Go to **Chat** tab
2. Type any message in the input
3. Click **Send**
4. IRIS responds with demo message after brief delay
5. History shows both messages

### Add a Reflection
1. Go to **Reflections** tab
2. Click **+ New Reflection**
3. Write your thoughts
4. Select mood, energy, and tags
5. Click **Save Reflection**
6. Toast confirms (but won't persist - demo only!)

---

## ⚠️ Limitations of Demo Mode

Since demo mode uses mock data, some behaviors differ from the real app:

| Feature | Demo Mode | Real App |
|---------|-----------|----------|
| **Data Persistence** | ❌ Resets on refresh | ✅ Saved to database |
| **IRIS AI Responses** | ❌ Generic demo text | ✅ Personalized analysis |
| **Habit Streaks** | ❌ Static values | ✅ Updates daily |
| **Historical Data** | ❌ Fixed samples | ✅ Your actual history |
| **User Accounts** | ❌ Single demo user | ✅ Multiple real users |
| **Proactive Insights** | ❌ Disabled | ✅ IRIS suggests actions |

---

## 🔧 Disable Demo Mode

To connect to the real backend:

1. Edit `.env` file:
   ```env
   VITE_DEMO_MODE=false
   ```

2. Restart the dev server:
   ```bash
   npm run dev
   ```

3. Or clear demo mode from localStorage:
   ```javascript
   localStorage.removeItem('demo_mode');
   location.reload();
   ```

4. Make sure your backend API is running on `http://localhost:8000`

---

## 🐛 Troubleshooting

### "I can't log in"
- Try username: `demo` with any password
- Check that `.env` has `VITE_DEMO_MODE=true`
- Restart the dev server after changing `.env`

### "My changes aren't saving"
- **This is expected in demo mode!**
- Demo mode doesn't persist data
- Connect to the real backend to save your work

### "IRIS responses are generic"
- **This is expected in demo mode!**
- The real IRIS uses AI to generate personalized responses
- Demo mode shows placeholder text

### "I want to test with real data"
- Set `VITE_DEMO_MODE=false` in `.env`
- Make sure backend is running
- Restart dev server
- Create a real account

---

## 📚 Next Steps

Once you've explored the demo:

1. **Set up the backend** to unlock full functionality
2. **Create a real account** to start tracking your habits
3. **Chat with the real IRIS** AI for personalized insights
4. **Build your habits** and watch your streaks grow!

---

## 🎉 Enjoy Exploring!

Demo mode is perfect for:
- **Showcasing the UI** to others
- **Testing new features** without affecting real data
- **Exploring the interface** before committing to setup
- **Development and design** work

Have fun! 🚀
