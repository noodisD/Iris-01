const Modal = ({ isOpen, onClose, title, children, footer }) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[2000] flex justify-center items-center"
      onClick={onClose}
    >
      <div
        className="bg-primary-dark/95 border border-primary-gold/30 rounded-xl p-8 w-full max-w-md shadow-2xl animate-scale"
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <h2 className="text-2xl text-primary-gold font-bold mb-4">{title}</h2>
        )}

        <div className="mb-6 text-text-primary">{children}</div>

        {footer && (
          <div className="flex gap-4 justify-end">{footer}</div>
        )}
      </div>
    </div>
  );
};

export default Modal;
