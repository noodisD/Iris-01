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
    <div className="flex-1 overflow-y-auto p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <h2 className="text-2xl gradient-text">Reflections</h2>
          <button
            className="btn-primary text-sm"
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? 'Cancel' : '+ New Reflection'}
          </button>
        </div>

        {/* Reflection Form */}
        {showForm && (
          <ReflectionForm
            onSubmit={handleCreateReflection}
            onCancel={() => setShowForm(false)}
          />
        )}

        {/* Reflections List */}
        {loading ? (
          <p className="text-text-secondary text-center py-8">
            Loading reflections...
          </p>
        ) : reflections.length === 0 ? (
          <p className="text-text-secondary text-center py-8">
            No reflections yet. Start reflecting!
          </p>
        ) : (
          <div className="space-y-4">
            {reflections.map((reflection) => (
              <ReflectionItem key={reflection.id} reflection={reflection} />
            ))}
          </div>
        )}

        {/* Mood Trend */}
        {!loading && reflections.length > 0 && <MoodTrend />}
      </div>
    </div>
  );
};

export default ReflectionsContainer;
