import { useState } from 'react';
import { ChipGroup } from '../shared/Chip';

const ReflectionForm = ({ onSubmit, onCancel }) => {
  const [content, setContent] = useState('');
  const [mood, setMood] = useState(null);
  const [energyLevel, setEnergyLevel] = useState(null);
  const [tags, setTags] = useState([]);

  const moodChips = [
    { label: 'Great ✨', value: 'great' },
    { label: 'Good 🙂', value: 'good' },
    { label: 'Okay 😐', value: 'okay' },
    { label: 'Bad 😕', value: 'bad' },
    { label: 'Terrible 😫', value: 'terrible' },
  ];

  const energyChips = [
    { label: '1 - Very Low', value: 1 },
    { label: '2 - Low', value: 2 },
    { label: '3 - Medium', value: 3 },
    { label: '4 - High', value: 4 },
    { label: '5 - Very High', value: 5 },
  ];

  const tagChips = [
    { label: 'Productive', value: 'productive' },
    { label: 'Grateful', value: 'grateful' },
    { label: 'Tired', value: 'tired' },
    { label: 'Anxious', value: 'anxious' },
    { label: 'Inspired', value: 'inspired' },
    { label: 'Distracted', value: 'distracted' },
    { label: 'Calm', value: 'calm' },
    { label: 'Stressed', value: 'stressed' },
    { label: 'Creative', value: 'creative' },
    { label: 'Pensive', value: 'pensive' },
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!content.trim()) return;

    onSubmit({
      content,
      mood,
      energy_level: energyLevel,
      tags,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="glass-surface p-6 space-y-4">
      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          What's on your mind?
        </label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Share your thoughts, feelings, and insights..."
          rows="4"
          className="input-field resize-none"
          required
        />
      </div>

      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          How are you feeling?
        </label>
        <ChipGroup chips={moodChips} selected={mood} onChange={setMood} />
      </div>

      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          Energy Level
        </label>
        <ChipGroup
          chips={energyChips}
          selected={energyLevel}
          onChange={setEnergyLevel}
        />
      </div>

      <div>
        <label className="block mb-2 text-sm text-text-secondary">
          Focus Tags (Select multiple)
        </label>
        <ChipGroup
          chips={tagChips}
          selected={tags}
          onChange={setTags}
          allowMultiple={true}
        />
      </div>

      <div className="flex gap-4 pt-4">
        <button type="submit" className="btn-primary interactive-tactile flex-1 py-3">
          Save Reflection
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-secondary interactive-tactile flex-1 py-3"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};

export default ReflectionForm;
