import { useApp } from '../../context/AppContext';

const Toast = () => {
  const { toasts, removeToast } = useApp();

  const getEmoji = (type) => {
    switch (type) {
      case 'error':
        return '☁️';
      case 'info':
        return '💡';
      default:
        return '✨';
    }
  };

  return (
    <div className="fixed bottom-8 right-8 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="glass-container animate-slide-in min-w-[300px] p-4 border-l-4 border-primary-gold shadow-xl"
          onClick={() => removeToast(toast.id)}
        >
          <div className="flex flex-col gap-1">
            <small className="text-primary-gold font-bold text-xs">IRIS</small>
            <div className="flex items-center gap-2">
              <span>{getEmoji(toast.type)}</span>
              <span className="text-text-primary">{toast.message}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default Toast;
