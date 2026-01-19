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
    <div className="flex-1 overflow-y-auto p-8">
      <div className="container-wide space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <h2 className="text-2xl gradient-text">Today's Habits</h2>
          <button
            className="btn-primary text-sm"
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? 'Cancel' : '+ New Habit'}
          </button>
        </div>

        {/* Habit Form */}
        {showForm && (
          <HabitForm
            onSubmit={handleCreateHabit}
            onCancel={() => setShowForm(false)}
          />
        )}

        {/* Habits List */}
        {loading ? (
          <p className="text-text-secondary text-center py-8">
            Loading habits...
          </p>
        ) : habits.length === 0 ? (
          <p className="text-text-secondary text-center py-8">
            No habits yet. Create one to get started!
          </p>
        ) : (
          <div className="space-y-4">
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

        {/* Weekly Summary */}
        {!loading && habits.length > 0 && <WeeklySummary />}
      </div>
    </div>
  );
};

export default HabitsContainer;
