import { useState } from 'react';
import { ChipGroup } from '../shared/Chip';

const HabitForm = ({ onSubmit, onCancel }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [habitType, setHabitType] = useState('completion');
  const [weeklyTarget, setWeeklyTarget] = useState(0);
  const [metric, setMetric] = useState('completion');
  const [category, setCategory] = useState('general');

  const habitTypeChips = [
    { label: 'Checkmark ✅', value: 'completion' },
    { label: 'Duration ⏳', value: 'duration' },
    { label: 'Count 🔢', value: 'count' },
  ];

  const categoryChips = [
    { label: 'General', value: 'general' },
    { label: 'Health & Fitness', value: 'health' },
    { label: 'Mindfulness', value: 'mindfulness' },
    { label: 'Productivity', value: 'productivity' },
    { label: 'Learning', value: 'learning' },
    { label: 'Social', value: 'social' },
    { label: 'Hobby', value: 'hobby' },
  ];

  const getDurationMetricChips = () => [
    { label: 'Minutes', value: 'minutes' },
    { label: 'Hours', value: 'hours' },
  ];

  const getCountMetricChips = () => [
    { label: 'Times', value: 'times' },
    { label: 'Pages', value: 'pages' },
    { label: 'Sessions', value: 'sessions' },
  ];

  const handleHabitTypeChange = (type) => {
    setHabitType(type);
    if (type === 'completion') {
      setWeeklyTarget(0);
      setMetric('completion');
    } else if (type === 'duration') {
      setMetric('minutes');
    } else {
      setMetric('times');
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    onSubmit({
      name,
      description: description || null,
      frequency_type: 'daily',
      habit_type: habitType,
      weekly_target: weeklyTarget,
      tracking_metric: metric,
      category,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="glass-container p-6 space-y-4">
      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          Habit Name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., Morning Meditation"
          className="input-field"
          required
        />
      </div>

      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          Description
        </label>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional description"
          className="input-field"
        />
      </div>

      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          Habit Type
        </label>
        <ChipGroup
          chips={habitTypeChips}
          selected={habitType}
          onChange={handleHabitTypeChange}
        />
      </div>

      {habitType !== 'completion' && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block mb-2 text-sm text-text-secondary">
              Weekly Target
            </label>
            <input
              type="number"
              value={weeklyTarget}
              onChange={(e) => setWeeklyTarget(parseFloat(e.target.value) || 0)}
              min="0"
              step="0.1"
              className="input-field"
            />
          </div>
          <div>
            <label className="block mb-2 text-sm text-text-secondary">
              Metric
            </label>
            <ChipGroup
              chips={
                habitType === 'duration'
                  ? getDurationMetricChips()
                  : getCountMetricChips()
              }
              selected={metric}
              onChange={setMetric}
            />
          </div>
        </div>
      )}

      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          Category
        </label>
        <ChipGroup
          chips={categoryChips}
          selected={category}
          onChange={setCategory}
        />
      </div>

      <div className="flex gap-4 pt-2">
        <button type="submit" className="btn-primary flex-1">
          Create
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-secondary flex-1"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};

export default HabitForm;
