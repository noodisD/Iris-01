import { Component, type ReactNode } from 'react';
import { ErrorState } from '@/components/states';
import { recordError } from '@/lib/telemetry';

interface Props { children: ReactNode }
interface State { failed: boolean }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }): void {
    recordError(error.message, error, { component_stack: info.componentStack ?? '' });
  }

  render(): ReactNode {
    if (this.state.failed) {
      return (
        <ErrorState
          message="Something broke on this screen. It has been recorded in the Observatory."
          onRetry={() => location.reload()}
        />
      );
    }
    return this.props.children;
  }
}
