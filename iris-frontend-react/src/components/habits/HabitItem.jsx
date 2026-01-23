import { useState, memo } from 'react';
import Modal from '../shared/Modal';
import { ChipGroup } from '../shared/Chip';

const HabitItem = memo(({ habit, onComplete, onSkip }) => {
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
      <div className="card-insight flex flex-col md:flex-row justify-between items-start md:items-center gap-6 p-6 animate-fade-in">
        <div className="flex-1 w-full">
          <div className="flex items-center gap-3 mb-2">
            <h3 className="text-xl font-bold text-text-primary">
              {habit.name}
            </h3>
            {habit.category && (
              <span className="badge opacity-80">{habit.category}</span>
            )}
          </div>
          
          <div className="flex items-center gap-4 text-sm text-text-secondary">
            <span className="flex items-center gap-1">
              <span className="text-primary-amber">🔥</span> {habit.current_streak} day streak
            </span>
            <span className="text-text-muted">|</span>
            <span className="capitalize">{habit.habit_type}</span>
          </div>

          {habit.weekly_target > 0 && habit.weekly_progress && (
            <div className="mt-4 max-w-md">
              <div className="flex justify-between text-xs font-medium mb-1.5">
                <span className="text-text-secondary uppercase tracking-tight">Weekly Progress</span>
                <span className="text-primary-amber">{progressPercent}%</span>
              </div>
              <div className="w-full h-2 bg-border-subtle rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary-amber to-primary-gold transition-all duration-500 ease-out"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <div className="text-[10px] text-text-muted mt-1.5 uppercase tracking-wide">
                {habit.weekly_progress.current} / {habit.weekly_progress.target} {habit.weekly_progress.metric} goal
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-3 w-full md:w-auto pt-2 md:pt-0">
          <button onClick={handleComplete} className="btn-primary interactive-tactile flex-1 md:flex-none">
            {habit.habit_type === 'completion' ? '✓ Mark Done' : '+ Log Progress'}
          </button>
          <button
            onClick={() => setShowSkipModal(true)}
            className="btn-secondary interactive-tactile flex-1 md:flex-none"
          >
            Skip
          </button>
        </div>
      </div>

      {/* Skip Modal */}
      <Modal
        isOpen={showSkipModal}
        onClose={() => setShowSkipModal(false)}
        title="Skip Ritual"
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
        <div className="space-y-4">
          <p className="text-text-secondary text-sm">
            Maintaining a streak is about intentionality. If you're skipping today, noting the reason can help identify patterns of friction.
          </p>
          <textarea
            value={skipReason}
            onChange={(e) => setSkipReason(e.target.value)}
            rows="3"
            placeholder="Why are you skipping today? (e.g., Illness, high priority work...)"
            className="input-field resize-none"
          />
        </div>
      </Modal>

      {/* Log Value Modal */}
      <Modal
        isOpen={showLogModal}
        onClose={() => setShowLogModal(false)}
        title="Log Activity"
        footer={
          <>
            <button
              onClick={() => setShowLogModal(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button onClick={handleLogSubmit} className="btn-primary">
              Record Progress
            </button>
          </>
        }
      >
        <div className="space-y-6">
          <p className="text-text-primary font-medium">
            {habit.habit_type === 'duration'
              ? 'How much time did you invest?'
              : `How many ${habit.tracking_metric} did you complete?`}
          </p>

          {habit.habit_type === 'duration' && (
            <div>
              <label className="block text-xs text-text-muted uppercase tracking-widest mb-3">
                Unit of measurement
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

          <div>
            <label className="block text-xs text-text-muted uppercase tracking-widest mb-2">
              Value
            </label>
            <input
              type="number"
              value={logValue}
              onChange={(e) => setLogValue(e.target.value)}
              step="0.1"
              min="0"
              className="input-field text-lg"
              autoFocus
            />
          </div>
        </div>
      </Modal>
    </>
  );
});

HabitItem.displayName = 'HabitItem';

export default HabitItem;
