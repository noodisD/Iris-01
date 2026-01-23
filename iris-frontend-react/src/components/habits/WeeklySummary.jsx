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
    <div className="glass-container" style={{ padding: '1.5rem' }}>
      <h3 className="gradient-text" style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>
        Weekly Summary
      </h3>
      <div className="stats-grid">
        {summary.habits.map((habit) => (
          <div key={habit.name} className="stat-box">
            <div className="stat-value">
              {habit.completed}/{habit.total_days}
            </div>
            <div className="stat-label">{habit.name}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default WeeklySummary;
