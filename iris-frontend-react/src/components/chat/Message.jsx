const Message = ({ text, sender }) => {
  return (
    <div
      className={`w-full max-w-3xl ${
        sender === 'user' ? 'message-user self-end' : 'message-iris self-start'
      }`}
    >
      {text}
    </div>
  );
};

export default Message;
