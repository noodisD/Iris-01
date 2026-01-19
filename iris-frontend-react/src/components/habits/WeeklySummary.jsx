import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

const WeeklySummary = () => {
  const [summary, setSummary] = useState(null);
  const { token } = useAuth();

  useEffect(() => {
    loadWeeklySummary();
  }, [token]);

  const loadWeeklySummary = async () => {
    if (!token) return;

    try {
      const data = await api.getWeeklySummary(token);
      setSummary(data);
    } catch (error) {
      console.error('Error loading weekly summary:', error);
    }
  };

  if (!summary || summary.habits.length === 0) {
    return null;
  }

  return (
    <div className="glass-container p-6">
      <h3 className="text-xl gradient-text mb-4">Weekly Summary</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {summary.habits.map((habit) => (
          <div
            key={habit.name}
            className="bg-primary-gold/5 p-4 rounded-lg text-center"
          >
            <div className="text-2xl font-bold text-primary-gold">
              {habit.completed}/{habit.total_days}
            </div>
            <div className="text-xs text-text-secondary mt-2">
              {habit.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default WeeklySummary;
