import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

const MoodTrend = () => {
  const [trend, setTrend] = useState(null);
  const { token } = useAuth();

  useEffect(() => {
    loadMoodTrend();
  }, [token]);

  const loadMoodTrend = async () => {
    if (!token) return;

    try {
      const data = await api.getMoodTrend(token, 30);
      setTrend(data);
    } catch (error) {
      console.error('Error loading mood trend:', error);
    }
  };

  if (!trend || Object.keys(trend.mood_distribution || {}).length === 0) {
    return null;
  }

  return (
    <div className="glass-container" style={{ padding: '1.5rem' }}>
      <h3 className="gradient-text" style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>
        30-Day Mood Trend
      </h3>
      <div className="stats-grid">
        {Object.entries(trend.mood_distribution).map(([mood, count]) => (
          <div key={mood} className="stat-box">
            <div className="stat-value">{count}</div>
            <div className="stat-label">{mood}</div>
          </div>
        ))}
        <div className="stat-box">
          <div className="stat-value">
            {trend.average_energy_level
              ? trend.average_energy_level.toFixed(1)
              : '-'}
          </div>
          <div className="stat-label">Avg Energy</div>
        </div>
      </div>
    </div>
  );
};

export default MoodTrend;
