import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useApp } from '../../context/AppContext';
import api from '../../services/api';
import HabitForm from './HabitForm';
import HabitItem from './HabitItem';
import WeeklySummary from './WeeklySummary';

const HabitsContainer = () => {
  const [habits, setHabits] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);

  const { token } = useAuth();
  const { showToast } = useApp();

  useEffect(() => {
    loadTodayHabits();
  }, [token]);

  const loadTodayHabits = async () => {
    if (!token) return;

    try {
      const data = await api.getTodayHabits(token);
      setHabits(data.habits);
    } catch (error) {
      console.error('Error loading habits:', error);
      showToast('Failed to load habits', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateHabit = async (habitData) => {
    try {
      await api.createHabit(token, habitData);
      setShowForm(false);
      loadTodayHabits();
      showToast(
        `A new journey begins! I've added "${habitData.name}" to our daily checklist.`
      );
    } catch (error) {
      console.error('Error creating habit:', error);
      showToast(
        'I had a little trouble creating that habit. Could you try again for me?',
        'error'
      );
    }
  };

  const handleLogCompletion = async (habitId, value = 1.0) => {
    try {
      await api.logHabitCompletion(token, habitId, value);
      loadTodayHabits();
      showToast(
        "Excellent! I've marked that as done. Keep up the great momentum."
      );

      // Trigger proactive response
      const habit = habits.find((h) => h.id === habitId);
      if (habit) {
        await api.triggerProactive(token, 'habit_complete', {
          habit_id: habitId,
          habit_name: habit.name,
          value,
        });
      }
    } catch (error) {
      showToast("I couldn't log that for you. Let's try once more.", 'error');
    }
  };

  const handleLogSkip = async (habitId, reason) => {
    try {
      await api.logHabitSkip(token, habitId, reason);
      loadTodayHabits();
      showToast(
        "It's okay to skip sometimes. Consistency is a marathon, not a sprint.",
        'info'
      );

      // Trigger proactive response
      const habit = habits.find((h) => h.id === habitId);
      if (habit) {
        await api.triggerProactive(token, 'habit_skip', {
          habit_id: habitId,
          habit_name: habit.name,
          reason,
        });
      }
    } catch (error) {
      showToast("I couldn't log that skip. Let's try once more.", 'error');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="page-container">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 section-header">
          <div>
            <h2 className="text-4xl font-black tracking-tight text-gradient-gold">Habits</h2>
            <p className="text-text-secondary text-sm mt-2 max-w-md">Small actions, consistent progress, long-term growth.</p>
          </div>
          <button
            className="btn-primary interactive-tactile whitespace-nowrap"
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? 'Close Form' : '+ New Ritual'}
          </button>
        </div>

        {/* Habit Form */}
        {showForm && (
          <div className="mb-12">
            <HabitForm
              onSubmit={handleCreateHabit}
              onCancel={() => setShowForm(false)}
            />
          </div>
        )}

        {/* Habits List */}
        <div className="space-y-8">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className="w-10 h-10 border-4 border-primary-amber border-t-transparent rounded-full animate-spin"></div>
              <p className="text-text-muted font-medium animate-pulse">Loading your operational loops...</p>
            </div>
          ) : habits.length === 0 ? (
            <div className="glass-surface p-16 text-center border-dashed border-2">
              <p className="text-text-secondary text-xl font-medium">No active rituals found.</p>
              <p className="text-text-muted text-sm mt-2 mb-6">Define your first recurring habit to start building evidence.</p>
              <button 
                onClick={() => setShowForm(true)}
                className="btn-secondary interactive-tactile"
              >
                Create Ritual
              </button>
            </div>
          ) : (
            <div className="grid gap-8">
              {habits.map((habit) => (
                <HabitItem
                  key={habit.id}
                  habit={habit}
                  onComplete={handleLogCompletion}
                  onSkip={handleLogSkip}
                />
              ))}
            </div>
          )}
        </div>

        {/* Weekly Summary */}
        {!loading && habits.length > 0 && (
          <div className="pt-16 mt-16 border-t border-border-subtle">
            <div className="mb-8">
              <h3 className="text-2xl font-black text-text-primary">Consistency Overview</h3>
              <p className="text-text-muted text-sm mt-1">Operational performance metrics</p>
            </div>
            <WeeklySummary />
          </div>
        )}
      </div>
    </div>
  );
};

export default HabitsContainer;
