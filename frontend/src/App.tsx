import React from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { LoadingState } from '@/components/states';
import { AppLayout } from '@/components/AppLayout';
import { ChatScreen } from '@/screens/ChatScreen';
import { TodayScreen } from '@/screens/TodayScreen';
import { JournalScreen } from '@/screens/JournalScreen';
import { HabitsScreen } from '@/screens/HabitsScreen';
import { DecisionsScreen } from '@/screens/DecisionsScreen';
import { PatternsScreen } from '@/screens/PatternsScreen';
import { InsightsScreen } from '@/screens/InsightsScreen';
import { ReviewScreen } from '@/screens/ReviewScreen';
import { ImportScreen } from '@/screens/ImportScreen';
import { ConstructsScreen } from '@/screens/ConstructsScreen';
import { IdeasScreen } from '@/screens/IdeasScreen';
import { SensorsScreen } from '@/screens/SensorsScreen';
// The Observatory is a diagnostic screen most visits never open; load it on demand.
const ObservatoryScreen = React.lazy(() => import('@/screens/ObservatoryScreen').then(m => ({ default: m.ObservatoryScreen })));
const observatory = <React.Suspense fallback={<LoadingState label="Opening the Observatory…" />}><ObservatoryScreen /></React.Suspense>;
import { SettingsScreen } from '@/screens/SettingsScreen';
import { OnboardingScreen } from '@/screens/OnboardingScreen';

const router = createBrowserRouter([
  // Onboarding sits outside the app shell (no sidebar)
  { path: '/onboarding', element: <OnboardingScreen /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: <ChatScreen /> },
      { path: 'today', element: <TodayScreen /> },
      { path: 'journal', element: <JournalScreen /> },
      { path: 'habits', element: <HabitsScreen /> },
      { path: 'decisions', element: <DecisionsScreen /> },
      { path: 'insights', element: <InsightsScreen /> },
      // Old-engine insight links had ids; those insights are gone from the app.
      { path: 'insights/:id', element: <Navigate to="/insights" replace /> },
      { path: 'patterns', element: <PatternsScreen /> },
      { path: 'patterns/:id', element: <PatternsScreen /> },
      { path: 'review', element: <ReviewScreen /> },
      { path: 'import', element: <ImportScreen /> },
      { path: 'constructs', element: <ConstructsScreen /> },
      { path: 'ideas', element: <IdeasScreen /> },
      { path: 'ideas/:id', element: <IdeasScreen /> },
      { path: 'sensors', element: <SensorsScreen /> },
      { path: 'observatory', element: observatory },
      { path: 'observatory/traces/:traceId', element: observatory },
      { path: 'settings', element: <SettingsScreen /> },
    ],
  },
  { path: '*', element: <Navigate to="/chat" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
