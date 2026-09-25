import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { AppLayout } from '@/components/AppLayout';
import { ChatScreen } from '@/screens/ChatScreen';
import { TodayScreen } from '@/screens/TodayScreen';
import { JournalScreen } from '@/screens/JournalScreen';
import { HabitsScreen } from '@/screens/HabitsScreen';
import { DecisionsScreen } from '@/screens/DecisionsScreen';
import { PatternsScreen } from '@/screens/PatternsScreen';
import { ReviewScreen } from '@/screens/ReviewScreen';
import { ImportScreen } from '@/screens/ImportScreen';
import { ConstructsScreen } from '@/screens/ConstructsScreen';
import { IdeasScreen } from '@/screens/IdeasScreen';
import { SensorsScreen } from '@/screens/SensorsScreen';
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
      // Insights came from the old engine; Patterns replaced them (the data stays).
      { path: 'insights', element: <Navigate to="/patterns" replace /> },
      { path: 'insights/:id', element: <Navigate to="/patterns" replace /> },
      { path: 'patterns', element: <PatternsScreen /> },
      { path: 'patterns/:id', element: <PatternsScreen /> },
      { path: 'review', element: <ReviewScreen /> },
      { path: 'import', element: <ImportScreen /> },
      { path: 'constructs', element: <ConstructsScreen /> },
      { path: 'ideas', element: <IdeasScreen /> },
      { path: 'ideas/:id', element: <IdeasScreen /> },
      { path: 'sensors', element: <SensorsScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
    ],
  },
  { path: '*', element: <Navigate to="/chat" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
