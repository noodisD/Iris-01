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
    <div className="glass-container p-6">
      <h3 className="text-xl gradient-text mb-4">30-Day Mood Trend</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {Object.entries(trend.mood_distribution).map(([mood, count]) => (
          <div
            key={mood}
            className="bg-primary-gold/5 p-4 rounded-lg text-center"
          >
            <div className="text-2xl font-bold text-primary-gold">{count}</div>
            <div className="text-xs text-text-secondary mt-2 capitalize">
              {mood}
            </div>
          </div>
        ))}
        <div className="bg-primary-gold/5 p-4 rounded-lg text-center">
          <div className="text-2xl font-bold text-primary-gold">
            {trend.average_energy_level
              ? trend.average_energy_level.toFixed(1)
              : '-'}
          </div>
          <div className="text-xs text-text-secondary mt-2">Avg Energy</div>
        </div>
      </div>
    </div>
  );
};

export default MoodTrend;
