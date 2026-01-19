import { useApp } from '../../context/AppContext';
import Header from '../shared/Header';
import ChatContainer from '../chat/ChatContainer';
import HabitsContainer from '../habits/HabitsContainer';
import ReflectionsContainer from '../reflections/ReflectionsContainer';

const MainLayout = () => {
  const { currentTab } = useApp();

  return (
    <div className="flex flex-col h-screen">
      <Header />

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden">
        {currentTab === 'chat' && <ChatContainer />}
        {currentTab === 'habits' && <HabitsContainer />}
        {currentTab === 'reflections' && <ReflectionsContainer />}
      </div>
    </div>
  );
};

export default MainLayout;
