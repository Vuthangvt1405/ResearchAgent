// App root: one QueryClient for the panel's lifetime and an error boundary so a crash
// shows a message inside the panel, not a blank sidebar (AC7).
import { Component, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Notebook } from "@/components/Notebook";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false }, mutations: { retry: false } },
});

class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error("[notebook panel]", error);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="rc-panel-fallback" role="alert">
          The notebook panel hit an error. Reload the page to try again.
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  return (
    <Boundary>
      <QueryClientProvider client={queryClient}>
        <Notebook />
      </QueryClientProvider>
    </Boundary>
  );
}
