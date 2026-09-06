import React from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { AppLayout } from '@/components/AppLayout';
import { ChatScreen } from '@/screens/ChatScreen';
import { TodayScreen } from '@/screens/TodayScreen';
import { BodyScreen } from '@/screens/BodyScreen';
import { JournalScreen } from '@/screens/JournalScreen';
import { HabitsScreen } from '@/screens/HabitsScreen';
import { InsightsScreen } from '@/screens/InsightsScreen';
import { ReviewScreen } from '@/screens/ReviewScreen';
import { MobileScreen } from '@/screens/MobileScreen';
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
      { path: 'body', element: <BodyScreen /> },
      { path: 'journal', element: <JournalScreen /> },
      { path: 'habits', element: <HabitsScreen /> },
      { path: 'insights', element: <InsightsScreen /> },
      { path: 'insights/:id', element: <InsightsScreen /> },
      { path: 'review', element: <ReviewScreen /> },
      { path: 'mobile', element: <MobileScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
    ],
  },
  { path: '*', element: <Navigate to="/chat" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
