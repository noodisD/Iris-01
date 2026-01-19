# IRIS Frontend - React Application

A modern React frontend for the IRIS AI Companion system, built with Vite, React, Tailwind CSS, and Context API.

## Features

- **Authentication**: User signup and login with JWT tokens
- **Chat Interface**: Real-time messaging with IRIS AI companion
- **Habits Tracking**: Track daily habits with streaks and progress
- **Reflections**: Journal your thoughts with mood and energy tracking
- **Responsive Design**: Beautiful dark theme with gold accents
- **Toast Notifications**: Contextual feedback for user actions
- **Modal Dialogs**: Skip habits and log progress with intuitive UIs

## Tech Stack

- **Vite**: Fast build tool and dev server
- **React 18**: Modern React with hooks
- **Tailwind CSS**: Utility-first CSS framework
- **Context API**: State management for auth and app state
- **Fetch API**: HTTP client for backend communication

## Project Structure

```
src/
├── components/
│   ├── auth/              # Authentication components
│   ├── chat/              # Chat interface components
│   ├── habits/            # Habits tracking components
│   ├── reflections/       # Reflections/journaling components
│   ├── shared/            # Shared/reusable components
│   └── layout/            # Layout components
├── context/               # React Context providers
├── services/              # API service layer
├── App.jsx                # Main app component
├── main.jsx               # Entry point
└── index.css              # Global styles with Tailwind
```

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- IRIS backend API running on `http://localhost:8000`

### Installation

1. Install dependencies:
   ```bash
   npm install
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env if your API is on a different URL
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

4. Open your browser to `http://localhost:5173`

### Build for Production

```bash
npm run build
npm run preview  # Preview the production build
```

## Configuration

Environment variables are defined in `.env`:

- `VITE_API_URL`: Backend API URL (default: `http://localhost:8000`)

## Component Overview

### Authentication
- `Landing.jsx`: Landing page with signup/login options
- `AuthForm.jsx`: Reusable form for signup and login

### Chat
- `ChatContainer.jsx`: Main chat interface with message history
- `Message.jsx`: Individual message component
- `ChatInput.jsx`: Message input with send functionality

### Habits
- `HabitsContainer.jsx`: Main habits tracking interface
- `HabitForm.jsx`: Form to create new habits
- `HabitItem.jsx`: Individual habit with completion/skip actions
- `WeeklySummary.jsx`: Weekly progress summary

### Reflections
- `ReflectionsContainer.jsx`: Main reflections interface
- `ReflectionForm.jsx`: Form to create new reflections
- `ReflectionItem.jsx`: Individual reflection display
- `MoodTrend.jsx`: 30-day mood trend visualization

### Shared Components
- `Modal.jsx`: Reusable modal dialog
- `Toast.jsx`: Toast notification system
- `Chip.jsx` / `ChipGroup.jsx`: Selection chips
- `TabNavigation.jsx`: Tab navigation
- `Header.jsx`: App header with logout

## Styling

The app uses Tailwind CSS with custom theme colors:

- **Primary Dark**: `#1a1a2e`, `#16213e`
- **Gold**: `#FFD700`, `#FFC107`
- **Text**: `#ecf0f1`, `#bdc3c7`

Custom CSS classes are defined in `index.css` using Tailwind's `@layer` directive.

## State Management

- **AuthContext**: Manages user authentication state
- **AppContext**: Manages app-level state (toasts, current tab)

## API Integration

The `src/services/api.js` file provides a clean API service layer for all backend communication:

- Authentication endpoints
- Chat message endpoints
- Habits CRUD operations
- Reflections CRUD operations

## Development

### Hot Module Replacement

Vite provides instant HMR during development. Changes to components will reflect immediately.

### Code Organization

- Components are organized by feature
- Shared/reusable components in `shared/`
- Context providers in `context/`
- API calls abstracted to `services/`

## License

Part of the IRIS project.
