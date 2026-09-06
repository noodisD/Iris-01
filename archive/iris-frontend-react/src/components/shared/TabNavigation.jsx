import { useApp } from '../../context/AppContext';

const TabNavigation = () => {
  const { currentTab, setCurrentTab } = useApp();

  const tabs = [
    { id: 'chat', label: 'Chat' },
    { id: 'habits', label: 'Habits' },
    { id: 'reflections', label: 'Reflections' },
  ];

  return (
    <div className="flex gap-10 justify-center overflow-x-auto no-scrollbar pt-2">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={(e) => {
            e.preventDefault();
            setCurrentTab(tab.id);
          }}
          className={`px-2 py-4 text-[11px] font-black uppercase tracking-[0.3em] transition-all duration-500 border-b-2 whitespace-nowrap ${
            currentTab === tab.id
              ? 'text-primary-amber border-primary-amber translate-y-[-1px]'
              : 'text-text-muted border-transparent hover:text-text-secondary hover:translate-y-[-1px]'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
};

export default TabNavigation;
