import { useApp } from '../../context/AppContext';

const TabNavigation = () => {
  const { currentTab, setCurrentTab } = useApp();

  const tabs = [
    { id: 'chat', label: 'Chat' },
    { id: 'habits', label: 'Habits' },
    { id: 'reflections', label: 'Reflections' },
  ];

  return (
    <div className="flex gap-0 justify-center border-b-2 border-primary-gold/10 flex-wrap">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => setCurrentTab(tab.id)}
          className={`px-6 py-3 text-base font-bold transition-all duration-300 border-b-4 ${
            currentTab === tab.id
              ? 'text-primary-gold border-primary-gold'
              : 'text-text-secondary border-transparent hover:text-primary-gold'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
};

export default TabNavigation;
