import { useState } from 'react';
import Modal from '../shared/Modal';
import { ChipGroup } from '../shared/Chip';

const HabitItem = ({ habit, onComplete, onSkip }) => {
  const [showSkipModal, setShowSkipModal] = useState(false);
  const [skipReason, setSkipReason] = useState('');
  const [showLogModal, setShowLogModal] = useState(false);
  const [logValue, setLogValue] = useState(0);
  const [logMetric, setLogMetric] = useState('minutes');

  const handleComplete = () => {
    if (habit.habit_type === 'completion') {
      onComplete(habit.id, 1.0);
    } else {
      setLogValue(0);
      setLogMetric(habit.tracking_metric || 'minutes');
      setShowLogModal(true);
    }
  };

  const handleLogSubmit = () => {
    let value = parseFloat(logValue);

    // Convert hours to minutes if needed
    if (habit.tracking_metric === 'minutes' && logMetric === 'hours') {
      value = value * 60;
    } else if (habit.tracking_metric === 'hours' && logMetric === 'minutes') {
      value = value / 60;
    }

    if (value > 0) {
      onComplete(habit.id, value);
    }
    setShowLogModal(false);
  };

  const handleSkipSubmit = () => {
    onSkip(habit.id, skipReason);
    setShowSkipModal(false);
    setSkipReason('');
  };

  const progressPercent =
    habit.weekly_progress?.percent ||
    (habit.weekly_target > 0
      ? Math.min(
          100,
          Math.round((habit.weekly_progress?.current / habit.weekly_target) * 100)
        )
      : 0);

  return (
    <>
      <div className="card flex flex-col md:flex-row justify-between items-start md:items-center gap-4 p-4">
        <div className="flex-1">
          <h3 className="text-lg font-bold text-text-primary mb-1">
            {habit.name}
          </h3>
          <p className="text-sm text-text-secondary">
            🔥 Streak: {habit.current_streak} | Type: {habit.habit_type}
          </p>

          {habit.weekly_target > 0 && habit.weekly_progress && (
            <div className="mt-3">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-text-secondary mt-1">
                <span>
                  Weekly Goal: {habit.weekly_progress.current} /{' '}
                  {habit.weekly_progress.target} {habit.weekly_progress.metric}
                </span>
                <span>{progressPercent}%</span>
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <button onClick={handleComplete} className="btn-primary text-sm">
            {habit.habit_type === 'completion' ? '✓ Done' : '+ Log'}
          </button>
          <button
            onClick={() => setShowSkipModal(true)}
            className="btn-secondary text-sm"
          >
            Skip
          </button>
        </div>
      </div>

      {/* Skip Modal */}
      <Modal
        isOpen={showSkipModal}
        onClose={() => setShowSkipModal(false)}
        title="Skipping Habit"
        footer={
          <>
            <button
              onClick={() => setShowSkipModal(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button onClick={handleSkipSubmit} className="btn-primary">
              Confirm Skip
            </button>
          </>
        }
      >
        <p className="mb-4">
          It's okay to take a break. Would you like to note why you're skipping
          this today?
        </p>
        <textarea
          value={skipReason}
          onChange={(e) => setSkipReason(e.target.value)}
          rows="3"
          placeholder="e.g., Not feeling well, busy day... (optional)"
          className="input-field resize-none"
        />
      </Modal>

      {/* Log Value Modal */}
      <Modal
        isOpen={showLogModal}
        onClose={() => setShowLogModal(false)}
        title="Log Progress"
        footer={
          <>
            <button
              onClick={() => setShowLogModal(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button onClick={handleLogSubmit} className="btn-primary">
              Save Progress
            </button>
          </>
        }
      >
        <p className="mb-4">
          {habit.habit_type === 'duration'
            ? 'How long did you complete?'
            : `How many ${habit.tracking_metric} did you complete?`}
        </p>

        {habit.habit_type === 'duration' && (
          <div className="mb-4">
            <label className="block text-xs text-text-secondary mb-2">
              Log in:
            </label>
            <ChipGroup
              chips={[
                { label: 'Minutes', value: 'minutes' },
                { label: 'Hours', value: 'hours' },
              ]}
              selected={logMetric}
              onChange={setLogMetric}
            />
          </div>
        )}

        <input
          type="number"
          value={logValue}
          onChange={(e) => setLogValue(e.target.value)}
          step="0.1"
          min="0"
          className="input-field"
        />
      </Modal>
    </>
  );
};

export default HabitItem;
