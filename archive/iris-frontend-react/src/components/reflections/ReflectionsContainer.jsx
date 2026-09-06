import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useApp } from '../../context/AppContext';
import api from '../../services/api';
import ReflectionForm from './ReflectionForm';
import ReflectionItem from './ReflectionItem';
import MoodTrend from './MoodTrend';

const ReflectionsContainer = () => {
  const [reflections, setReflections] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);

  const { token } = useAuth();
  const { showToast } = useApp();

  useEffect(() => {
    loadReflections();
  }, [token]);

  const loadReflections = async () => {
    if (!token) return;

    try {
      const data = await api.getReflections(token, 10);
      setReflections(data.reflections);
    } catch (error) {
      console.error('Error loading reflections:', error);
      showToast('Failed to load reflections', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateReflection = async (reflectionData) => {
    try {
      await api.createReflection(token, reflectionData);
      setShowForm(false);
      loadReflections();
      showToast(
        "I've noted your thoughts down. It's always good to reflect and process."
      );

      // Trigger proactive response
      await api.triggerProactive(token, 'reflection', reflectionData);
    } catch (error) {
      console.error('Error creating reflection:', error);
      showToast(
        "I couldn't save your reflection just now. Shall we try again?",
        'error'
      );
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="page-container">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 section-header">
          <div>
            <h2 className="text-4xl font-black tracking-tight text-gradient-gold">Reflections</h2>
            <p className="text-text-secondary text-sm mt-2 max-w-md">Capture your thoughts and observe your growth over time.</p>
          </div>
          <button
            className="btn-primary interactive-tactile whitespace-nowrap"
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? 'Close Entry' : '+ New Reflection'}
          </button>
        </div>

        {/* Reflection Form */}
        {showForm && (
          <div className="mb-12">
            <ReflectionForm
              onSubmit={handleCreateReflection}
              onCancel={() => setShowForm(false)}
            />
          </div>
        )}

        {/* Reflections List */}
        <div className="space-y-8">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className="w-10 h-10 border-4 border-primary-amber border-t-transparent rounded-full animate-spin"></div>
              <p className="text-text-muted font-medium animate-pulse">Retrieving your memory fragments...</p>
            </div>
          ) : reflections.length === 0 ? (
            <div className="glass-surface p-16 text-center border-dashed border-2">
              <p className="text-text-secondary text-xl font-medium">The mirror is empty.</p>
              <p className="text-text-muted text-sm mt-2 mb-6">Share your first thought to begin the pattern discovery.</p>
              <button 
                onClick={() => setShowForm(true)}
                className="btn-secondary interactive-tactile"
              >
                Reflect Now
              </button>
            </div>
          ) : (
            <div className="grid gap-8">
              {reflections.map((reflection) => (
                <ReflectionItem key={reflection.id} reflection={reflection} />
              ))}
            </div>
          )}
        </div>

        {/* Mood Trend */}
        {!loading && reflections.length > 0 && (
          <div className="pt-16 mt-16 border-t border-border-subtle">
            <div className="mb-8">
              <h3 className="text-2xl font-black text-text-primary">Temporal Analysis</h3>
              <p className="text-text-muted text-sm mt-1">30-day psychological distribution</p>
            </div>
            <MoodTrend />
          </div>
        )}
      </div>
    </div>
  );
};

export default ReflectionsContainer;
